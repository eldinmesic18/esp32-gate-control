"""
Geteilter globaler State zwischen allen Modulen.
"""
import threading

# Kamera
camera_url    = "http://10.109.199.104/stream"
esp32_base_url = camera_url.split("/stream")[0]

# Aktueller Frame (wird vom Video-Proxy gesetzt, vom OCR-Worker gelesen)
ocr_frame = None
ocr_lock  = threading.Lock()

# OCR
ocr_reader     = None
scanning       = True
last_triggered = {}    # plate -> timestamp (Cooldown 30s)
recent_reads   = []    # Abstimmungs-Buffer
VOTE_WINDOW    = 5
VOTE_THRESHOLD = 3

# WebSocket-Clients
ws_clients      = []
ws_clients_lock = threading.Lock()
