from flask import Flask, render_template, Response, request, jsonify, redirect, url_for
import cv2
import threading
import time
import database
import markdown
import os

app = Flask(__name__)

# Initialisiert die Datenbank beim Start (erstellt Tabellen, falls nicht vorhanden)
database.init_db()

# Globale Variablen
# URL zum Videostream der ESP32-CAM. Muss angepasst werden, wenn sich die IP ändert.
camera_url = "http://192.168.1.100:81/stream"  
frame = None  # Speichert das aktuelle Bild (Frame) der Kamera für den Zugriff durch verschiedene Threads
lock = threading.Lock()  # Thread-Lock, um gleichzeitigen Zugriff auf die 'frame'-Variable zu verhindern

def capture_frames():
    """
    Diese Funktion läuft in einem separaten Hintergrund-Thread.
    Sie verbindet sich dauerhaft mit dem ESP32-Stream und aktualisiert
    die globale 'frame'-Variable mit dem neuesten Bild.
    """
    global frame
    cap = cv2.VideoCapture(camera_url)
    while True:
        success, img = cap.read()
        if success:
            with lock:
                frame = img  # Aktualisiert das Bild thread-sicher
        else:
            time.sleep(0.1) # Kurze Pause bei Fehler, um CPU zu schonen
            # Versuche die Verbindung wiederherzustellen
            cap.release()
            cap = cv2.VideoCapture(camera_url)

@app.route('/')
def index():
    """Startseite: Zeigt das Dashboard mit dem Video-Stream."""
    return render_template('index.html')

@app.route('/manage')
def manage():
    """Verwaltungsseite: Listet alle gespeicherten Nummernschilder auf."""
    plates = database.get_all_plates()
    return render_template('manage.html', plates=plates)

@app.route('/add_plate', methods=['POST'])
def add_plate_route():
    """API-Endpunkt zum Hinzufügen eines neuen Kennzeichens."""
    plate = request.form.get('plate')
    if plate:
        database.add_plate(plate.upper()) # Speichert Kennzeichen immer in Großbuchstaben
    return redirect(url_for('manage'))

@app.route('/delete_plate', methods=['POST'])
def delete_plate_route():
    """API-Endpunkt zum Löschen eines Kennzeichens."""
    plate_id = request.form.get('plate_id')
    if plate_id:
        database.remove_plate(plate_id)
    return redirect(url_for('manage'))

@app.route('/docs')
def list_docs():
    """Listet alle verfügbaren Dokumentationsdateien auf."""
    docs_path = os.path.join(app.root_path, 'docs')
    files = [f for f in os.listdir(docs_path) if f.endswith('.md')]
    return render_template('docs_list.html', files=files)

@app.route('/docs/<filename>')
def view_doc(filename):
    """Zeigt eine einzelne Dokumentationsdatei an (konvertiert Markdown zu HTML)."""
    docs_path = os.path.join(app.root_path, 'docs')
    filepath = os.path.join(docs_path, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            html_content = markdown.markdown(content)
        return render_template('doc_view.html', content=html_content, title=filename)
    return "Datei nicht gefunden", 404

def generate_frames():
    """
    Generator-Funktion für den Video-Stream.
    Liest kontinuierlich das aktuelle Frame, kodiert es als JPEG
    und sendet es im MJPEG-Format an den Browser.
    """
    global frame
    while True:
        with lock:
            if frame is None:
                continue
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
        
        # Erstellt den Multipart-Stream für den Browser
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """Route für das `img`-Tag im HTML, liefert den MJPEG-Stream."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Startet den Frame-Capture-Thread im Hintergrund
    # (Aktuell auskommentiert, da Kamera-URL noch Platzhalter ist)
    # t = threading.Thread(target=capture_frames)
    # t.daemon = True
    # t.start()
    
    # Startet den Webserver auf Port 5000, erreichbar von allen Netzwerk-Interfaces (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=True)
