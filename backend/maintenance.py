from __future__ import annotations
import sqlite3


def cleanup_exposures(conn: sqlite3.Connection, keep_days: int = 180) -> int:
    cur = conn.execute(
        "DELETE FROM exposures WHERE checked_at < datetime('now', ?)",
        (f"-{keep_days} days",),
    )
    return cur.rowcount
