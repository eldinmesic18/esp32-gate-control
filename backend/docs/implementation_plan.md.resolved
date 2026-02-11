# Implementierungsplan: ESP32-CAM Nummernschilderkennung mit Webschnittstelle

## Zielbeschreibung
Entwicklung eines Systems zur automatischen Steuerung eines Garagentors basierend auf Nummernschilderkennung (ALPR/ANPR). Das System besteht aus einem ESP32-CAM Modul und einem zentralen Server (PC/Raspberry Pi), der die Bildverarbeitung und Webverwaltung übernimmt.

## Architekturübersicht

### Komponenten
1.  **ESP32-CAM Modul**:
    -   Fungiert als IP-Kamera (MJPEG Stream).
    -   Steuert das Relais für das Garagentor über einen GPIO-Pin.
    -   Bietet HTTP-Endpunkte für Videostream und Torsteuerung.

2.  **Backend-Server (Python)**:
    -   Hostet die Web-Applikation.
    -   Verarbeitet den Videostream der ESP32-CAM.
    -   Führt die Nummernschilderkennung (OCR) durch (z.B. mit EasyOCR oder OpenALPR).
    -   Verwaltet die Datenbank der zugelassenen Kennzeichen.
    -   Sendet den Öffnungsbefehl an den ESP32, wenn ein Kennzeichen erkannt wird.

3.  **Web-Interface (Frontend)**:
    -   Dashboard mit Live-Ansicht der Kamera.
    -   Verwaltung der Datenbank (Hinzufügen/Löschen von Kennzeichen).
    -   Protokollierung der Zugriffe (Logs).
    -   Manueller Öffnungs-Button.

### Workflow
1.  ESP32 streamt Video an den Server.
2.  Server analysiert Frames in regelmäßigen Abständen (z.B. 1-2 FPS oder bei Bewegung).
3.  Server extrahiert Text (Kennzeichen).
4.  Server prüft Kennzeichen gegen SQLite-Datenbank.
5.  Bei Übereinstimmung: Server sendet HTTP-Request an ESP32 (`/toggle_gate`).
6.  ESP32 aktiviert Relais -> Tor öffnet.

## Technologie-Stack
-   **Hardware**: ESP32-CAM, Relais-Modul, Server (PC/Laptop/Raspberry Pi).
-   **Firmware**: Arduino/C++ für ESP32.
-   **Backend**: Python (Flask oder FastAPI).
-   **OCR**: EasyOCR oder Pytesseract.
-   **Datenbank**: SQLite.
-   **Frontend**: HTML, CSS, JavaScript (TailwindCSS empfohlen für modernes UI).

## Schritte zur Umsetzung

### 1. ESP32-Firmware
-   Einrichten des Webservers für Video-Streaming.
-   Implementieren der `/control`-Route für das Relais.
-   WLAN-Verbindung konfigurieren.

### 2. Python Backend & OCR
-   Aufsetzen des Flask-Servers.
-   Integration von OpenCV zum Abgreifen des Streams.
-   Implementierung der OCR-Pipeline.
-   Datenbankmodell für `KnownPlates` und `AccessLogs` erstellen.

### 3. Web-App Entwicklung
-   Route für Video-Stream-Proxy (Server leitet ESP32-Stream an Browser weiter oder Browser greift direkt zu).
-   Interface zur Verwaltung der Kennzeichen-Liste.
-   Styling des Dashboards.

### 4. Integration & Test
-   Kalibrierung der Kamera und OCR-Parameter.
-   Test der Reaktionszeiten und Erkennungsgenauigkeit.

## Offene Punkte / Fragen an den User
-   Soll der Server (Python) auf einem PC laufen, oder soll alles (sehr limitiert) auf dem ESP32 laufen? (Empfehlung: PC/Pi für zuverlässige OCR).
-   Welches Relais wird verwendet (Low/High Trigger)?
