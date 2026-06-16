# Funktionsweise – ESP32 Kennzeichenerkennung

## Was ist das System?

Ein automatisches Torzugangs-System. Eine Kamera filmt die Einfahrt,
erkennt das Kennzeichen des ankommenden Fahrzeugs und öffnet das Tor
automatisch – ohne dass jemand einen Knopf drücken muss.

---

## Die zwei Komponenten

**ESP32-CAM** – die Hardware  
Ein kleiner Mikrocontroller mit eingebauter Kamera. Er ist mit dem WLAN verbunden
und sendet permanent ein Live-Video. Außerdem hat er ein Relais angeschlossen,
das das Tor öffnen kann.

**Flask-Backend** – die Software  
Ein Python-Programm das auf einem Computer läuft. Es empfängt das Video,
analysiert die Bilder, verwaltet die Whitelist und spricht mit dem ESP32.

---

## Was passiert Schritt für Schritt?

### 1. Start
Beim Start des Programms passieren drei Dinge gleichzeitig:
- Die Datenbank wird geöffnet (oder erstellt falls sie noch nicht existiert)
- EasyOCR wird geladen – das KI-Modell das Text auf Bildern lesen kann
- Der Web-Server startet und ist bereit für Browser-Verbindungen

---

### 2. Kamera-Stream
Der ESP32 sendet ununterbrochen Bilder über das WLAN (ca. 10–25 Bilder pro Sekunde).
Das Backend verbindet sich mit dem ESP32 und liest diesen Datenstrom.

Aus dem rohen Datenstrom werden einzelne Bilder herausgeschnitten
(erkennbar an speziellen Start- und End-Markierungen im JPEG-Format).

Jedes Bild wird an zwei Stellen weitergegeben:
- An den Browser → damit der Benutzer das Live-Video sieht
- An den OCR-Worker → damit das Kennzeichen erkannt werden kann

---

### 3. Bildverarbeitung
Bevor das KI-Modell ein Bild analysiert, wird es vorbereitet:

1. **Farbe entfernen** – das Bild wird in Graustufen umgewandelt,
   da Farbe für die Texterkennung irrelevant ist
2. **Größe normalisieren** – das Bild wird auf eine einheitliche Breite gebracht
3. **Kontrast verbessern** – dunkle Bereiche werden aufgehellt,
   helle Bereiche gedämpft (CLAHE-Algorithmus)
4. **Schärfen** – Kanten und Buchstabenränder werden hervorgehoben

Dieser Schritt macht die Erkennung deutlich zuverlässiger,
besonders bei schlechter Beleuchtung oder Unschärfe.

---

### 4. Kennzeichenerkennung (OCR)
Das vorbereitete Bild wird an EasyOCR übergeben.
EasyOCR ist ein KI-Modell das darauf trainiert wurde, Text in Bildern zu finden.

EasyOCR gibt zurück:
- Den erkannten Text (z.B. "WR◆AB123" – das ◆ ist das Wappen)
- Eine Konfidenz-Zahl (wie sicher ist das Modell, z.B. 87%)

**Sonderfall Österreich:** Österreichische Kennzeichen haben an dritter Stelle
ein Wappen-Symbol. Die KI liest dieses als Buchstaben mit.
Deshalb wird das dritte Zeichen automatisch immer entfernt.

Das Ergebnis wird bereinigt: nur Buchstaben und Zahlen bleiben übrig.
Dann wird geprüft ob es wie ein Kennzeichen aussieht
(1–3 Buchstaben am Anfang, gesamt 5–9 Zeichen).

---

### 5. Abstimmung (Voting)
Ein einzelnes Bild reicht nicht aus – die Kamera kann unscharf sein,
das Auto fährt, die Beleuchtung wechselt.

Deshalb werden die letzten Erkennungen gesammelt.
Erst wenn dasselbe Kennzeichen oft genug innerhalb von 6 Sekunden
erkannt wurde, gilt es als bestätigt.

Das verhindert Fehlauslösungen durch zufällig ähnlich aussehende Texte.

---

### 6. Datenbankabfrage
Sobald ein Kennzeichen bestätigt ist, wird die Datenbank gefragt:
*Ist dieses Kennzeichen in der Whitelist?*

Der Vergleich ignoriert Bindestriche und Leerzeichen –
"WR-AB 123" und "WRAB123" gelten als dasselbe Kennzeichen.

---

### 7. Tor öffnen oder ablehnen

**Kennzeichen erlaubt →**  
Das Backend schickt eine Anfrage an den ESP32: `/toggle_gate`  
Der ESP32 schaltet das Relais für kurze Zeit ein → das Tor öffnet sich.  
Das Ereignis wird im Log gespeichert.  
Für 30 Sekunden wird das Kennzeichen nicht nochmals ausgelöst (Cooldown).

**Kennzeichen nicht erlaubt →**  
Das Tor bleibt zu. Das Ereignis wird trotzdem im Log gespeichert.

---

### 8. Live-Anzeige im Browser
Während all das passiert, bekommt der Browser in Echtzeit Updates –
ohne die Seite neu laden zu müssen (WebSocket-Verbindung).

Der Browser zeigt:
- Das erkannte Kennzeichen
- Ob es erlaubt oder abgelehnt wurde
- Den Konfidenz-Wert der Erkennung
- Grünes Licht (Zugang) oder rotes Licht (kein Zugang)

---

## Zusammenfassung als Ablauf

```
ESP32-Kamera
     │
     │  MJPEG-Stream über WLAN
     ▼
Flask-Backend empfängt Bilder
     │
     ├──► Browser zeigt Live-Video
     │
     └──► Bildverarbeitung (Graustufen, Kontrast, Schärfe)
               │
               ▼
          EasyOCR erkennt Text
               │
               ▼
          Wappen entfernen, Format prüfen
               │
               ▼
          Voting: oft genug erkannt?
               │
          ┌────┴────┐
         Nein      Ja
          │         │
        warten   Datenbankabfrage
                  │
             ┌────┴────┐
          Nicht      Erlaubt
         erlaubt       │
            │       ESP32: Relais ein
         Rotes       Tor öffnet sich
          Licht      Grünes Licht
```
