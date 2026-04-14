"""
Einstiegspunkt der Flask-Anwendung.
Registriert Blueprints, startet Hintergrund-Threads.
"""
import os
import threading
from flask import Flask, render_template
from flask_sock import Sock
import database
import state
import ocr
from routes.camera import camera_bp
from routes.plates import plates_bp
from routes.recognition import recognition_bp

app = Flask(__name__)
sock = Sock(app)
database.init_db()

# Blueprints registrieren
app.register_blueprint(camera_bp)
app.register_blueprint(plates_bp)
app.register_blueprint(recognition_bp)


# ── WebSocket ─────────────────────────────────────────────────
@sock.route('/api/recognition/ws')
def recognition_ws(ws):
    with state.ws_clients_lock:
        state.ws_clients.append(ws)
    try:
        while True:
            ws.receive(timeout=60)
    except Exception:
        pass
    finally:
        with state.ws_clients_lock:
            if ws in state.ws_clients:
                state.ws_clients.remove(ws)


# ── Seiten ────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


# ── Start ─────────────────────────────────────────────────────
if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=ocr.init_ocr, daemon=True).start()
        threading.Thread(target=ocr.ocr_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
