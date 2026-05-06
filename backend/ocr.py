import re
import json
import time
import cv2
import numpy as np
import requests
import state
import database

# Nur diese Zeichen darf EasyOCR erkennen — beschleunigt die Erkennung
# und verhindert dass Sonderzeichen oder Kleinbuchstaben ausgegeben werden
_ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


def init_ocr():
    """Lädt das EasyOCR-Modell. Läuft in einem eigenen Thread beim Start."""
    import easyocr
    print("[OCR] Initialisiere EasyOCR...")
    # gpu=False weil der Server keine GPU hat — läuft auf CPU
    state.ocr_reader = easyocr.Reader(['en'], gpu=False)
    print("[OCR] EasyOCR bereit!")


def broadcast(data: dict):
    """Sendet ein Erkennungsergebnis als JSON an alle offenen Browser-Verbindungen."""
    msg = json.dumps(data)
    with state.ws_clients_lock:
        dead = []
        for client in state.ws_clients:
            try:
                client.send(msg)
            except Exception:
                # Client hat die Verbindung getrennt → zur Löschliste hinzufügen
                dead.append(client)
        for client in dead:
            state.ws_clients.remove(client)


def preprocess(img):
    """Bereitet ein Bild für die OCR vor: Graustufen, Normgröße, Kontrast, Schärfe."""
    # In Graustufen umwandeln — OCR braucht keine Farbe
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Auf genau 640px Breite skalieren für konsistente OCR-Ergebnisse
    h, w = gray.shape
    if w != 640:
        scale = 640 / w
        interp = cv2.INTER_AREA if w > 640 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, (640, int(h * scale)), interpolation=interp)

    # CLAHE: lokale Kontrastverbesserung (hilft bei schlechter Beleuchtung)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Schärfefilter: hebt Kanten hervor damit Buchstaben klarer erkennbar sind
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    return gray


def extract_plate(raw: str) -> str | None:
    """Wandelt rohen OCR-Text in ein gültiges Kennzeichen um.

    Österreichische Kennzeichen haben an Position 3 ein Wappen-Symbol,
    das die OCR als Buchstaben liest → wird entfernt.
    Gültig: 1-3 Buchstaben am Anfang, gesamt 5-9 Zeichen.
    """
    # Alle Nicht-Buchstaben/Zahlen entfernen
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())

    # Das 3. Zeichen (Index 2) ist das Wappen — entfernen
    if len(text) > 3:
        text = text[:2] + text[3:]

    # Format prüfen: beginnt mit 1-3 Buchstaben, dann Buchstaben/Zahlen, gesamt 5-9 Zeichen
    if 5 <= len(text) <= 9 and re.match(r'^[A-Z]{1,3}[A-Z0-9]+$', text):
        return text
    return None


def run_ocr_on(img) -> tuple | None:
    """Führt OCR auf einem Bild aus. Gibt (kennzeichen, konfidenz) oder None zurück."""
    if state.ocr_reader is None or img is None:
        return None

    processed = preprocess(img)

    # mag_ratio=1.5: EasyOCR vergrößert intern vor der Analyse (besser für kleine Schilder)
    # text_threshold=0.5: Texterkennung bereits bei 50% Sicherheit (Standard ist 70%)
    results = state.ocr_reader.readtext(processed, allowlist=_ALLOWLIST,
                                        mag_ratio=1.5, text_threshold=0.5)
    print(f"[OCR-RAW] {[(t, f'{c:.0%}') for _, t, c in results]}")

    # Bestes Ergebnis (höchste Konfidenz) das ein gültiges Kennzeichen-Format hat
    best = None
    for (_, text, conf) in results:
        if conf < 0.4:
            continue  # zu unsicher → ignorieren
        plate = extract_plate(text)
        if plate is None:
            continue  # kein gültiges Kennzeichen-Format
        if best is None or conf > best[1]:
            best = (plate, conf)

    return best


def ocr_worker():
    """Hintergrund-Thread: liest laufend Frames und erkennt Kennzeichen."""
    # Warten bis EasyOCR fertig geladen ist
    while state.ocr_reader is None:
        time.sleep(0.5)
    print("[OCR] Worker gestartet")

    while True:
        # Wenn Scanner pausiert → warten
        if not state.scanning:
            time.sleep(0.5)
            continue

        # Aktuellen Frame kopieren (Lock damit der Proxy nicht gleichzeitig schreibt)
        with state.ocr_lock:
            img = state.ocr_frame.copy() if state.ocr_frame is not None else None

        result = run_ocr_on(img)
        now = time.time()

        # Einträge älter als VOTE_WINDOW_SECS aus dem Puffer entfernen
        state.recent_reads = [(p, t) for p, t in state.recent_reads
                              if now - t < state.VOTE_WINDOW_SECS]

        if result is None:
            # Nichts erkannt → Frontend informieren
            broadcast({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                       "erlaubt": False, "zeitstempel": now * 1000})
            time.sleep(0.3)
            continue

        plate, conf = result
        print(f"[OCR] Gelesen: '{plate}' ({conf:.0%})")

        # Lesung mit Zeitstempel in den Puffer eintragen
        state.recent_reads.append((plate, now))

        # Zählen wie oft dieses Kennzeichen im Zeitfenster gelesen wurde
        votes = sum(1 for p, _ in state.recent_reads if p == plate)
        print(f"[OCR] Votes: {votes}/{state.VOTE_THRESHOLD}")

        # Frontend über aktuelle Erkennung informieren (noch kein Auslösen)
        broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                   "erlaubt": False, "zeitstempel": now * 1000,
                   "confirmed": votes >= state.VOTE_THRESHOLD})

        if votes >= state.VOTE_THRESHOLD:
            # Cooldown prüfen: dasselbe Kennzeichen darf nicht öfter als alle 30s auslösen
            cooldown_ok = (plate not in state.last_triggered or
                           (now - state.last_triggered[plate]) > 30)
            if cooldown_ok:
                granted = database.check_plate(plate)   # In Whitelist?
                database.log_access(plate, granted, conf)  # Im Log speichern
                state.recent_reads = []  # Puffer leeren nach Auslösung

                if granted:
                    state.last_triggered[plate] = now
                    print(f"[OCR] {plate} — ZUGANG GEWÄHRT ✓")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": True, "zeitstempel": now * 1000, "confirmed": True})
                    # Relay am ESP32 auslösen → Tor öffnen
                    try:
                        requests.get(f"{state.esp32_base_url}/toggle_gate", timeout=3)
                    except Exception as e:
                        print(f"[OCR] Relay-Fehler: {e}")
                else:
                    print(f"[OCR] {plate} — KEIN ZUGANG ✗")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": False, "zeitstempel": now * 1000, "confirmed": True})

        time.sleep(0.3)
