"""
Kamera-Routen: Video-Stream und Status.
"""
import cv2
import numpy as np
import requests
from flask import Blueprint, Response
import state

camera_bp = Blueprint('camera', __name__)


@camera_bp.route('/api/camera/stream')
@camera_bp.route('/video_feed')
def video_feed():
    """Proxyt den ESP32-MJPEG-Stream und extrahiert nebenbei Frames für OCR."""
    def generate():
        buf = bytes()
        try:
            r = requests.get(state.camera_url, stream=True, timeout=10,
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
                    with state.ocr_lock:
                        state.ocr_frame = cv2.imdecode(
                            np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception as e:
            print(f"[Proxy] Fehler: {e}")
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@camera_bp.route('/api/camera/status')
def camera_status():
    with state.ocr_lock:
        online = state.ocr_frame is not None
    return {'online': online}
