"""
Kennzeichenerkennung: Initialisierung, Bildverarbeitung, OCR-Worker.
"""
import re
import json
import time
import threading
import cv2
import numpy as np
import requests
import state
import database


def init_ocr():
    import easyocr
    print("[OCR] Initialisiere EasyOCR...")
    state.ocr_reader = easyocr.Reader(['en'], gpu=False)
    print("[OCR] EasyOCR bereit!")


def broadcast(data: dict):
    """Sendet Erkennungsergebnis an alle WebSocket-Clients."""
    msg = json.dumps(data)
    with state.ws_clients_lock:
        dead = []
        for client in state.ws_clients:
            try:
                client.send(msg)
            except Exception:
                dead.append(client)
        for client in dead:
            state.ws_clients.remove(client)


def preprocess(img):
    """Verbessert Bildqualität für stabilere OCR-Ergebnisse."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)
    h, w = gray.shape
    if w < 800:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    return gray


def extract_plate(raw: str) -> str | None:
    """
    Bereinigt OCR-Text zu einem Kennzeichen.
    Entfernt das 3. Zeichen (Index 2) — dort sitzt das Wappen.
    Gültig: beginnt mit 1-3 Buchstaben, gesamt 5-9 Zeichen.
    """
    text = re.sub(r'[^A-Z0-9]', '', raw.upper())
    if len(text) > 3:
        text = text[:2] + text[3:]  # Wappen (3. Zeichen) entfernen
    if 5 <= len(text) <= 9 and re.match(r'^[A-Z]{1,3}[A-Z0-9]+$', text):
        return text
    return None


def run_ocr_on(img) -> tuple | None:
    """Führt OCR auf vorverarbeitetem Bild aus. Gibt (plate, konfidenz) oder None zurück."""
    if state.ocr_reader is None or img is None:
        return None
    processed = preprocess(img)
    results = state.ocr_reader.readtext(processed)
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


def ocr_worker():
    """Hintergrund-Thread: liest Frames, erkennt Kennzeichen, löst Relais aus."""
    while state.ocr_reader is None:
        time.sleep(0.5)
    print("[OCR] Worker gestartet")

    while True:
        if not state.scanning:
            time.sleep(0.5)
            continue

        with state.ocr_lock:
            img = state.ocr_frame.copy() if state.ocr_frame is not None else None

        result = run_ocr_on(img)
        now = time.time()

        if result is None:
            state.recent_reads.clear()
            broadcast({"erkannt": False, "kennzeichen": None, "konfidenz": 0,
                       "erlaubt": False, "zeitstempel": now * 1000})
            time.sleep(1)
            continue

        plate, conf = result
        print(f"[OCR] Gelesen: '{plate}' ({conf:.0%})")

        state.recent_reads.append(plate)
        if len(state.recent_reads) > state.VOTE_WINDOW:
            state.recent_reads.pop(0)

        votes = state.recent_reads.count(plate)
        print(f"[OCR] Votes: {votes}/{state.VOTE_THRESHOLD}")

        broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                   "erlaubt": False, "zeitstempel": now * 1000,
                   "confirmed": votes >= state.VOTE_THRESHOLD})

        if votes >= state.VOTE_THRESHOLD:
            cooldown_ok = (plate not in state.last_triggered or
                           (now - state.last_triggered[plate]) > 30)
            if cooldown_ok:
                granted = database.check_plate(plate)
                database.log_access(plate, granted, conf)
                state.recent_reads.clear()
                if granted:
                    state.last_triggered[plate] = now
                    print(f"[OCR] {plate} — ZUGANG GEWÄHRT ✓")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": True, "zeitstempel": now * 1000, "confirmed": True})
                    try:
                        requests.get(f"{state.esp32_base_url}/toggle_gate", timeout=3)
                    except Exception as e:
                        print(f"[OCR] Relay-Fehler: {e}")
                else:
                    print(f"[OCR] {plate} — KEIN ZUGANG ✗")
                    broadcast({"erkannt": True, "kennzeichen": plate, "konfidenz": conf,
                               "erlaubt": False, "zeitstempel": now * 1000, "confirmed": True})

        time.sleep(1)
