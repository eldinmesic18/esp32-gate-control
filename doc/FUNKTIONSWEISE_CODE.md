# Funktionsweise mit Code – ESP32 Kennzeichenerkennung

---

## 1. Start

Beim Ausführen von `app.py` passieren drei Dinge gleichzeitig:

```python
# Datenbank öffnen / erstellen
database.init_db()

# Blueprints registrieren (Routen bekannt machen)
app.register_blueprint(camera_bp)
app.register_blueprint(plates_bp)
app.register_blueprint(recognition_bp)
```

Und die Hintergrund-Threads starten:

```python
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    threading.Thread(target=ocr.init_ocr, daemon=True).start()    # EasyOCR laden
    threading.Thread(target=ocr.ocr_worker, daemon=True).start()  # Scanner starten
```

> `daemon=True` bedeutet: der Thread wird automatisch beendet wenn das Hauptprogramm stoppt.

---

## 2. Kamera-Stream

Der ESP32 sendet einen MJPEG-Stream – ein endloser Datenstrom voller JPEG-Bilder.
Das Backend liest ihn und sucht darin einzelne Bilder anhand der JPEG-Markierungen:

```python
r = requests.get(state.camera_url, stream=True, timeout=10)

for chunk in r.iter_content(chunk_size=4096):
    buf += chunk

    while True:
        start = buf.find(b'\xff\xd8')   # JPEG-Start
        end   = buf.find(b'\xff\xd9')   # JPEG-Ende

        jpg = buf[start:end + 2]        # Ein vollständiges Bild ausschneiden
        buf = buf[end + 2:]             # Verarbeiteten Teil aus dem Puffer entfernen
```

Jedes Bild wird gleichzeitig an den Browser und den OCR-Worker weitergegeben:

```python
# Für den OCR-Worker speichern
with state.ocr_lock:
    state.ocr_frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

# An den Browser schicken (MJPEG-Format)
yield (b'--frame\r\n'
       b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
```

---

## 3. Bildverarbeitung

Bevor EasyOCR das Bild analysiert, wird es vorbereitet:

```python
def preprocess(img):
    # 1. Farbe entfernen – OCR braucht keine Farbe
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Auf einheitliche Breite bringen (640px)
    h, w = gray.shape
    if w != 640:
        scale = 640 / w
        interp = cv2.INTER_AREA if w > 640 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, (640, int(h * scale)), interpolation=interp)

    # 3. Kontrast verbessern (CLAHE – funktioniert lokal, nicht global)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 4. Schärfen – Buchstabenkanten hervorheben
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    return gray
```

---

## 4. Kennzeichenerkennung (OCR)

Das vorbereitete Bild geht an EasyOCR:

```python
_ALLOWLIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

results = state.ocr_reader.readtext(
    processed,
    allowlist=_ALLOWLIST,   # Nur Buchstaben und Zahlen erlaubt
    mag_ratio=1.5,          # EasyOCR vergrößert intern vor der Analyse
    text_threshold=0.5      # Erkennung ab 50% Sicherheit
)
```

EasyOCR gibt eine Liste zurück, z.B.:
```
[("WR◆AB123", 0.87), ("something", 0.21)]
```

Daraus wird das beste Ergebnis mit der höchsten Konfidenz gewählt:

```python
best = None
for (_, text, conf) in results:
    if conf < 0.4:
        continue  # Zu unsicher → ignorieren
    plate = extract_plate(text)
    if plate is None:
        continue  # Kein gültiges Kennzeichen-Format
    if best is None or conf > best[1]:
        best = (plate, conf)
```

---

## 5. Wappen entfernen & Format prüfen

Österreichische Kennzeichen haben an dritter Stelle ein Wappen.
Die KI liest es als Zeichen mit → wird automatisch entfernt:

```python
def extract_plate(raw: str) -> str | None:
    # Nur Buchstaben und Zahlen behalten
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())

    # 3. Zeichen (Index 2) = Wappen → entfernen
    if len(text) > 3:
        text = text[:2] + text[3:]

    # Format prüfen: 1-3 Buchstaben am Anfang, gesamt 5-9 Zeichen
    if 5 <= len(text) <= 9 and re.match(r'^[A-Z]{1,3}[A-Z0-9]+$', text):
        return text
    return None
```

