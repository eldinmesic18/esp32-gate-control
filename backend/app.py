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

# Flask-App erstellen
app = Flask(__name__)

# WebSocket-Unterstützung hinzufügen (für Live-Updates im Browser)
sock = Sock(app)

# Datenbank initialisieren (Tabellen erstellen falls noch nicht vorhanden)
database.init_db()

# Routen aus den einzelnen Modulen registrieren
app.register_blueprint(camera_bp)       # /api/camera/...
app.register_blueprint(plates_bp)       # /api/plates/...
app.register_blueprint(recognition_bp)  # /api/recognition/...


@sock.route('/api/recognition/ws')
def recognition_ws(ws):
    """WebSocket-Verbindung: Browser verbindet sich hier und bekommt live OCR-Ergebnisse."""
    # Neuen Client zur Liste hinzufügen
    with state.ws_clients_lock:
        state.ws_clients.append(ws)
    try:
        # Verbindung offen halten (timeout=60: alle 60s wird ein Ping erwartet)
        while True:
            ws.receive(timeout=60)
    except Exception:
        pass  # Verbindung wurde getrennt
    finally:
        # Client aus der Liste entfernen
        with state.ws_clients_lock:
            if ws in state.ws_clients:
                state.ws_clients.remove(ws)


@app.route('/')
def index():
    """Hauptseite — gibt das Dashboard zurück."""
    return render_template('index.html')


if __name__ == '__main__':
    # WERKZEUG_RUN_MAIN ist nur im Kindprozess des Werkzeug-Reloaders gesetzt.
    # So starten die Hintergrund-Threads nur einmal (nicht doppelt beim Neustart).
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=ocr.init_ocr, daemon=True).start()    # EasyOCR laden
        threading.Thread(target=ocr.ocr_worker, daemon=True).start()  # Scanner starten
    app.run(host='0.0.0.0', port=5000, debug=True)
