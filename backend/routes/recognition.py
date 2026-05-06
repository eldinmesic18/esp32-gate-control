import time
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
import state
import database
import ocr

recognition_bp = Blueprint('recognition', __name__)


@recognition_bp.route('/api/recognition/status')
def status():
    """Gibt den aktuellen Status des Scanners zurück."""
    with state.ws_clients_lock:
        clients = len(state.ws_clients)
    return jsonify({
        'scanning':  state.scanning,          # Läuft der Scanner gerade?
        'clients':   clients,                  # Wie viele Browser sind verbunden?
        'esp32_url': state.camera_url,         # Welche IP wird verwendet?
        'ocr_ready': state.ocr_reader is not None,  # Ist EasyOCR fertig geladen?
    })


@recognition_bp.route('/api/recognition/scan/start', methods=['POST'])
def scan_start():
    """Startet den automatischen Scanner."""
    state.scanning = True
    return jsonify({'status': 'ok'})


@recognition_bp.route('/api/recognition/scan/stop', methods=['POST'])
def scan_stop():
    """Pausiert den automatischen Scanner."""
    state.scanning = False
    return jsonify({'status': 'ok'})


@recognition_bp.route('/api/recognition/scan-once', methods=['POST'])
def scan_once():
    """Führt eine einmalige OCR auf dem aktuellen Frame durch (ohne Voting)."""
    with state.ocr_lock:
        img = state.ocr_frame.copy() if state.ocr_frame is not None else None
    result = ocr.run_ocr_on(img)
    now = time.time()
    if result is None:
        return jsonify({'erkannt': False, 'kennzeichen': None, 'konfidenz': 0,
                        'erlaubt': False, 'zeitstempel': now * 1000})
    plate, conf = result
    granted = database.check_plate(plate)
    return jsonify({'erkannt': True, 'kennzeichen': plate, 'konfidenz': conf,
                    'erlaubt': granted, 'zeitstempel': now * 1000})


@recognition_bp.route('/api/recognition/upload', methods=['POST'])
def upload():
    """Nimmt ein hochgeladenes Bild entgegen und führt OCR darauf durch."""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'Keine Datei'}), 400
    # Bilddatei in ein numpy-Array dekodieren das OpenCV versteht
    img = cv2.imdecode(np.frombuffer(file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
    result = ocr.run_ocr_on(img)
    now = time.time()
    if result is None:
        return jsonify({'erkannt': False, 'kennzeichen': None, 'konfidenz': 0,
                        'erlaubt': False, 'zeitstempel': now * 1000})
    plate, conf = result
    granted = database.check_plate(plate)
    return jsonify({'erkannt': True, 'kennzeichen': plate, 'konfidenz': conf,
                    'erlaubt': granted, 'zeitstempel': now * 1000})
