"""
core/message_store.py
=====================
Persistent SQLite-backed message store.

Tables
──────
  messages  – all chat messages (in + out)
  sos_log   – SOS events with lat/lng and timestamps
"""

import sqlite3
import time
import os
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)

def _get_db_path():
    """Return a writable DB path (Android app storage or local data/)."""
    try:
        from android.storage import app_storage_path
        base = app_storage_path()
    except ImportError:
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, 'mesh.db')

DB_PATH = _get_db_path()


class MessageStore:
    """
    Thread-safe SQLite store for chat messages and SOS events.
    Uses WAL mode for concurrent reads.
    """

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        log.info("MessageStore initialised at %s", db_path)

    # ── Schema ────────────────────────────────────────────────────────────────

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                sender     TEXT    NOT NULL,
                text       TEXT    NOT NULL,
                direction  TEXT    NOT NULL CHECK(direction IN ('in','out')),
                ts         REAL    NOT NULL,
                read       INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sos_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                sender     TEXT    NOT NULL,
                lat        REAL    NOT NULL,
                lng        REAL    NOT NULL,
                ts         REAL    NOT NULL,
                resolved   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS telemetry_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id    TEXT    NOT NULL,
                lat        REAL,
                lng        REAL,
                temp       REAL,
                hum        REAL,
                smoke      INTEGER,
                water      INTEGER,
                ts         REAL    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_ts  ON messages(ts);
            CREATE INDEX IF NOT EXISTS idx_sos_ts       ON sos_log(ts);
            CREATE INDEX IF NOT EXISTS idx_telem_ts     ON telemetry_log(ts);
        """)
        self._conn.commit()

    # ── Messages ──────────────────────────────────────────────────────────────

    def add_message(self, sender: str, text: str, direction: str) -> int:
        ts = time.time()
        cur = self._conn.execute(
            "INSERT INTO messages (sender, text, direction, ts) VALUES (?,?,?,?)",
            (sender, text, direction, ts)
        )
        self._conn.commit()
        return cur.lastrowid

    def get_messages(self, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, sender, text, direction, ts, read FROM messages "
            "ORDER BY ts DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return list(reversed(rows))   # chronological order

    def mark_read(self, msg_id: int):
        self._conn.execute("UPDATE messages SET read=1 WHERE id=?", (msg_id,))
        self._conn.commit()

    def unread_count(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE direction='in' AND read=0"
        )
        return cur.fetchone()[0]

    def clear_messages(self):
        self._conn.execute("DELETE FROM messages")
        self._conn.commit()

    # ── SOS log ───────────────────────────────────────────────────────────────

    def log_sos(self, sender: str, lat: float, lng: float) -> int:
        ts = time.time()
        cur = self._conn.execute(
            "INSERT INTO sos_log (sender, lat, lng, ts) VALUES (?,?,?,?)",
            (sender, lat, lng, ts)
        )
        self._conn.commit()
        return cur.lastrowid

    def resolve_sos(self, sos_id: int):
        self._conn.execute("UPDATE sos_log SET resolved=1 WHERE id=?", (sos_id,))
        self._conn.commit()

    def get_sos_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, sender, lat, lng, ts, resolved FROM sos_log "
            "ORDER BY ts DESC LIMIT ?", (limit,)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── Telemetry log ─────────────────────────────────────────────────────────

    def log_telemetry(self, data: Dict[str, Any]):
        self._conn.execute(
            "INSERT INTO telemetry_log "
            "(node_id, lat, lng, temp, hum, smoke, water, ts) VALUES (?,?,?,?,?,?,?,?)",
            (
                data.get('node_id', 'NODE-1'),
                data.get('lat'), data.get('lng'),
                data.get('temp'), data.get('hum'),
                data.get('smoke'), data.get('water'),
                data.get('ts', time.time())
            )
        )
        self._conn.commit()

    def get_telemetry(self, node_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        if node_id:
            cur = self._conn.execute(
                "SELECT * FROM telemetry_log WHERE node_id=? ORDER BY ts DESC LIMIT ?",
                (node_id, limit)
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM telemetry_log ORDER BY ts DESC LIMIT ?",
                (limit,)
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self):
        self._conn.close()
