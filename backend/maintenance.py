from __future__ import annotations
import sqlite3
from typing import Dict

from backend.db import cleanup_expired_cache
from backend.admin_db import cleanup_old_analytics


def cleanup_exposures(conn: sqlite3.Connection, keep_days: int = 180) -> int:
    cur = conn.execute(
        "DELETE FROM exposures WHERE checked_at < datetime('now', ?)",
        (f"-{keep_days} days",),
    )
    return cur.rowcount


def cleanup_all(conn: sqlite3.Connection, keep_days: int = 180) -> Dict[str, int]:
    """기존 exposures 보관 정책 + 만료 캐시 정리 + 분석 로그 정리 통합."""
    exp_deleted = cleanup_exposures(conn, keep_days)
    cache_stats = cleanup_expired_cache(conn)
    analytics_stats = cleanup_old_analytics(conn, keep_days=90)
    return {
        "exposures_deleted": exp_deleted,
        **cache_stats,
        **analytics_stats,
    }
