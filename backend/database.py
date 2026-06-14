import sqlite3
# sqlite3 ist ein eingebautes Python-Modul.
# SQLite ist eine Datenbank die komplett in einer einzigen Datei lebt (plates.db).
# Man braucht keinen extra Server – Python kann direkt mit der Datei reden.

import datetime
# datetime brauchen wir um den aktuellen Zeitpunkt zu speichern,


# Das ist der Name der Datenbankdatei.
# Sie wird automatisch im backend/ Ordner erstellt wenn das Programm startet.
DB_NAME = "plates.db"


def init_db():
    # Diese Funktion wird einmal beim Start aufgerufen.
    # Sie erstellt die Datenbank und die Tabellen – falls sie noch nicht existieren.

    # sqlite3.connect() öffnet die Datenbankdatei.
    # Falls die Datei noch nicht existiert, wird sie hier automatisch erstellt.
    conn = sqlite3.connect(DB_NAME)

    # conn.cursor() erstellt einen sogenannten "Cursor".
    # Stell dir den Cursor vor wie einen Stift:
    # Mit ihm schreibst und liest du in der Datenbank.
    # Ohne Cursor kannst du keine Befehle ausführen.
    c = conn.cursor()

    # c.execute() schickt einen SQL-Befehl an die Datenbank.
    # SQL ist eine eigene Sprache nur für Datenbanken – wie eine Art Befehlssprache.
    # "CREATE TABLE IF NOT EXISTS" bedeutet:
    #   → Erstelle eine Tabelle namens "plates"
    #   → aber NUR wenn sie noch nicht existiert (damit kein Fehler beim 2. Start kommt)
    #
    # Eine Tabelle ist wie eine Excel-Tabelle mit Spalten und Zeilen.
    # Hier erstellen wir die Tabelle mit diesen Spalten:
    #   id           – eine eindeutige Nummer für jeden Eintrag (zählt automatisch: 1, 2, 3...)
    #   plate_number – das Kennzeichen als Text, z.B. "WRAB123"
    #                  UNIQUE bedeutet: dasselbe Kennzeichen darf nicht zweimal vorkommen
    #   beschreibung – optionaler Text z.B. "Mein Auto" oder "Papa"
    #   aktiv        – 1 = das Auto darf rein, 0 = gesperrt (aber nicht gelöscht)
    #   created_at   – Datum und Uhrzeit wann das Kennzeichen hinzugefügt wurde
    c.execute('''CREATE TABLE IF NOT EXISTS plates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT UNIQUE,
                  beschreibung TEXT,
                  aktiv INTEGER DEFAULT 1,
                  created_at TIMESTAMP)''')

    # Zweite Tabelle: "logs" – das Zugriffsprotokoll.
    # Hier wird jeder Erkennungsversuch gespeichert, egal ob erlaubt oder nicht.
    # So kann man später nachschauen: Wer hat wann versucht reinzukommen?
    #
    # Spalten:
    #   id             – eindeutige Nummer
    #   plate_number   – welches Kennzeichen wurde erkannt
    #   access_granted – wurde Zugang gewährt? True (ja) oder False (nein)
    #   konfidenz      – wie sicher war die OCR? z.B. 0.87 bedeutet 87% sicher
    #   timestamp      – wann war der Versuch
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT,
                  access_granted BOOLEAN,
                  konfidenz REAL,
                  timestamp TIMESTAMP)''')

    # ----------------------- eigentlicht nicht relevant -------------------------
    # Migration – das ist ein Sicherheitsnetz für ältere Datenbanken.
    # Situation: Das Programm lief schon, die plates.db existiert bereits,
    # aber damals gab es die Spalten "beschreibung" und "aktiv" noch nicht.
    # ALTER TABLE fügt eine neue Spalte nachträglich hinzu.
    # Falls die Spalte schon existiert, würde SQL einen Fehler werfen –
    # deshalb fangen wir den Fehler mit try/except ab und ignorieren ihn einfach.
    for col, definition in [("beschreibung", "TEXT"), ("aktiv", "INTEGER DEFAULT 1")]:
        try:
            c.execute(f"ALTER TABLE plates ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # "pass" bedeutet: tu nichts, mach einfach weiter

    try:
        c.execute("ALTER TABLE logs ADD COLUMN konfidenz REAL")
    except sqlite3.OperationalError:
        pass
    # --------------------------- bis hier nicht relevant ---------------------------

    # conn.commit() speichert alle Änderungen dauerhaft in die Datei.
    # Ohne commit() gehen die Änderungen verloren wenn das Programm stoppt.
    # Denk daran wie Strg+S beim Speichern.
    conn.commit()

    # conn.close() schließt die Verbindung zur Datenbankdatei wieder.
    # Das sollte man immer machen wenn man fertig ist.
    conn.close()


def add_plate(plate_number, beschreibung=None):
    # beschreibung=None bedeutet: wenn man keinen Text mitgibt, ist es einfach leer

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # INSERT INTO fügt eine neue Zeile in die Tabelle ein.
        # Die Fragezeichen (?) sind Platzhalter – die echten Werte kommen im zweiten Argument.
        # Warum Platzhalter? Weil es sicherer ist als Text direkt einzusetzen.
        # Würde man schreiben: f"INSERT ... VALUES ('{plate_number}'...)"
        # könnte jemand mit einem manipulierten Kennzeichen die Datenbank kaputtmachen.
        # Mit ? macht Python das automatisch sicher.
        c.execute(
            "INSERT INTO plates (plate_number, beschreibung, aktiv, created_at) VALUES (?, ?, 1, ?)",
            (plate_number, beschreibung, datetime.datetime.now())
            # datetime.datetime.now() gibt die aktuelle Uhrzeit zurück, z.B. "2026-05-12 10:31:00"
        )

        conn.commit()
        conn.close()
        return True  # Hat geklappt → True zurückgeben

    except sqlite3.IntegrityError:
        # Dieser Fehler passiert wenn das Kennzeichen schon in der DB ist.
        # Wir haben oben "plate_number TEXT UNIQUE" definiert –
        # UNIQUE bedeutet: kein Eintrag darf denselben Wert zweimal haben.
        # Also: statt das Programm abstürzen zu lassen, geben wir einfach False zurück.
        return False


def remove_plate(plate_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # DELETE FROM löscht eine Zeile aus der Tabelle.
    # WHERE id=? bedeutet: nur die Zeile mit dieser bestimmten ID löschen.
    # Ohne WHERE würde man ALLE Zeilen löschen!
    c.execute("DELETE FROM plates WHERE id=?", (plate_id,))

    conn.commit()
    conn.close()


# Kennzeichen aktivieren oder sperren (ohne es zu löschen)
def set_plate_active(plate_id, aktiv):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # UPDATE ändert einen Wert in einer bestehenden Zeile.
    # Hier setzen wir die Spalte "aktiv" auf 1 oder 0.
    # "1 if aktiv else 0" bedeutet:
    #   → wenn aktiv=True  → speichere 1
    #   → wenn aktiv=False → speichere 0
    # SQLite kennt kein echtes True/False, deshalb nehmen wir 1 und 0.
    c.execute("UPDATE plates SET aktiv=? WHERE id=?", (1 if aktiv else 0, plate_id))

    conn.commit()
    conn.close()


def get_all_plates(nur_aktive=False):
    conn = sqlite3.connect(DB_NAME)

    # row_factory = sqlite3.Row ist eine Einstellung die bestimmt wie Ergebnisse aussehen.
    # Ohne diese Einstellung bekommt man Tupel zurück: (1, "WRAB123", "Mein Auto", 1, "2026-05-01")
    # Mit dieser Einstellung bekommt man Dictionaries: row["plate_number"] = "WRAB123"
    # Das ist viel lesbarer im Code.
    conn.row_factory = sqlite3.Row

    c = conn.cursor()

    if nur_aktive:
        # SELECT * bedeutet: hole alle Spalten
        # WHERE aktiv=1 bedeutet: nur die erlaubten Kennzeichen
        # ORDER BY created_at DESC bedeutet: neueste zuerst
        c.execute("SELECT * FROM plates WHERE aktiv=1 ORDER BY created_at DESC")
    else:
        # Alle Kennzeichen, auch gesperrte
        c.execute("SELECT * FROM plates ORDER BY created_at DESC")

    # fetchall() holt alle Ergebniszeilen auf einmal und gibt sie als Liste zurück
    rows = c.fetchall()
    conn.close()
    return rows


def _normalize(plate: str) -> str:
    # Der Unterstrich am Anfang signalisiert: diese Funktion ist nur intern gedacht,
    # sie wird nicht von außen aufgerufen.
    #
    # Problem: Die OCR gibt "WRAB123" zurück,
    # aber in der Datenbank steht vielleicht "WR-AB 123" (mit Bindestrich und Leerzeichen).
    # Normaler Textvergleich würde sagen: die sind unterschiedlich → kein Zugang.
    # Das wäre falsch!
    #
    # Lösung: Wir entfernen aus BEIDEN Seiten alles außer Buchstaben und Zahlen,
    # und machen alles groß. Dann sind sie gleich.
    #
    # re.sub(r'[^A-Z0-9]', '', text) bedeutet:
    #   → Ersetze alles was KEIN Buchstabe oder keine Zahl ist, mit nichts (löschen)
    #   → [^A-Z0-9] = alles außer A-Z und 0-9
    # Beispiele:
    #   "WR-AB 123"  →  "WRAB123"
    #   "wrab123"    →  "WRAB123"
    #   "WR.AB/123"  →  "WRAB123"
    import re
    return re.sub(r'[^A-Z0-9]', '', plate.upper())


def check_plate(plate_number):
    # Schritt 1: Das erkannte Kennzeichen normalisieren
    # z.B. "WRAB123" bleibt "WRAB123"
    norm = _normalize(plate_number)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Alle aktiven Kennzeichen aus der Whitelist holen
    c.execute("SELECT plate_number FROM plates WHERE aktiv=1")
    rows = c.fetchall()
    conn.close()

    # Jeden DB-Eintrag ebenfalls normalisieren und mit dem erkannten Kennzeichen vergleichen.
    # any() schaut ob mindestens EIN Eintrag in der Liste zutrifft.
    # Sobald ein Treffer gefunden wird, gibt any() True zurück – ohne alle anderen zu prüfen.
    return any(_normalize(r["plate_number"]) == norm for r in rows)


def log_access(plate_number, granted, konfidenz=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Erkennungsversuch in die logs-Tabelle schreiben.
    # Das passiert immer – egal ob Zugang gewährt wurde oder nicht.
    # granted ist True oder False (hat Python automatisch als 1 oder 0 gespeichert)
    # datetime.datetime.now() = aktuelle Uhrzeit
    c.execute(
        "INSERT INTO logs (plate_number, access_granted, konfidenz, timestamp) VALUES (?, ?, ?, ?)",
        (plate_number, granted, konfidenz, datetime.datetime.now())
    )

    conn.commit()
    conn.close()


def get_recent_logs(limit=100):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Die letzten Einträge holen, neueste zuerst.
    # LIMIT ? bedeutet: maximal so viele Einträge zurückgeben.
    # Standard ist 100 – man kann aber auch z.B. 10 übergeben für nur die letzten 10.
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))

    rows = c.fetchall()
    conn.close()
    return rows
