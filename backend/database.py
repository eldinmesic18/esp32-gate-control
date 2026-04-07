import sqlite3
import datetime

DB_NAME = "plates.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS plates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT UNIQUE,
                  beschreibung TEXT,
                  aktiv INTEGER DEFAULT 1,
                  created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  plate_number TEXT,
                  access_granted BOOLEAN,
                  konfidenz REAL,
                  timestamp TIMESTAMP)''')
    # Migrate: add columns if they don't exist yet
    for col, definition in [("beschreibung", "TEXT"), ("aktiv", "INTEGER DEFAULT 1")]:
        try:
            c.execute(f"ALTER TABLE plates ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass
    try:
        c.execute("ALTER TABLE logs ADD COLUMN konfidenz REAL")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def add_plate(plate_number, beschreibung=None):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO plates (plate_number, beschreibung, aktiv, created_at) VALUES (?, ?, 1, ?)",
                  (plate_number, beschreibung, datetime.datetime.now()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def remove_plate(plate_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE id=?", (plate_id,))
    conn.commit()
    conn.close()

def set_plate_active(plate_id, aktiv):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE plates SET aktiv=? WHERE id=?", (1 if aktiv else 0, plate_id))
    conn.commit()
    conn.close()

def get_all_plates(nur_aktive=False):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if nur_aktive:
        c.execute("SELECT * FROM plates WHERE aktiv=1 ORDER BY created_at DESC")
    else:
        c.execute("SELECT * FROM plates ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def check_plate(plate_number):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM plates WHERE plate_number=? AND aktiv=1", (plate_number,))
    result = c.fetchone()
    conn.close()
    return result is not None

def log_access(plate_number, granted, konfidenz=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO logs (plate_number, access_granted, konfidenz, timestamp) VALUES (?, ?, ?, ?)",
              (plate_number, granted, konfidenz, datetime.datetime.now()))
    conn.commit()
    conn.close()

def get_recent_logs(limit=100):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows
