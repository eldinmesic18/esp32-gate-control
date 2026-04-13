from flask import Flask, render_template, Response, request, jsonify
from flask_sock import Sock
import cv2
import numpy as np
import requests
import threading
import time
import re
import json
import database
import markdown
import os

app = Flask(__name__)
sock = Sock(app)
database.init_db()

camera_url   = "http://10.109.199.104/stream"
esp32_base_url = camera_url.split("/stream")[0]  # "http://10.109.199.104:81"

# ── Shared state ──────────────────────────────────────────────
ocr_frame      = None
ocr_lock       = threading.Lock()
ocr_reader     = None
scanning       = True   # Ob OCR-Worker aktiv scannt
last_triggered = {}     # plate -> timestamp (Cooldown)
recent_reads   = []     # Letzte N Erkennungen für Abstimmung
VOTE_WINDOW    = 5      # Wie viele Reads gespeichert werden
VOTE_THRESHOLD = 3      # Wie viele gleiche Reads für Bestätigung nötig

# WebSocket-Clients für Live-Push
ws_clients      = []
ws_clients_lock = threading.Lock()

# ── OCR ───────────────────────────────────────────────────────
def init_ocr():
    global ocr_reader
    import easyocr
    print("[OCR] Initialisiere EasyOCR...")
    ocr_reader = easyocr.Reader(['en'], gpu=False)
    print("[OCR] EasyOCR bereit!")

def extract_plate(raw: str) -> str | None:
    """
    Extrahiert ein gültiges Kennzeichen aus dem OCR-Text.
    Das Wappen sitzt immer an Position 3 (Index 2) → wird entfernt.
    """
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())
    if len(text) > 3:
        text = text[:2] + text[3:]  # 3. Zeichen (Wappen) entfernen
    if 5 <= len(text) <= 9 and re.match(r'^[A-Z]{1,3}[A-Z0-9]+$', text):
        return text
    return None

