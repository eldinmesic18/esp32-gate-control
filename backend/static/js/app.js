/* === Konfiguration === */
const API_BASE = window.location.origin;
const WS_URL   = `ws://${window.location.host}/api/recognition/ws`;

/* === State === */
let ws = null;
let scanning = false;

/* === DOM-Referenzen === */
const statusLight    = document.getElementById("statusLight");
const statusLabel    = document.getElementById("statusLabel");
const plateText      = document.getElementById("plateText");
const confidenceText = document.getElementById("confidenceText");
const lastUpdate     = document.getElementById("lastUpdate");
const cameraFeed     = document.getElementById("cameraFeed");
const cameraOverlay  = document.getElementById("cameraOverlay");
const connectionDot  = document.querySelector(".dot");
const connectionText = document.getElementById("connectionText");

/* =====================
   KAMERA
   ===================== */
function startStream() {
    cameraFeed.src = `${API_BASE}/api/camera/stream`;
}

cameraFeed.addEventListener("load",  () => cameraOverlay.classList.remove("visible"));
cameraFeed.addEventListener("error", () => {
    cameraOverlay.classList.add("visible");
    setTimeout(startStream, 3000);
});

/* =====================
   WEBSOCKET
   ===================== */
function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    setConnectionStatus("connecting");
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setConnectionStatus("online");
    };

    ws.onmessage = (event) => {
        try {
            const result = JSON.parse(event.data);
            updateRecognitionUI(result);
        } catch (e) {
            console.error("[WS] Parse-Fehler:", e);
        }
    };

    ws.onclose = () => {
        setConnectionStatus("offline");
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => ws.close();
}

/* =====================
   ERKENNUNGS-UI
   ===================== */
function updateRecognitionUI(result) {
    const { erkannt, kennzeichen, konfidenz, erlaubt, zeitstempel } = result;

    statusLight.className = "status-light";
    if (!erkannt) {
        statusLabel.textContent = "Kein Kennzeichen erkannt";
        plateText.textContent = "–";
        confidenceText.textContent = "";
    } else if (erlaubt) {
        statusLight.classList.add("green");
        statusLabel.textContent = "Erlaubt – Zugang gewährt";
        plateText.textContent = kennzeichen;
        confidenceText.textContent = `Konfidenz: ${Math.round(konfidenz * 100)}%`;
    } else {
        statusLight.classList.add("red");
        statusLabel.textContent = "Nicht erlaubt – Zugang verweigert";
        plateText.textContent = kennzeichen;
        confidenceText.textContent = `Konfidenz: ${Math.round(konfidenz * 100)}%`;
    }

    if (zeitstempel) {
        const dt = new Date(zeitstempel);
        lastUpdate.textContent = `Zuletzt: ${dt.toLocaleTimeString("de-DE")}`;
    }
}

function setConnectionStatus(state) {
    connectionDot.className = "dot " + state;
    connectionText.textContent = { online: "Verbunden", offline: "Getrennt", connecting: "Verbinde..." }[state] ?? state;
}

/* =====================
   TABS
   ===================== */
document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
        if (btn.dataset.tab === "log")      loadLog();
        if (btn.dataset.tab === "settings") loadSystemStatus();
    });
});

/* =====================
   WHITELIST
   ===================== */
async function loadPlates() {
    const onlyActive = document.getElementById("showOnlyActive").checked;
    const list = document.getElementById("platesList");
    list.innerHTML = '<div class="loading">Lade...</div>';

    try {
        const resp = await fetch(`${API_BASE}/api/plates/?nur_aktive=${onlyActive}`);
        const plates = await resp.json();

        document.getElementById("plateCount").textContent = `${plates.length} Einträge`;

        if (plates.length === 0) {
            list.innerHTML = '<div class="empty">Keine Kennzeichen in der Whitelist</div>';
            return;
        }

        list.innerHTML = plates.map(p => `
            <div class="plate-item ${p.aktiv ? "" : "inactive"}" data-id="${p.id}">
                <span class="plate-number">${p.kennzeichen}</span>
                <span class="plate-desc">${p.beschreibung || "–"}</span>
                <span class="badge ${p.aktiv ? "badge-active" : "badge-inactive"}">
                    ${p.aktiv ? "Aktiv" : "Inaktiv"}
                </span>
                <div class="actions">
                    <button class="btn btn-sm btn-secondary toggle-btn"
                            data-id="${p.id}" data-aktiv="${p.aktiv}">
                        ${p.aktiv ? "Deaktivieren" : "Aktivieren"}
                    </button>
                    <button class="btn btn-sm btn-danger delete-btn" data-id="${p.id}">Löschen</button>
                </div>
            </div>
        `).join("");

        list.querySelectorAll(".toggle-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const aktiv = btn.dataset.aktiv === "true";
                await fetch(`${API_BASE}/api/plates/${btn.dataset.id}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ aktiv: !aktiv }),
                });
                loadPlates();
            });
        });

        list.querySelectorAll(".delete-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                if (!confirm("Kennzeichen wirklich löschen?")) return;
                await fetch(`${API_BASE}/api/plates/${btn.dataset.id}`, { method: "DELETE" });
                loadPlates();
            });
        });
    } catch (e) {
        list.innerHTML = '<div class="empty">Fehler beim Laden</div>';
    }
}

document.getElementById("addPlateForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const kennzeichen  = document.getElementById("newPlate").value.trim().toUpperCase();
    const beschreibung = document.getElementById("newDescription").value.trim();

    const resp = await fetch(`${API_BASE}/api/plates/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kennzeichen, beschreibung: beschreibung || null }),
    });

    if (resp.ok) {
        document.getElementById("newPlate").value = "";
        document.getElementById("newDescription").value = "";
        loadPlates();
    } else if (resp.status === 409) {
        alert("Kennzeichen ist bereits vorhanden.");
    } else {
        alert("Fehler beim Hinzufügen.");
    }
});