Beispiel:
```
"WR◆AB123"  →  "WRAB123"   ✓ gültig
"ABCDEFGH"  →  None         ✗ kein Kennzeichen-Format
"XY"        →  None         ✗ zu kurz
```

---

## 6. Voting

Ein einzelnes Bild reicht nicht – das Kennzeichen muss mehrfach erkannt werden.
Alte Einträge (älter als 6 Sekunden) werden verworfen:

```python
# Alte Einträge entfernen
state.recent_reads = [(p, t) for p, t in state.recent_reads
                      if now - t < state.VOTE_WINDOW_SECS]

# Neue Lesung hinzufügen
state.recent_reads.append((plate, now))

# Zählen wie oft dieses Kennzeichen im Zeitfenster vorkam
votes = sum(1 for p, _ in state.recent_reads if p == plate)
```

Erst wenn `votes >= VOTE_THRESHOLD` (aktuell: 1) gilt es als bestätigt.

---

## 7. Datenbankabfrage

Ist das Kennzeichen in der Whitelist?

```python
def check_plate(plate_number):
    norm = _normalize(plate_number)   # Bindestriche etc. entfernen
    c.execute("SELECT plate_number FROM plates WHERE aktiv=1")
    rows = c.fetchall()
    return any(_normalize(r["plate_number"]) == norm for r in rows)
```

Die Normalisierung sorgt dafür dass `"WR-AB 123"` und `"WRAB123"` gleich behandelt werden:

```python
def _normalize(plate: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', plate.upper())
```

---

## 8. Tor öffnen oder ablehnen

```python
granted = database.check_plate(plate)
database.log_access(plate, granted, conf)  # Immer im Log speichern

if granted:
    state.last_triggered[plate] = now  # Cooldown starten

    # HTTP-Anfrage an den ESP32 → Relais schaltet → Tor öffnet
    requests.get(f"{state.esp32_base_url}/toggle_gate", timeout=3)

    broadcast({"erlaubt": True, ...})   # Grünes Licht im Browser
else:
    broadcast({"erlaubt": False, ...})  # Rotes Licht im Browser
```

Cooldown: dasselbe Kennzeichen kann nicht öfter als alle 30 Sekunden auslösen:

```python
cooldown_ok = (plate not in state.last_triggered or
               (now - state.last_triggered[plate]) > 30)
```

---

## 9. Live-Anzeige im Browser

Jedes Ergebnis wird sofort an alle offenen Browser geschickt (WebSocket):

```python
def broadcast(data: dict):
    msg = json.dumps(data)
    for client in state.ws_clients:
        client.send(msg)
```

Der Browser empfängt z.B.:
```json
{
  "erkannt": true,
  "kennzeichen": "WRAB123",
  "konfidenz": 0.87,
  "erlaubt": true,
  "zeitstempel": 1746123456789,
  "confirmed": true
}
```

Und zeigt entsprechend grünes oder rotes Licht an – ohne Seite neu laden.

---

## Gesamtablauf

```
app.py startet
  ├── database.init_db()          → Datenbank bereit
  ├── ocr.init_ocr()              → EasyOCR geladen
  └── ocr.ocr_worker()            → Scanner läuft

Kamera-Stream (camera.py)
  └── requests.get(camera_url)
        └── JPEG aus Datenstrom ausschneiden (FFD8...FFD9)
              ├── state.ocr_frame = bild       → für OCR
              └── yield frame                  → an Browser

OCR-Worker (ocr.py) – läuft in Schleife
  └── preprocess(ocr_frame)       → Graustufen, Größe, Kontrast, Schärfe
        └── readtext(bild)        → EasyOCR erkennt Text
              └── extract_plate() → Wappen entfernen, Format prüfen
                    └── Voting    → oft genug erkannt?
                          └── check_plate()   → in Whitelist?
                                ├── Ja  → toggle_gate → Tor auf + grünes Licht
                                └── Nein → rotes Licht
```
