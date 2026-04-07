from flask import Flask, render_template, Response, request, jsonify, redirect, url_for
import cv2
import numpy as np
import requests
import threading
import time
import re
import database
import markdown
import os

app = Flask(__name__)
database.init_db()

camera_url = "http://10.109.199.104:81/stream"
esp32_base_url = camera_url.rsplit('/', 1)[0]  # "http://10.54.141.104"

# Geteilter Frame zwischen Proxy und OCR-Thread
ocr_frame = None
ocr_lock = threading.Lock()

# OCR Reader (wird im Hintergrund geladen)
ocr_reader = None
last_triggered = {}  # plate -> timestamp, Cooldown gegen Mehrfach-Trigger

def init_ocr():
    global ocr_reader
    import easyocr
    print("[OCR] Initialisiere EasyOCR (kann etwas dauern)...")
    ocr_reader = easyocr.Reader(['en'], gpu=False)
    print("[OCR] EasyOCR bereit!")

def ocr_worker():
    while ocr_reader is None:
        time.sleep(0.5)
    print("[OCR] Worker gestartet")
    while True:
        with ocr_lock:
            img = ocr_frame.copy() if ocr_frame is not None else None

        if img is not None:
            try:
                results = ocr_reader.readtext(img)
                for (_, text, confidence) in results:
                    if confidence < 0.5:
                        continue
                    # Nur Buchstaben und Zahlen behalten, Großbuchstaben
                    plate = re.sub(r'[^A-Z0-9]', '', text.upper())
                    if len(plate) < 4:
                        continue
                    now = time.time()
                    cooldown_ok = plate not in last_triggered or (now - last_triggered[plate]) > 30
                    if not cooldown_ok:
                        continue
                    granted = database.check_plate(plate)
                    database.log_access(plate, granted)
                    if granted:
                        print(f"[OCR] Kennzeichen erkannt: {plate} — ZUGANG GEWÄHRT")
                        last_triggered[plate] = now
                        try:
                            requests.get(f"{esp32_base_url}/toggle_gate", timeout=3)
                            print("[OCR] Relais ausgelöst (LED an)")
                        except Exception as e:
                            print(f"[OCR] Relais-Fehler: {e}")
                    else:
                        print(f"[OCR] Kennzeichen erkannt: {plate} — KEIN ZUGANG")
            except Exception as e:
                print(f"[OCR] Fehler: {e}")

        time.sleep(2)  # Alle 2 Sekunden ein Frame auswerten


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage')
def manage():
    plates = database.get_all_plates()
    return render_template('manage.html', plates=plates)

@app.route('/add_plate', methods=['POST'])
def add_plate_route():
    plate = request.form.get('plate')
    if plate:
        database.add_plate(plate.upper())
    return redirect(url_for('manage'))

@app.route('/delete_plate', methods=['POST'])
def delete_plate_route():
    plate_id = request.form.get('plate_id')
    if plate_id:
        database.remove_plate(plate_id)
    return redirect(url_for('manage'))

@app.route('/toggle_gate', methods=['POST'])
def toggle_gate():
    """Manuelles Öffnen per Dashboard-Button."""
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

@app.route('/video_feed')
def video_feed():
    """Liest ESP32-MJPEG-Stream, extrahiert Frames und sendet eigenen MJPEG-Stream."""
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


if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=init_ocr, daemon=True).start()
        threading.Thread(target=ocr_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
