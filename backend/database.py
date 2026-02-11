import sqlite3
import datetime

DB_NAME = "plates.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS plates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_number TEXT UNIQUE, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_number TEXT, access_granted BOOLEAN, timestamp TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_plate(plate_number):
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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM plates WHERE id=?", (plate_id,))
    conn.commit()
    conn.close()

def get_all_plates():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM plates ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def log_access(plate_number, granted):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO logs (plate_number, access_granted, timestamp) VALUES (?, ?, ?)", 
              (plate_number, granted, datetime.datetime.now()))
    conn.commit()
    conn.close()

def get_recent_logs(limit=10):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def check_plate(plate_number):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM plates WHERE plate_number=?", (plate_number,))
    result = c.fetchone()
    conn.close()
    return result is not None