def preprocess(img):
    """Verbessert das Bild für zuverlässigere OCR-Ergebnisse."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Kontrast gleichmäßig erhöhen
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # Leichtes Schärfen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)
    # Skalieren falls Bild zu klein (OCR braucht mind. ~30px Texthöhe)
    h, w = gray.shape
    if w < 800:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    return gray

def run_ocr_on(img):
    """Führt OCR auf vorverarbeitetem Bild aus."""
    if ocr_reader is None or img is None:
        return None
    processed = preprocess(img)
    results = ocr_reader.readtext(processed)
    print(f"[OCR-RAW] {[(t, f'{c:.0%}') for _, t, c in results]}")
    best = None
    for (_, text, conf) in results:
        if conf < 0.4:
            continue
        plate = extract_plate(text)
        if plate is None:
            continue
        if best is None or conf > best[1]:
            best = (plate, conf)
    return best

def broadcast(data: dict):
    """Sendet ein Erkennungsergebnis an alle verbundenen WS-Clients."""
    msg = json.dumps(data)
    with ws_clients_lock:
        dead = []
        for client in ws_clients:
            try:
                client.send(msg)
            except Exception:
                dead.append(client)
        for client in dead:
            ws_clients.remove(client)

def ocr_worker():
    global recent_reads
    while ocr_reader is None:
        time.sleep(0.5)
    print("[OCR] Worker gestartet")
    while True:
        if not scanning:
            time.sleep(0.5)
            continue

        with ocr_lock:
            img = ocr_frame.copy() if ocr_frame is not None else None

        result = run_ocr_on(img)
        now = time.time()

        if result is None:
            recent_reads.clear()
            broadcast({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                       "erlaubt": False, "zeitstempel": now * 1000})
            time.sleep(1)
            continue

        plate, conf = result
        print(f"[OCR] Gelesen: '{plate}' ({conf:.0%})")

        # Abstimmung: letzten VOTE_WINDOW Reads merken
        recent_reads.append(plate)
        if len(recent_reads) > VOTE_WINDOW:
            recent_reads.pop(0)

        votes = recent_reads.count(plate)
        print(f"[OCR] Votes für '{plate}': {votes}/{VOTE_THRESHOLD}")

        # Live-Vorschau im Dashboard anzeigen (noch nicht bestätigt)
        broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                   "erlaubt": False, "zeitstempel": now * 1000, "confirmed": votes >= VOTE_THRESHOLD})

        # Erst ab VOTE_THRESHOLD gleichen Reads auslösen
        if votes >= VOTE_THRESHOLD:
            cooldown_ok = plate not in last_triggered or (now - last_triggered[plate]) > 30
            if cooldown_ok:
                granted = database.check_plate(plate)
                database.log_access(plate, granted, conf)
                recent_reads.clear()  # Reset nach Auslösung
                if granted:
                    last_triggered[plate] = now
                    print(f"[OCR] {plate} — ZUGANG GEWÄHRT ✓")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": True, "zeitstempel": now * 1000, "confirmed": True})
                    try:
                        requests.get(f"{esp32_base_url}/toggle_gate", timeout=3)
                    except Exception as e:
                        print(f"[OCR] Relay-Fehler: {e}")
                else:
                    print(f"[OCR] {plate} — KEIN ZUGANG ✗ (in DB: {database.check_plate(plate)})")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": False, "zeitstempel": now * 1000, "confirmed": True})

        time.sleep(1)

# ── WebSocket ─────────────────────────────────────────────────
@sock.route('/api/recognition/ws')
def recognition_ws(ws):
    with ws_clients_lock:
        ws_clients.append(ws)
    try:
        while True:
            ws.receive(timeout=60)  # Hält die Verbindung offen
    except Exception:
        pass
    finally:
        with ws_clients_lock:
            if ws in ws_clients:
                ws_clients.remove(ws)

# ── Kamera-Routen ─────────────────────────────────────────────
@app.route('/api/camera/stream')
@app.route('/video_feed')
def video_feed():
    def generate():
        global ocr_frame
        buf = bytes()
        try:
            r = requests.get(camera_url, stream=True, timeout=10,
                             headers={'Accept-Encoding': 'identity'})
            for chunk in r.iter_content(chunk_size=4096):
                buf += chunk
                while True:
                    start = buf.find(b'\xff\xd8')
                    if start == -1:
                        break
                    end = buf.find(b'\xff\xd9', start + 2)
                    if end == -1:
                        break
                    jpg = buf[start:end+2]
                    buf = buf[end+2:]
                    with ocr_lock:
                        ocr_frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception as e:
            print(f"[Proxy] Fehler: {e}")
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera/status')
def camera_status():
    with ocr_lock:
        has_frame = ocr_frame is not None
    return jsonify({"online": has_frame})

# ── Platten-Routen ────────────────────────────────────────────
@app.route('/api/plates/', methods=['GET'])
def api_get_plates():
    nur_aktive = request.args.get('nur_aktive', 'false').lower() == 'true'
    plates = database.get_all_plates(nur_aktive=nur_aktive)
    return jsonify([{
        "id":          p["id"],
        "kennzeichen": p["plate_number"],
        "beschreibung": p["beschreibung"],
        "aktiv":       bool(p["aktiv"]),
        "created_at":  p["created_at"],
    } for p in plates])

@app.route('/api/plates/', methods=['POST'])
def api_add_plate():
    data = request.get_json()
    kennzeichen  = (data.get("kennzeichen") or "").upper().strip()
    beschreibung = data.get("beschreibung")
    if not kennzeichen:
        return jsonify({"error": "Kennzeichen fehlt"}), 400
    ok = database.add_plate(kennzeichen, beschreibung)
    if not ok:
        return jsonify({"error": "Bereits vorhanden"}), 409
    return jsonify({"status": "ok"}), 201

@app.route('/api/plates/<int:plate_id>', methods=['PATCH'])
def api_toggle_plate(plate_id):
    data = request.get_json()
    database.set_plate_active(plate_id, data.get("aktiv", True))
    return jsonify({"status": "ok"})

@app.route('/api/plates/<int:plate_id>', methods=['DELETE'])
def api_delete_plate(plate_id):
    database.remove_plate(plate_id)
    return jsonify({"status": "ok"})

@app.route('/api/plates/log/history')
def api_log_history():
    limit = int(request.args.get("limit", 100))
    logs = database.get_recent_logs(limit)
    return jsonify([{
        "kennzeichen": l["plate_number"],
        "erlaubt":     bool(l["access_granted"]),
        "erkannt":     l["plate_number"] is not None,
        "konfidenz":   l["konfidenz"],
        "zeitstempel": l["timestamp"],
    } for l in logs])

# ── Erkennungs-Routen ─────────────────────────────────────────
@app.route('/api/recognition/status')
def recognition_status():
    with ws_clients_lock:
        clients = len(ws_clients)
    return jsonify({
        "scanning":  scanning,
        "clients":   clients,
        "esp32_url": camera_url,
        "ocr_ready": ocr_reader is not None,
    })

@app.route('/api/recognition/scan/start', methods=['POST'])
def scan_start():
    global scanning
    scanning = True
    return jsonify({"status": "ok"})

@app.route('/api/recognition/scan/stop', methods=['POST'])
def scan_stop():
    global scanning
    scanning = False
    return jsonify({"status": "ok"})

@app.route('/api/recognition/scan-once', methods=['POST'])
def scan_once():
    with ocr_lock:
        img = ocr_frame.copy() if ocr_frame is not None else None
    result = run_ocr_on(img)
    now = time.time()
    if result is None:
        return jsonify({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                        "erlaubt": False, "zeitstempel": now * 1000})
    plate, conf = result
    granted = database.check_plate(plate)
    return jsonify({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                    "erlaubt": granted, "zeitstempel": now * 1000})

@app.route('/api/recognition/upload', methods=['POST'])
def upload_recognize():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Keine Datei"}), 400
    img_array = np.frombuffer(file.read(), dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    result = run_ocr_on(img)
    now = time.time()
    if result is None:
        return jsonify({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                        "erlaubt": False, "zeitstempel": now * 1000})
    plate, conf = result
    granted = database.check_plate(plate)
    return jsonify({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                    "erlaubt": granted, "zeitstempel": now * 1000})

# ── Alte Routen (Kompatibilität) ──────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/toggle_gate', methods=['POST'])
def toggle_gate():
    try:
        requests.get(f"{esp32_base_url}/toggle_gate", timeout=3)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/docs')
def list_docs():
    docs_path = os.path.join(app.root_path, 'docs')
    files = [f for f in os.listdir(docs_path) if f.endswith('.md')]
    return render_template('docs_list.html', files=files)

@app.route('/docs/<filename>')
def view_doc(filename):
    docs_path = os.path.join(app.root_path, 'docs')
    filepath = os.path.join(docs_path, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = markdown.markdown(f.read())
        return render_template('doc_view.html', content=html_content, title=filename)
    return "Datei nicht gefunden", 404

# ── Start ─────────────────────────────────────────────────────
if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=init_ocr, daemon=True).start()
        threading.Thread(target=ocr_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
