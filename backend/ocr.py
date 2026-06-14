import re
import json
import time
import cv2
import numpy as np
import requests
import state
import database

# EasyOCR kann viele verschiedene Zeichen erkennen — auch Sonderzeichen, Kleinbuchstaben, etc.
# Das wollen wir nicht, weil Kennzeichen nur aus Großbuchstaben und Zahlen bestehen.
# Mit dieser Liste sagen wir EasyOCR: "Erkenne NUR diese Zeichen, alles andere ignorieren."
# Das macht die Erkennung schneller und verhindert Fehler wie "WR@B 123" statt "WRAB123".
_ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def init_ocr():
    # Lädt das EasyOCR-Modell in den Speicher. Wird beim Programmstart einmal aufgerufen.
    import easyocr
    print("[OCR] Initialisiere EasyOCR...")
    # Das Laden des Modells dauert einige Sekunden — deshalb läuft es in einem eigenen Thread
    # damit der Rest des Programms (Flask, WebSocket) schon starten kann.
    # gpu=False weil der Server keine Grafikkarte hat — läuft auf der normalen CPU.
    state.ocr_reader = easyocr.Reader(['en'], gpu=False)
    print("[OCR] EasyOCR bereit!")


def broadcast(data: dict):
    # Schickt ein Ergebnis als JSON an alle Browser die gerade die Seite offen haben.
    # Der Browser ist über WebSocket verbunden — das ist eine dauerhafte Verbindung
    # (kein normales HTTP). So kann der Server von sich aus Daten schicken,
    # ohne dass der Browser zuerst fragen muss. Das ermöglicht die Live-Anzeige im Dashboard.
    msg = json.dumps(data)  # Python-Dictionary in einen JSON-Text umwandeln
    with state.ws_clients_lock:
        dead = []
        for client in state.ws_clients:
            try:
                client.send(msg)
            except Exception:
                # Falls ein Browser die Seite geschlossen hat, schlägt send() fehl.
                # Wir merken uns diese toten Verbindungen und löschen sie danach.
                dead.append(client)
        for client in dead:
            state.ws_clients.remove(client)


def preprocess(img):
    # Bereitet ein Kamerabild für die OCR vor.
    # Rohe Kamerabilder sind oft zu bunt, zu groß, zu dunkel oder zu unscharf
    # für eine zuverlässige Texterkennung. Diese Funktion macht das Bild
    # OCR-freundlicher — Schritt für Schritt.
    # Schritt 1: Farbe entfernen
    # OCR braucht keine Farben — Buchstaben erkennt man auch in Graustufen.
    # Graustufen = jeder Pixel hat nur noch einen Helligkeitswert (0=schwarz, 255=weiß)
    # statt drei Werte (Rot, Grün, Blau). Das macht das Bild einfacher zu verarbeiten.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Schritt 2: Größe normieren
    # Die Kamera liefert unterschiedlich große Bilder je nach Einstellung.
    # EasyOCR liefert konsistentere Ergebnisse wenn das Bild immer gleich groß ist.
    # Wir skalieren alles auf genau 640px Breite — die Höhe wird proportional angepasst.
    h, w = gray.shape
    if w != 640:
        scale = 640 / w
        # INTER_AREA = bessere Qualität beim Verkleinern
        # INTER_CUBIC = bessere Qualität beim Vergrößern
        interp = cv2.INTER_AREA if w > 640 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, (640, int(h * scale)), interpolation=interp)

    # Schritt 3: Kontrast verbessern (CLAHE)
    # CLAHE = Contrast Limited Adaptive Histogram Equalization
    # Normaler Kontrast verbessert das gesamte Bild gleichmäßig.
    # CLAHE verbessert den Kontrast in kleinen lokalen Bereichen — das hilft besonders
    # wenn ein Teil des Kennzeichens im Schatten und ein anderer in der Sonne ist.
    # clipLimit=3.0 verhindert zu starkes Rauschen, tileGridSize=(8,8) = Bereichsgröße
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Schritt 4: Schärfen
    # Dieser Kernel (3x3 Matrix) ist ein Schärfefilter.
    # Er hebt Kanten und Übergänge hervor — dadurch werden Buchstabenkonturen
    # klarer und EasyOCR erkennt sie besser.
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    return gray


