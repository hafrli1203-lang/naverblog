from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Any

DB_PATH = Path(__file__).parent / "blogger_db.sqlite"


def get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def conn_ctx(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = get_conn(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS stores (
          store_id        INTEGER PRIMARY KEY AUTOINCREMENT,
          store_name      TEXT,
          place_url       TEXT,
          region_text     TEXT NOT NULL,
          category_text   TEXT NOT NULL,
          address_text    TEXT,
          created_at      TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_stores_region_cat ON stores(region_text, category_text);

        CREATE TABLE IF NOT EXISTS campaigns (
          campaign_id     INTEGER PRIMARY KEY AUTOINCREMENT,
          store_id        INTEGER NOT NULL,
          memo            TEXT,
          status          TEXT NOT NULL DEFAULT '대기중',
          created_at      TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY(store_id) REFERENCES stores(store_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_campaigns_store ON campaigns(store_id, created_at);

        CREATE TABLE IF NOT EXISTS bloggers (
          blogger_id      TEXT PRIMARY KEY,
          blog_url        TEXT NOT NULL,
          first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
          last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
          last_post_date  TEXT,
          activity_interval_days REAL,
          sponsor_signal_rate REAL,
          food_bias_rate  REAL,
          posts_sample_json TEXT
        );

        CREATE TABLE IF NOT EXISTS exposures (
          exposure_id     INTEGER PRIMARY KEY AUTOINCREMENT,
          checked_at      TEXT NOT NULL,
          checked_date    TEXT NOT NULL,
          store_id        INTEGER NOT NULL,
          keyword         TEXT NOT NULL,
          blogger_id      TEXT NOT NULL,
          rank            INTEGER,
          strength_points INTEGER NOT NULL,
          is_page1        INTEGER NOT NULL,
          is_exposed      INTEGER NOT NULL,
          post_link       TEXT,
          post_title      TEXT,
          FOREIGN KEY(store_id) REFERENCES stores(store_id) ON DELETE CASCADE,
          FOREIGN KEY(blogger_id) REFERENCES bloggers(blogger_id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_exposures_daily
        ON exposures(store_id, keyword, blogger_id, checked_date);

        CREATE INDEX IF NOT EXISTS idx_exposures_store_date ON exposures(store_id, checked_at);
        CREATE INDEX IF NOT EXISTS idx_exposures_blogger_date ON exposures(blogger_id, checked_at);
        CREATE INDEX IF NOT EXISTS idx_exposures_keyword_date ON exposures(keyword, checked_at);
        """
    )

    # 마이그레이션: 기존 DB에 post_link, post_title 컬럼이 없으면 추가
    cursor = conn.execute("PRAGMA table_info(exposures)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "post_link" not in existing_cols:
        conn.execute("ALTER TABLE exposures ADD COLUMN post_link TEXT")
    if "post_title" not in existing_cols:
        conn.execute("ALTER TABLE exposures ADD COLUMN post_title TEXT")


def upsert_store(
    conn: sqlite3.Connection,
    region_text: str,
    category_text: str,
    place_url: Optional[str],
    store_name: Optional[str],
    address_text: Optional[str],
) -> int:
    region_text = (region_text or "").strip()
    category_text = (category_text or "").strip()
    if not region_text or not category_text:
        raise ValueError("region_text and category_text are required")

    # 동일 매장 식별: place_url이 있으면 우선, 없으면 (region+category+store_name+address) 조합
    if place_url:
        row = conn.execute("SELECT store_id FROM stores WHERE place_url = ?", (place_url,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE stores
                SET store_name=COALESCE(?, store_name),
                    region_text=?,
                    category_text=?,
                    address_text=COALESCE(?, address_text),
                    updated_at=datetime('now')
                WHERE store_id=?
                """,
                (store_name, region_text, category_text, address_text, row["store_id"]),
            )
            return int(row["store_id"])

    row = conn.execute(
        """
        SELECT store_id FROM stores
        WHERE region_text=? AND category_text=?
          AND COALESCE(store_name,'') = COALESCE(?, '')
          AND COALESCE(address_text,'') = COALESCE(?, '')
        ORDER BY store_id DESC LIMIT 1
        """,
        (region_text, category_text, store_name, address_text),
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE stores
            SET place_url=COALESCE(?, place_url),
                updated_at=datetime('now')
            WHERE store_id=?
            """,
            (place_url, row["store_id"]),
        )
        return int(row["store_id"])

    cur = conn.execute(
        """
        INSERT INTO stores(place_url, store_name, region_text, category_text, address_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        (place_url, store_name, region_text, category_text, address_text),
    )
    return int(cur.lastrowid)


def create_campaign(conn: sqlite3.Connection, store_id: int, memo: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO campaigns(store_id, memo) VALUES (?, ?)",
        (store_id, memo),
    )
    return int(cur.lastrowid)


def upsert_blogger(
    conn: sqlite3.Connection,
    blogger_id: str,
    blog_url: str,
    last_post_date: Optional[str],
    activity_interval_days: Optional[float],
    sponsor_signal_rate: Optional[float],
    food_bias_rate: Optional[float],
    posts_sample_json: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO bloggers(
          blogger_id, blog_url, last_post_date,
          activity_interval_days, sponsor_signal_rate, food_bias_rate,
          posts_sample_json, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(blogger_id) DO UPDATE SET
          blog_url=excluded.blog_url,
          last_post_date=COALESCE(excluded.last_post_date, bloggers.last_post_date),
          activity_interval_days=COALESCE(excluded.activity_interval_days, bloggers.activity_interval_days),
          sponsor_signal_rate=COALESCE(excluded.sponsor_signal_rate, bloggers.sponsor_signal_rate),
          food_bias_rate=COALESCE(excluded.food_bias_rate, bloggers.food_bias_rate),
          posts_sample_json=COALESCE(excluded.posts_sample_json, bloggers.posts_sample_json),
          last_seen_at=datetime('now')
        """,
        (
            blogger_id,
            blog_url,
            last_post_date,
            activity_interval_days,
            sponsor_signal_rate,
            food_bias_rate,
            posts_sample_json,
        ),
    )


def insert_exposure_fact(
    conn: sqlite3.Connection,
    store_id: int,
    keyword: str,
    blogger_id: str,
    rank: Optional[int],
    strength_points: int,
    is_page1: bool,
    is_exposed: bool,
    post_link: Optional[str] = None,
    post_title: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO exposures(
          checked_at, checked_date, store_id, keyword, blogger_id,
          rank, strength_points, is_page1, is_exposed, post_link, post_title
        )
        VALUES (datetime('now'), date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(store_id, keyword, blogger_id, checked_date) DO UPDATE SET
          rank=excluded.rank,
          strength_points=excluded.strength_points,
          is_page1=excluded.is_page1,
          is_exposed=excluded.is_exposed,
          post_link=excluded.post_link,
          post_title=excluded.post_title
        """,
        (
            store_id,
            keyword,
            blogger_id,
            rank,
            strength_points,
            1 if is_page1 else 0,
            1 if is_exposed else 0,
            post_link,
            post_title,
        ),
    )
