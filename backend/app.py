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

# Flask-App erstellen — das ist der Webserver der alle HTTP-Anfragen entgegennimmt
app = Flask(__name__)

# WebSocket-Unterstützung hinzufügen.
# Normale HTTP-Verbindungen sind "einmalig" — Browser fragt, Server antwortet, fertig.
# WebSocket ist eine dauerhafte Verbindung — der Server kann jederzeit von sich aus
# Daten schicken. Das brauchen wir damit das Dashboard live aktualisiert wird.
sock = Sock(app)

# Datenbank initialisieren — erstellt plates.db und die Tabellen falls noch nicht vorhanden
database.init_db()

# Blueprints registrieren — die Routen aus den einzelnen Dateien in die App einbinden.
# Ohne diese Zeilen würde Flask die URLs aus camera.py, plates.py, recognition.py nicht kennen.
app.register_blueprint(camera_bp)       # /api/camera/...
app.register_blueprint(plates_bp)       # /api/plates/...
app.register_blueprint(recognition_bp)  # /api/recognition/...


# WebSocket-Route: Browser verbindet sich hier beim Öffnen des Dashboards.
# Ab diesem Moment ist der Browser in state.ws_clients — er bekommt alle OCR-Ergebnisse live.
@sock.route('/api/recognition/ws')
def recognition_ws(ws):
    # Neuen Browser zur Liste hinzufügen
    with state.ws_clients_lock:
        state.ws_clients.append(ws)
    try:
        # Verbindung offen halten — timeout=60 bedeutet alle 60s wird ein Ping erwartet.
        # Solange der Browser die Seite offen hat, bleibt diese Schleife aktiv.
        while True:
            ws.receive(timeout=60)
    except Exception:
        pass  # Browser hat die Seite geschlossen → Verbindung getrennt
    finally:
        # Browser aus der Liste entfernen damit broadcast() ihn nicht mehr anschreibt
        with state.ws_clients_lock:
            if ws in state.ws_clients:
                state.ws_clients.remove(ws)


# Hauptseite — gibt das Dashboard zurück wenn jemand localhost:5000 aufruft
@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    # Werkzeug (der eingebaute Flask-Entwicklungsserver) startet sich selbst zweimal:
    # einmal als "Elternprozess" der auf Dateiänderungen wartet (Auto-Reload),
    # und einmal als "Kindprozess" der eigentlich die Anfragen bearbeitet.
    # WERKZEUG_RUN_MAIN ist nur im Kindprozess gesetzt — so starten die Threads
    # nur einmal und nicht doppelt.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=ocr.init_ocr, daemon=True).start()    # EasyOCR laden
        threading.Thread(target=ocr.ocr_worker, daemon=True).start()  # Scanner starten
    app.run(host='0.0.0.0', port=5000, debug=True)
