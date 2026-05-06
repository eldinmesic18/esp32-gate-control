"""
Geteilter globaler State zwischen allen Modulen.
"""

import threading

# ── Kamera ────────────────────────────────────────────────────────────────────

# Vollständige URL zum MJPEG-Stream des ESP32
camera_url = "http://10.79.59.104/stream"

# Basis-URL des ESP32 (ohne /stream) — wird für den Relay-Aufruf verwendet
esp32_base_url = camera_url.split("/stream")[0]

# ── Aktueller Frame ───────────────────────────────────────────────────────────

# Das zuletzt empfangene Kamerabild (numpy array).
# Wird vom Video-Proxy (camera.py) geschrieben und vom OCR-Worker (ocr.py) gelesen.
ocr_frame = None

# Lock verhindert, dass Proxy und OCR-Worker gleichzeitig auf ocr_frame zugreifen
# (würde sonst zu einem Absturz führen)
ocr_lock = threading.Lock()

# ── OCR ───────────────────────────────────────────────────────────────────────

# Das geladene EasyOCR-Modell. Ist None solange es noch initialisiert wird.
ocr_reader = None

# Ob der OCR-Worker aktiv scannt. Kann über die API gestartet/gestoppt werden.
scanning = True

# Speichert wann ein Kennzeichen zuletzt das Tor ausgelöst hat.
# Format: { "WRAB123": 1234567890.0 }
# Verhindert dass dasselbe Kennzeichen innerhalb von 30 Sekunden zweimal auslöst.
last_triggered = {}

# ── Voting-System ─────────────────────────────────────────────────────────────

# Puffer der letzten Lesungen. Format: [(kennzeichen, zeitstempel), ...]
# Einträge älter als VOTE_WINDOW_SECS werden automatisch verworfen.
recent_reads = []

# Wie lange eine Lesung gültig bleibt (in Sekunden)
VOTE_WINDOW_SECS = 6

# Wie viele gleiche Lesungen im Zeitfenster nötig sind um das Tor zu öffnen
VOTE_THRESHOLD = 1

# ── WebSocket-Clients ─────────────────────────────────────────────────────────

# Liste aller Browser die gerade die Seite offen haben.
# Jeder Eintrag ist eine offene WebSocket-Verbindung.
ws_clients = []

# Lock für den gleichzeitigen Zugriff auf ws_clients
ws_clients_lock = threading.Lock()
