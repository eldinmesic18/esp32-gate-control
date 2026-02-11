import sqlite3
import datetime

DB_NAME = "plates.db"

def init_db():
    """
    Erstellt die Datenbanktabellen, falls sie noch nicht existieren.
    - plates: Speichert die zugelassenen Kennzeichen.
    - logs: Speichert die Zugriffsversuche.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Tabelle für zugelassene Kennzeichen
    c.execute('''CREATE TABLE IF NOT EXISTS plates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_number TEXT UNIQUE, created_at TIMESTAMP)''')
    # Tabelle für Zugriffsprotokolle
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_number TEXT, access_granted BOOLEAN, timestamp TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_plate(plate_number):
    """
    Fügt ein neues Kennzeichen zur Datenbank hinzu.
    Gibt True zurück, wenn erfolgreich, False, wenn das Kennzeichen schon existiert.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO plates (plate_number, created_at) VALUES (?, ?)", (plate_number, datetime.datetime.now()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def remove_plate(plate_id):
    """Löscht ein Kennzeichen anhand der ID aus der Datenbank."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE id=?", (plate_id,))
    conn.commit()
    conn.close()

def get_all_plates():
    """Holt alle gespeicherten Kennzeichen, sortiert nach Erstellungsdatum (neueste zuerst)."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Dictionary-ähnlicher Zugriff auf Zeilen
    c = conn.cursor()
    c.execute("SELECT * FROM plates ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def log_access(plate_number, granted):
    """
    Protokolliert einen Zugriffsversuch.
    - plate_number: Das erkannte Kennzeichen
    - granted: Boolean, ob Zugriff gewährt wurde (True) oder nicht (False)
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO logs (plate_number, access_granted, timestamp) VALUES (?, ?, ?)", 
              (plate_number, granted, datetime.datetime.now()))
    conn.commit()
    conn.close()

def get_recent_logs(limit=10):
    """Holt die letzten 'limit' Log-Einträge."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def check_plate(plate_number):
    """
    Prüft, ob ein Kennzeichen in der Datenbank ('plates' Tabelle) vorhanden ist.
    Gibt True zurück, wenn ja (Zugriff erlaubt), sonst False.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM plates WHERE plate_number=?", (plate_number,))
    result = c.fetchone()
    conn.close()
    return result is not None
