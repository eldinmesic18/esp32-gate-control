import cv2
import numpy as np
import requests
from flask import Blueprint, Response
import state

camera_bp = Blueprint('camera', __name__)


@camera_bp.route('/api/camera/stream')
@camera_bp.route('/video_feed')
def video_feed():
    """Leitet den MJPEG-Stream des ESP32 an den Browser weiter.

    Der ESP32 sendet einen kontinuierlichen MJPEG-Stream (viele JPEGs hintereinander).
    Diese Funktion empfängt die Rohdaten, sucht darin einzelne JPEG-Bilder
    (erkennbar an den Markierungen FFD8 = Start, FFD9 = Ende) und schickt
    sie Frame für Frame an den Browser weiter. Nebenbei wird jeder Frame
    in state.ocr_frame gespeichert, damit der OCR-Worker ihn lesen kann.
    """
    def generate():
        buf = bytes()  # Puffer für empfangene Rohdaten
        try:
            # Verbindung zum ESP32-Stream öffnen (stream=True = chunksweise lesen)
            r = requests.get(state.camera_url, stream=True, timeout=10,
                             headers={'Accept-Encoding': 'identity'})
            for chunk in r.iter_content(chunk_size=4096):
                buf += chunk

                # Solange vollständige JPEGs im Puffer sind → extrahieren und senden
                while True:
                    start = buf.find(b'\xff\xd8')  # JPEG-Start-Marker
                    if start == -1:
                        break
                    end = buf.find(b'\xff\xd9', start + 2)  # JPEG-End-Marker
                    if end == -1:
                        break  # Noch kein vollständiges Bild → mehr Daten abwarten

                    jpg = buf[start:end + 2]   # Einzelnes JPEG-Bild ausschneiden
                    buf = buf[end + 2:]        # Verarbeiteten Teil aus dem Puffer entfernen

                    # Frame für OCR speichern (Lock wegen gleichzeitigem Zugriff)
                    with state.ocr_lock:
                        state.ocr_frame = cv2.imdecode(
                            np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                    # Frame im MJPEG-Format an den Browser schicken
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception as e:
            print(f"[Proxy] Fehler: {e}")

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@camera_bp.route('/api/camera/status')
def camera_status():
    """Gibt zurück ob die Kamera online ist (hat sie schon einen Frame geliefert?)."""
    with state.ocr_lock:
        online = state.ocr_frame is not None
    return {'online': online}