def extract_plate(raw: str) -> str | None:
    # Wandelt einen rohen OCR-Text in ein gültiges österreichisches Kennzeichen um.
    # Das Problem: Österreichische Kennzeichen haben an Position 3 ein Wappen-Symbol
    # (z.B. das Bundesadler-Symbol). Die OCR kann kein Wappen lesen — sie liest es
    # als zufälligen Buchstaben oder Symbol. Dieses falsch erkannte Zeichen muss
    # entfernt werden damit das Kennzeichen stimmt.
    # Beispiel: "WR?AB123" → "WRAB123"
    # Alles entfernen was kein Buchstabe oder keine Zahl ist
    # (Leerzeichen, Bindestriche, Wappen-Symbol, etc.)
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())

    # Das 3. Zeichen (Index 2) ist immer das Wappen → entfernen
    # Beispiel: "WR" + "X" + "AB123" → "WR" + "AB123" = "WRAB123"
    if len(text) > 3:
        text = text[:2] + text[3:]

    # Prüfen ob das Ergebnis wie ein echtes Kennzeichen aussieht:
    # - Muss 5 bis 9 Zeichen lang sein
    # - Muss mit 1 bis 3 Buchstaben beginnen (Bezirkskürzel, z.B. "WR", "GD", "B")
    # - Danach kommen Buchstaben und Zahlen (die eigentliche Nummer)
    if 5 <= len(text) <= 9 and re.match(r'^[A-Z]{1,3}[A-Z0-9]+$', text):
        return text
    return None  # Kein gültiges Kennzeichen → None zurückgeben


def run_ocr_on(img) -> tuple | None:
    # Führt die eigentliche KI-Texterkennung auf einem Bild aus.
    # Gibt ein Tupel (kennzeichen, konfidenz) zurück wenn etwas erkannt wurde,
    # oder None wenn kein gültiges Kennzeichen gefunden wurde.
    # Sicherheitscheck: OCR-Modell muss geladen sein und ein Bild muss vorhanden sein
    if state.ocr_reader is None or img is None:
        return None

    # Bild vorverarbeiten (Graustufen, Kontrast, Schärfe)
    processed = preprocess(img)

    # EasyOCR auf das vorverarbeitete Bild loslassen.
    # mag_ratio=1.5: EasyOCR vergrößert das Bild intern vor der Analyse —
    #   das hilft bei kleinen Kennzeichen die weit weg sind.
    # text_threshold=0.5: EasyOCR meldet Text bereits ab 50% Sicherheit
    #   (Standard wäre 70% — wir senken es damit auch schwer lesbare Schilder erkannt werden).
    # allowlist=_ALLOWLIST: nur Großbuchstaben und Zahlen erlaubt (kein Sonderzeichen).
    results = state.ocr_reader.readtext(processed, allowlist=_ALLOWLIST,
                                        mag_ratio=1.5, text_threshold=0.5)
    print(f"[OCR-RAW] {[(t, f'{c:.0%}') for _, t, c in results]}")

    # EasyOCR kann mehrere Textbereiche im Bild finden (z.B. auch Aufkleber oder Beschriftungen).
    # Wir wollen nur das beste Ergebnis das auch ein gültiges Kennzeichen-Format hat.
    best = None
    for (_, text, conf) in results:
        if conf < 0.4:
            continue  # Unter 40% Sicherheit → zu unsicher, ignorieren
        plate = extract_plate(text)
        if plate is None:
            continue  # Kein gültiges Kennzeichen-Format → ignorieren
        if best is None or conf > best[1]:
            best = (plate, conf)  # Bestes Ergebnis merken

    return best