document.getElementById("showOnlyActive").addEventListener("change", loadPlates);

/* =====================
   LOG
   ===================== */
async function loadLog() {
    const list = document.getElementById("logList");
    list.innerHTML = '<div class="loading">Lade...</div>';

    try {
        const resp = await fetch(`${API_BASE}/api/plates/log/history?limit=100`);
        const logs = await resp.json();

        if (logs.length === 0) {
            list.innerHTML = '<div class="empty">Noch keine Einträge</div>';
            return;
        }

        list.innerHTML = logs.map(entry => {
            let cssClass = "no-plate", label = "Kein Kennzeichen";
            if (entry.erkannt && entry.erlaubt)  { cssClass = "allowed"; label = "Erlaubt"; }
            if (entry.erkannt && !entry.erlaubt) { cssClass = "denied";  label = "Verweigert"; }
            const dt = new Date(entry.zeitstempel);
            return `
                <div class="log-item ${cssClass}">
                    <span class="log-plate">${entry.kennzeichen || "–"}</span>
                    <span>${label}</span>
                    <span class="log-conf">${entry.konfidenz ? Math.round(entry.konfidenz * 100) + "%" : ""}</span>
                    <span class="log-time">${dt.toLocaleString("de-DE")}</span>
                </div>`;
        }).join("");
    } catch (e) {
        list.innerHTML = '<div class="empty">Fehler beim Laden</div>';
    }
}

document.getElementById("refreshLog").addEventListener("click", loadLog);

/* =====================
   SYSTEM STATUS
   ===================== */
async function loadSystemStatus() {
    const grid = document.getElementById("systemStatus");

    try {
        const [camResp, recResp] = await Promise.all([
            fetch(`${API_BASE}/api/camera/status`),
            fetch(`${API_BASE}/api/recognition/status`),
        ]);
        const cam = await camResp.json();
        const rec = await recResp.json();

        grid.innerHTML = `
            <div class="status-item">
                <div class="label">ESP32 Kamera</div>
                <div class="value ${cam.online ? "ok" : "offline"}">${cam.online ? "Online" : "Offline"}</div>
            </div>
            <div class="status-item">
                <div class="label">Scanner</div>
                <div class="value ${rec.scanning ? "ok" : ""}">${rec.scanning ? "Läuft" : "Gestoppt"}</div>
            </div>
            <div class="status-item">
                <div class="label">Verbundene Clients</div>
                <div class="value">${rec.clients}</div>
            </div>
            <div class="status-item">
                <div class="label">ESP32 URL</div>
                <div class="value" style="font-size:0.8rem">${rec.esp32_url}</div>
            </div>`;
    } catch (e) {
        grid.innerHTML = '<div class="empty">Fehler beim Laden</div>';
    }
}

/* =====================
   SCANNER-STEUERUNG
   ===================== */
document.getElementById("startScan").addEventListener("click", async () => {
    await fetch(`${API_BASE}/api/recognition/scan/start`, { method: "POST" });
    loadSystemStatus();
});

document.getElementById("stopScan").addEventListener("click", async () => {
    await fetch(`${API_BASE}/api/recognition/scan/stop`, { method: "POST" });
    loadSystemStatus();
});

document.getElementById("scanOnce").addEventListener("click", async () => {
    const btn = document.getElementById("scanOnce");
    btn.disabled = true;
    btn.textContent = "Scanne...";
    try {
        const resp = await fetch(`${API_BASE}/api/recognition/scan-once`, { method: "POST" });
        const result = await resp.json();
        updateRecognitionUI(result);
    } finally {
        btn.disabled = false;
        btn.textContent = "Einmal scannen";
    }
});

/* =====================
   UPLOAD (TEST)
   ===================== */
document.getElementById("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = document.getElementById("uploadFile").files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    const resultDiv = document.getElementById("uploadResult");
    resultDiv.style.display = "none";

    try {
        const resp = await fetch(`${API_BASE}/api/recognition/upload`, {
            method: "POST",
            body: formData,
        });
        const result = await resp.json();
        updateRecognitionUI(result);

        resultDiv.style.display = "block";
        resultDiv.className = result.erlaubt ? "success" : "denied";
        resultDiv.innerHTML = result.erkannt
            ? `Erkannt: <strong>${result.kennzeichen}</strong> (${Math.round(result.konfidenz * 100)}%) – ${result.erlaubt ? "✓ Erlaubt" : "✗ Nicht erlaubt"}`
            : "Kein Kennzeichen erkannt";
    } catch (e) {
        resultDiv.style.display = "block";
        resultDiv.className = "denied";
        resultDiv.textContent = "Fehler bei der Erkennung";
    }
});

/* =====================
   INIT
   ===================== */
document.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
    startStream();
    loadPlates();
});
