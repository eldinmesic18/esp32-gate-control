# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Install dependencies:**
```bash
pip install -r backend/requirements.txt
```

**Run the Flask backend:**
```bash
cd backend
python app.py
```

The server starts at `http://localhost:5000`. The camera capture thread only starts when `WERKZEUG_RUN_MAIN=true` (i.e., after Werkzeug's reloader forks), so in debug mode the background thread won't start in the parent process — this is intentional.

**Flash ESP32 firmware:**
Open `esp32/CameraWebServer/CameraWebServer.ino` in Arduino IDE with the ESP32 board package installed.

## Architecture

This is a two-component system:

### Backend (`backend/`)
- **`app.py`**: Flask app with a background thread (`capture_frames`) that continuously reads MJPEG frames from the ESP32 into a global `frame` variable protected by a `threading.Lock`. The `/video_feed` route re-streams these frames to the browser as MJPEG. All plate CRUD operations redirect back to `/manage`.
- **`database.py`**: Thin SQLite wrapper (no ORM). DB file `plates.db` is created in the working directory from which `app.py` is run (project root when run via `cd backend && python app.py` — note: `sqlite3.connect("plates.db")` uses relative path, so always run from `backend/`). Two tables: `plates` (allowlist) and `logs` (access history).
- **`templates/`**: Jinja2 templates styled with Tailwind CSS via CDN. `index.html` = dashboard with live stream + access log. `manage.html` = plate CRUD. `docs_list.html` / `doc_view.html` = Markdown docs viewer.
- **`docs/`**: Markdown documentation files rendered at `/docs/<filename>`.

### ESP32 Firmware (`esp32/CameraWebServer/`)
- **`CameraWebServer.ino`**: Sets up the OV2640 camera (AI Thinker model), connects to WiFi, and calls `startCameraServer()`. Relay is on GPIO 14; `RELAY_ACTIVE_HIGH` controls polarity.
- **`app_httpd.cpp`**: HTTP server handlers — `/stream` (MJPEG) and `/relay` (gate trigger). Exposes `RELAY_PIN` and `RELAY_ACTIVE_HIGH` as `extern` from the `.ino` file.
- **`camera_pins.h`**: GPIO pin definitions for the AI Thinker module.

### Key configuration points
- **ESP32 IP**: `camera_url` in `backend/app.py` line 16 must match the ESP32's actual IP. The ESP32 prints its IP over Serial on boot. Stream endpoint is `/stream` (no port suffix for the AI Thinker default server on port 80).
- **WiFi credentials**: Hardcoded in `esp32/CameraWebServer/CameraWebServer.ino` lines 7–8.
- **Relay logic**: `RELAY_ACTIVE_HIGH = true` means HIGH signal activates the relay. Set to `false` for low-trigger relay modules.

### EasyOCR integration status
EasyOCR is in `requirements.txt` but **not yet wired into `app.py`**. The OCR pipeline (capture frame → detect plate region → read text → check against DB → trigger relay) is planned but not implemented.