def ocr_worker():
    # Der Haupt-Scan-Loop — läuft als Hintergrund-Thread solange das Programm läuft.
    # Dieser Thread macht drei Dinge in einer Endlosschleife:
    #   1. Frame vom Kamera-Proxy holen
    #   2. OCR drauf laufen lassen
    #   3. Ergebnis ans Frontend schicken und ggf. das Tor öffnen
    # Warten bis EasyOCR fertig geladen ist (kann einige Sekunden dauern)
    while state.ocr_reader is None:
        time.sleep(0.5)
    print("[OCR] Worker gestartet")

    while True:
        # Scanning kann über die API pausiert werden (z.B. über einen Button im Dashboard)
        if not state.scanning:
            time.sleep(0.5)
            continue

        # Aktuellen Frame holen — mit Lock damit camera.py nicht gleichzeitig schreibt
        with state.ocr_lock:
            img = state.ocr_frame.copy() if state.ocr_frame is not None else None

        result = run_ocr_on(img)
        now = time.time()

        # Voting-Puffer bereinigen: Lesungen die älter als VOTE_WINDOW_SECS sind rauswerfen.
        # So zählen nur Erkennungen der letzten 6 Sekunden.
        state.recent_reads = [(p, t) for p, t in state.recent_reads
                              if now - t < state.VOTE_WINDOW_SECS]

        if result is None:
            # Nichts erkannt → Browser informieren damit die Anzeige aktuell bleibt
            broadcast({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                       "erlaubt": False, "zeitstempel": now * 1000})
            time.sleep(0.3)
            continue

        plate, conf = result
        print(f"[OCR] Gelesen: '{plate}' ({conf:.0%})")

        # Aktuelle Lesung mit Zeitstempel in den Voting-Puffer eintragen
        state.recent_reads.append((plate, now))

        # Voting: wie oft wurde dieses Kennzeichen in den letzten 6 Sekunden erkannt?
        # Das verhindert Fehlauslösungen — ein einzelnes schlechtes Bild reicht nicht.
        # Erst wenn dasselbe Kennzeichen oft genug erkannt wird, gilt es als bestätigt.
        votes = sum(1 for p, _ in state.recent_reads if p == plate)
        print(f"[OCR] Votes: {votes}/{state.VOTE_THRESHOLD}")

        # Browser über aktuelle Erkennung informieren (Tor noch nicht geöffnet)
        broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                   "erlaubt": False, "zeitstempel": now * 1000,
                   "confirmed": votes >= state.VOTE_THRESHOLD})

        if votes >= state.VOTE_THRESHOLD:
            # Cooldown prüfen: dasselbe Kennzeichen darf nicht öfter als alle 30 Sekunden
            # das Tor öffnen — sonst würde das Tor aufgehen solange das Auto vor der Kamera steht.
            cooldown_ok = (plate not in state.last_triggered or
                           (now - state.last_triggered[plate]) > 30)
            if cooldown_ok:
                granted = database.check_plate(plate)      # Ist das Kennzeichen in der Whitelist?
                database.log_access(plate, granted, conf)  # Versuch ins Log schreiben (immer)
                state.recent_reads = []                    # Puffer leeren damit nicht sofort nochmal ausgelöst wird

                if granted:
                    state.last_triggered[plate] = now
                    print(f"[OCR] {plate} — ZUGANG GEWÄHRT ✓")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": True, "zeitstempel": now * 1000, "confirmed": True})
                    # HTTP-Anfrage an den ESP32 → Relais schaltet → Tor geht auf
                    try:
                        requests.get(f"{state.esp32_base_url}/toggle_gate", timeout=3) # Tor öffnen
                    except Exception as e:
                        print(f"[OCR] Relay-Fehler: {e}")
                else:
                    print(f"[OCR] {plate} — KEIN ZUGANG ✗")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": False, "zeitstempel": now * 1000, "confirmed": True})

        time.sleep(0.3)  # 0.3 Sekunden warten → ca. 3 Frames pro Sekunde analysiert
