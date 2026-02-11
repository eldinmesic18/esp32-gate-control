# Smart Gate Control System

Ein intelligentes System zur Steuerung eines Garagentors mittels Nummernschilderkennung (ALPR) und Web-Interface.

## 🌟 Funktionen

Das System bietet folgende Hauptfunktionen:

- **📸 Live Video-Stream**:
  - Echtzeit-Übertragung vom ESP32-CAM Modul.
  - Anzeige direkt im Web-Browser.

- **🚗 Automatische Nummernschilderkennung (ALPR)**:
  - Erkennt Nummernschilder im Video-Stream automatisch.
  - Gleicht erkannte Kennzeichen mit einer Datenbank (Allowlist) ab.
  - Öffnet das Tor automatisch bei Übereinstimmung.

- **💻 Web-Dashboard**:
  - Übersichtliches Dashboard zur Kontrolle des Systems.
  - Anzeige des Live-Bildes inkl. Status (Online/Offline).
  - Protokoll der letzten Zugriffe (Wer hat wann das Tor geöffnet?).

- **✅ Verwaltungs-Interface**:
  - Einfaches Hinzufügen und Löschen von berechtigten Kennzeichen.
  - Verwaltung der Datenbank über die Weboberfläche.

- **🔘 Manuelle Steuerung**:
  - "Open Gate" Button im Dashboard, um das Tor manuell zu öffnen.

- **📚 Dokumentation**:
  - Integrierter Dokumentations-Viewer für Projektinfos und Anleitungen.

## 🛠 Technologien

Das Projekt wurde mit folgenden Technologien umgesetzt:

### Hardware & Firmware
- **ESP32-CAM**: Kostengünstiges WLAN-Video-Modul.
- **C++ / Arduino**: Firmware für den ESP32 (Webserver, Kamera-Streaming, GPIO-Steuerung).

### Backend (Server)
- **Python**: Hauptprogrammiersprache für die Logik.
- **Flask**: Web-Framework für das Dashboard und die API.
- **OpenCV**: Bibliothek zur Bildverarbeitung und Erfassung des Video-Streams.
- **EasyOCR**: Machine-Learning-Modell zur Texterkennung (OCR) auf Bildern.
- **SQLite**: Leichte, dateibasierte Datenbank für Kennzeichen und Logs.
- **Threading**: Zur parallelen Verarbeitung von Video-Stream und Web-Anfragen.

### Frontend (Benutzeroberfläche)
- **HTML5**: Struktur der Webseiten.
- **Tailwind CSS**: Modernes Utility-First CSS-Framework für das Styling (über CDN eingebunden).
- **JavaScript**: Für interaktive Elemente.
- **Google Fonts**: Typografie (Schriftart "Inter").
- **Jinja2**: Templating-Engine von Flask.

## 🚀 Schnellstart

1. **Hardware einrichten**: ESP32-CAM flashen und verkabeln.
2. **Abhängigkeiten installieren**:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. **Server starten**:
   ```bash
   cd backend
   python app.py
   ```
4. **Dashboard öffnen**: Browser auf `http://localhost:5000` steuern.

---
*Erstellt für das ESP32 Gate Control Projekt.*
