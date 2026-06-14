import cv2
# cv2 = OpenCV, eine Bibliothek für Bildverarbeitung.
# Wir brauchen sie hier um die empfangenen JPEG-Bytes in ein Bild umzuwandeln
# das Python/NumPy versteht (ein Array aus Pixelwerten).

import numpy as np
# NumPy ist eine Bibliothek für Arrays und Zahlen.
# cv2.imdecode() braucht ein NumPy-Array als Eingabe – deshalb importieren wir es hier.

import requests
# requests ist eine Bibliothek um HTTP-Anfragen zu machen – wie ein Browser in Python.
# Wir benutzen es um den Video-Stream vom ESP32 abzurufen.

from flask import Blueprint, Response
# Blueprint = eine Art "Teil-App" – Routen können in eigene Dateien ausgelagert werden.
# Response = damit können wir eine eigene HTTP-Antwort zusammenbauen (für den Stream).

import state
# Unser eigenes state.py – dort sind die gemeinsamen Variablen wie ocr_frame und ocr_lock.


# Blueprint erstellen – alle Routen in dieser Datei gehören zu "camera"
camera_bp = Blueprint('camera', __name__)


# @camera_bp.route(...) bedeutet: wenn der Browser diese URL aufruft,
# wird die darunter stehende Funktion ausgeführt.
# Wir haben hier zwei URLs die zur selben Funktion führen:
#   /api/camera/stream  – der offizielle API-Pfad
#   /video_feed         – alter Pfad, zur Kompatibilität noch drin
@camera_bp.route('/api/camera/stream')
@camera_bp.route('/video_feed')
def video_feed():
    # Diese Funktion ist ein "Proxy" – sie steht zwischen dem ESP32 und dem Browser.
    # Der Browser fragt hier an, wir fragen beim ESP32 nach, und leiten alles weiter.
    #
    # Warum brauchen wir das?
    # Der Browser kann den ESP32-Stream nicht direkt öffnen (andere Domain, CORS-Probleme).
    # Außerdem wollen wir nebenbei jeden Frame für die OCR abgreifen.
    # ESP32 → Proxy → Browser
    # der esp32 kann das Bild nur an einen Empfänger schicken, aber wir wollen es gleichzeitig an den 
    # Browser und an den OCR-Worker schicken.
    # deswegen fungiert diese Funktion als Proxy: sie empfängt die Daten vom ESP32, speichert sie in state.ocr_frame
    # und leitet sie dann an den Browser weiter.

    def generate():
        # generate() ist eine sogenannte "Generator-Funktion".
        # Statt alles auf einmal zurückzugeben, liefert sie mit "yield" Stück für Stück.
        # Das ist wichtig für Streams – der Browser bekommt laufend neue Bilder.

        # buf = Puffer. Hier sammeln wir die rohen Bytes die vom ESP32 ankommen,
        # bis wir ein vollständiges JPEG-Bild zusammengesetzt haben.
        buf = bytes()

        try:
            # requests.get() öffnet eine Verbindung zur ESP32-URL.
            # stream=True bedeutet: nicht alles auf einmal herunterladen,
            # sondern die Daten Stück für Stück (chunk) empfangen – der Stream läuft ja ewig.
            # timeout=10 bedeutet: wenn 10 Sekunden lang nichts kommt → Fehler.
            # Accept-Encoding: identity bedeutet: keine Komprimierung – wir wollen die Rohdaten.
            r = requests.get(state.camera_url, stream=True, timeout=10,
                             headers={'Accept-Encoding': 'identity'})

            # iter_content(chunk_size=4096) liefert die Daten in 4096-Byte-Häppchen.
            # 4096 Bytes = 4 Kilobyte – ein typischer Wert für netzwerk-effizientes Lesen.
            for chunk in r.iter_content(chunk_size=4096):

                # Neues Häppchen zum Puffer hinzufügen
                buf += chunk

                # Jetzt schauen wir ob im Puffer schon ein vollständiges JPEG-Bild steckt.
                # JPEG-Bilder haben immer:
                #   Anfang: die Bytes FF D8  (in Python: b'\xff\xd8')
                #   Ende:   die Bytes FF D9  (in Python: b'\xff\xd9')
                # Wir suchen diese Markierungen um das Bild aus dem Datenstrom auszuschneiden.
                while True:

                    # buf.find() sucht nach einem bestimmten Byte-Muster im Puffer.
                    # Gibt die Position zurück wo es gefunden wurde, oder -1 wenn nicht.
                    start = buf.find(b'\xff\xd8')  # JPEG-Startmarkierung suchen
                    if start == -1:
                        break  # Kein JPEG-Anfang gefunden → mehr Daten abwarten

                    end = buf.find(b'\xff\xd9', start + 2)  # JPEG-Ende suchen (nach dem Anfang)
                    if end == -1:
                        break  # Ende noch nicht angekommen → mehr Daten abwarten

                    # Wir haben einen vollständigen JPEG-Frame gefunden!
                    # buf[start:end+2] schneidet genau diese Bytes aus dem Puffer aus.
                    # +2 weil das Ende-Marker selbst 2 Bytes lang ist (FF D9).
                    jpg = buf[start:end + 2]

                    # Den verarbeiteten Teil aus dem Puffer entfernen
                    # (der Rest gehört zum nächsten Bild)
                    buf = buf[end + 2:]

                    # Das JPEG-Bild für den OCR-Worker in state.ocr_frame speichern.
                    # with state.ocr_lock: bedeutet – Lock aktivieren.
                    # Ein Lock ist wie eine Türe: nur einer darf gleichzeitig rein.
                    # Ohne Lock könnten Proxy und OCR-Worker gleichzeitig auf ocr_frame zugreifen
                    # und das würde zu einem Fehler/Absturz führen.
                    with state.ocr_lock:
                        # cv2.imdecode() wandelt die rohen JPEG-Bytes in ein Pixel-Array um
                        # das OpenCV und EasyOCR verarbeiten können.
                        # np.frombuffer() macht aus den Bytes zuerst ein NumPy-Array –
                        # das braucht imdecode() als Eingabe.
                        state.ocr_frame = cv2.imdecode(
                            np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                    # Das JPEG-Bild an den Browser schicken.
                    # yield gibt das Bild zurück OHNE die Funktion zu beenden –
                    # beim nächsten Aufruf macht sie genau hier weiter.
                    # Das Format ist MJPEG: jedes Bild wird mit einem Trennzeichen (--frame)
                    # und einem Header (Content-Type) verpackt.
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')

        except Exception as e:
            # Falls die Verbindung zum ESP32 abbricht (z.B. WLAN-Ausfall),
            # wird der Fehler gedruckt aber das Programm läuft weiter.
            print(f"[Proxy] Fehler: {e}")

    # Response() verpackt unsere generate()-Funktion als HTTP-Antwort.
    # mimetype='multipart/x-mixed-replace' sagt dem Browser:
    # "Das ist ein kontinuierlicher Stream, ersetze das Bild immer mit dem nächsten."
    # boundary=frame ist das Trennzeichen zwischen den einzelnen Bildern.
    # macht die generate()-Funktion zu einem Live-Stream für den Browser
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@camera_bp.route('/api/camera/status')
def camera_status():
    # Diese Route gibt zurück ob die Kamera online ist.
    # Wir prüfen einfach: hat ocr_frame schon einen Wert?
    # Wenn ja → mindestens ein Bild wurde empfangen → Kamera ist online.
    # Wenn nein (None) → noch kein Bild angekommen → offline.
    with state.ocr_lock:
        online = state.ocr_frame is not None  # True oder False
    return {'online': online}
