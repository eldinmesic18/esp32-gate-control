# ESP32-CAM Verkabelung & Einrichtung

Da du dir ein neues Modul kaufst, hier die wichtigsten Infos zur Hardware.

## 1. Verkabelung (Wiring)

Du brauchst ein **5V Relais-Modul** für das Garagentor.

### ESP32-CAM <-> Relais
*   **VCC** -> 5V (vom ESP32 oder extern)
*   **GND** -> GND
*   **IN** -> **GPIO 14** (Das ist im Code voreingestellt)

### Relais <-> Garagentor
*   **COM** (Common) -> Ein Pin vom Garagentor-Taster
*   **NO** (Normally Open) -> Der andere Pin vom Garagentor-Taster
*   *(Wenn das Relais schaltet, werden COM und NO verbunden, wie ein Tasterdruck)*

### Stromversorgung
*   Versorge den ESP32-CAM stabil mit **5V** am 5V-Pin. USB-Ports am PC reichen oft nicht für WiFi + Kamera + Blitzlicht. Ein externes 5V/2A Netzteil ist empfohlen.

---

## 2. Code Anpassungen

Wenn du das neue Modul hast, musst du nur 2 Dinge im Code ändern:

### A. Im ESP32 Code (`esp32/CameraWebServer.ino`)
1.  **WLAN-Daten**:
    ```cpp
    const char* ssid = "DEIN_WLAN_NAME";
    const char* password = "DEIN_WLAN_PASSWORT";
    ```
2.  **Relais-Logik (Optional)**:
    Falls dein Relais "Low Trigger" ist (schaltet bei GND), ändere:
    ```cpp
    #define RELAY_ACTIVE_HIGH false 
    ```

### B. Im Python Backend (`backend/app.py`)
1.  **IP-Adresse**:
    Sobald der ESP32 im WLAN ist, zeigt er dir im "Serial Monitor" (Arduino IDE) eine IP-Adresse an (z.B. `192.168.178.45`).
    Diese trägst du in `backend/app.py` ein:
    ```python
    camera_url = "http://192.168.178.45:81/stream"
    ```

## 3. Datenbank-Problem
Die Datenbank-Funktion ("Manage Database") war noch nicht fertig programmiert. Ich füge das jetzt für dich hinzu!
