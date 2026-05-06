import sqlite3
import datetime

# Name der SQLite-Datenbankdatei (liegt im backend/ Ordner)
DB_NAME = "plates.db"


def init_db():
    """Erstellt die Datenbank und Tabellen beim ersten Start."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Tabelle für die Whitelist (erlaubte Kennzeichen)
    c.execute('''CREATE TABLE IF NOT EXISTS plates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT UNIQUE,
                  beschreibung TEXT,
                  aktiv INTEGER DEFAULT 1,
                  created_at TIMESTAMP)''')

    # Tabelle für den Zugriffslog (jeder Erkennungsversuch wird gespeichert)
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT,
                  access_granted BOOLEAN,
                  konfidenz REAL,
                  timestamp TIMESTAMP)''')

    # Migration: falls die DB bereits existiert, fehlende Spalten nachträglich hinzufügen
    for col, definition in [("beschreibung", "TEXT"), ("aktiv", "INTEGER DEFAULT 1")]:
        try:
            c.execute(f"ALTER TABLE plates ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits
    try:
        c.execute("ALTER TABLE logs ADD COLUMN konfidenz REAL")
    except sqlite3.OperationalError:
        pass  # Spalte existiert bereits

    conn.commit()
    conn.close()


def add_plate(plate_number, beschreibung=None):
    """Fügt ein Kennzeichen zur Whitelist hinzu. Gibt False zurück wenn es bereits existiert."""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO plates (plate_number, beschreibung, aktiv, created_at) VALUES (?, ?, 1, ?)",
            (plate_number, beschreibung, datetime.datetime.now())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # UNIQUE-Constraint verletzt: Kennzeichen bereits in der DB
        return False


def remove_plate(plate_id):
    """Löscht ein Kennzeichen anhand seiner ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE id=?", (plate_id,))
    conn.commit()
    conn.close()


def set_plate_active(plate_id, aktiv):
    """Aktiviert oder deaktiviert ein Kennzeichen (ohne es zu löschen)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE plates SET aktiv=? WHERE id=?", (1 if aktiv else 0, plate_id))
    conn.commit()
    conn.close()


def get_all_plates(nur_aktive=False):
    """Gibt alle Kennzeichen zurück. Mit nur_aktive=True nur die aktivierten."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Ergebnisse als Dictionary statt Tupel
    c = conn.cursor()
    if nur_aktive:
        c.execute("SELECT * FROM plates WHERE aktiv=1 ORDER BY created_at DESC")
    else:
        c.execute("SELECT * FROM plates ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


def _normalize(plate: str) -> str:
    """Entfernt alles außer Buchstaben und Zahlen (z.B. Bindestriche, Leerzeichen).
    So matchen 'WR-AB 123' und 'WRAB123' auf dasselbe Kennzeichen."""
    import re
    return re.sub(r'[^A-Z0-9]', '', plate.upper())


def check_plate(plate_number):
    """Prüft ob ein Kennzeichen in der Whitelist ist.
    Vergleich ist normalisiert — Bindestriche und Leerzeichen werden ignoriert."""
    norm = _normalize(plate_number)
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT plate_number FROM plates WHERE aktiv=1")
    rows = c.fetchall()
    conn.close()
    return any(_normalize(r["plate_number"]) == norm for r in rows)


def log_access(plate_number, granted, konfidenz=None):
    """Speichert einen Erkennungsversuch im Log (unabhängig ob erlaubt oder nicht)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (plate_number, access_granted, konfidenz, timestamp) VALUES (?, ?, ?, ?)",
        (plate_number, granted, konfidenz, datetime.datetime.now())
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit=100):
    """Gibt die letzten N Log-Einträge zurück, neueste zuerst."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows
