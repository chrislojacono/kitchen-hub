import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("KITCHEN_DB", Path(__file__).resolve().parent.parent / "kitchen.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS pantry_items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    qty REAL NOT NULL DEFAULT 1 CHECK (qty >= 0),
    unit TEXT,
    category TEXT,
    added_on TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    expires_on TEXT,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'receipt', 'agent'))
);
CREATE INDEX IF NOT EXISTS idx_pantry_expires ON pantry_items (expires_on);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    slot TEXT NOT NULL CHECK (slot IN ('breakfast', 'lunch', 'dinner', 'snack')),
    title TEXT NOT NULL,
    recipe_json TEXT,
    UNIQUE (date, slot)
);

CREATE TABLE IF NOT EXISTS grocery_items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    qty REAL,
    unit TEXT,
    checked INTEGER NOT NULL DEFAULT 0 CHECK (checked IN (0, 1)),
    added_on TEXT NOT NULL DEFAULT (date('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    image_path TEXT NOT NULL,
    raw_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'parsed', 'confirmed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn
