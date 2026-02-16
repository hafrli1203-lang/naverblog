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

    # 마이그레이션: bloggers 테이블에 base_score, tier_score, tier_grade 컬럼 추가
    cursor2 = conn.execute("PRAGMA table_info(bloggers)")
    blogger_cols = {row[1] for row in cursor2.fetchall()}
    if "base_score" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN base_score REAL")
    if "tier_score" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN tier_score REAL")
    if "tier_grade" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN tier_grade TEXT")

    # v5.0 마이그레이션: RSS 메트릭 + 교차카테고리 데이터
    if "region_power_hits" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN region_power_hits INTEGER DEFAULT 0")
    if "broad_query_hits" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN broad_query_hits INTEGER DEFAULT 0")
    if "rss_interval_avg" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_interval_avg REAL")
    if "rss_originality" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_originality REAL")
    if "rss_diversity" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_diversity REAL")
    if "rss_richness" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_richness REAL")

    # v6.0 마이그레이션: 키워드 적합도 데이터
    if "keyword_match_ratio" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN keyword_match_ratio REAL DEFAULT 0")
    if "queries_hit_ratio" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN queries_hit_ratio REAL DEFAULT 0")

    # v7.0 마이그레이션: 9축 통합 데이터
    if "popularity_cross_score" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN popularity_cross_score REAL DEFAULT 0")
    if "topic_focus" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN topic_focus REAL DEFAULT 0")
    if "topic_continuity" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN topic_continuity REAL DEFAULT 0")
    if "game_defense" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN game_defense REAL DEFAULT 0")
    if "quality_floor" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN quality_floor REAL DEFAULT 0")
    if "days_since_last_post" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN days_since_last_post INTEGER")
    if "rss_originality_v7" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_originality_v7 REAL DEFAULT 0")
    if "rss_diversity_smoothed" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN rss_diversity_smoothed REAL DEFAULT 0")

    # v7.1 마이그레이션: 신규 블로거 메트릭
    if "neighbor_count" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN neighbor_count INTEGER DEFAULT 0")
    if "blog_years" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN blog_years REAL DEFAULT 0")
    if "estimated_tier" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN estimated_tier TEXT DEFAULT 'unknown'")
    if "image_ratio" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN image_ratio REAL DEFAULT 0")
    if "video_ratio" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN video_ratio REAL DEFAULT 0")
    if "exposure_power" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN exposure_power REAL DEFAULT 0")

    # v7.2 마이그레이션: ContentAuthority + SearchPresence
    if "content_authority" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN content_authority REAL DEFAULT 0")
    if "search_presence" not in blogger_cols:
        conn.execute("ALTER TABLE bloggers ADD COLUMN search_presence REAL DEFAULT 0")

    # 마이그레이션: stores 테이블에 topic 컬럼 추가
    cursor3 = conn.execute("PRAGMA table_info(stores)")
    store_cols = {row[1] for row in cursor3.fetchall()}
    if "topic" not in store_cols:
        conn.execute("ALTER TABLE stores ADD COLUMN topic TEXT")

    # blog_analyses 테이블: 블로그 개별 분석 이력
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_analyses (
          analysis_id     INTEGER PRIMARY KEY AUTOINCREMENT,
          blogger_id      TEXT NOT NULL,
          blog_url        TEXT NOT NULL,
          analysis_mode   TEXT NOT NULL DEFAULT 'standalone',
          store_id        INTEGER,
          blog_score      REAL,
          grade           TEXT,
          result_json     TEXT,
          created_at      TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY(store_id) REFERENCES stores(store_id) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_blog_analyses_blogger ON blog_analyses(blogger_id, created_at)"
    )


def upsert_store(
    conn: sqlite3.Connection,
    region_text: str,
    category_text: str,
    place_url: Optional[str],
    store_name: Optional[str],
    address_text: Optional[str],
    topic: Optional[str] = None,
) -> int:
    region_text = (region_text or "").strip()
    category_text = (category_text or "").strip()
    if not region_text:
        raise ValueError("region_text is required")

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
                    topic=COALESCE(?, topic),
                    updated_at=datetime('now')
                WHERE store_id=?
                """,
                (store_name, region_text, category_text, address_text, topic, row["store_id"]),
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
                topic=COALESCE(?, topic),
                updated_at=datetime('now')
            WHERE store_id=?
            """,
            (place_url, topic, row["store_id"]),
        )
        return int(row["store_id"])

    cur = conn.execute(
        """
        INSERT INTO stores(place_url, store_name, region_text, category_text, address_text, topic)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (place_url, store_name, region_text, category_text, address_text, topic),
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
    base_score: Optional[float] = None,
    tier_score: Optional[float] = None,
    tier_grade: Optional[str] = None,
    region_power_hits: Optional[int] = None,
    broad_query_hits: Optional[int] = None,
    rss_interval_avg: Optional[float] = None,
    rss_originality: Optional[float] = None,
    rss_diversity: Optional[float] = None,
    rss_richness: Optional[float] = None,
    keyword_match_ratio: Optional[float] = None,
    queries_hit_ratio: Optional[float] = None,
    # v7.0 신규
    popularity_cross_score: Optional[float] = None,
    topic_focus: Optional[float] = None,
    topic_continuity: Optional[float] = None,
    game_defense: Optional[float] = None,
    quality_floor: Optional[float] = None,
    days_since_last_post: Optional[int] = None,
    rss_originality_v7: Optional[float] = None,
    rss_diversity_smoothed: Optional[float] = None,
    # v7.1 신규
    neighbor_count: Optional[int] = None,
    blog_years: Optional[float] = None,
    estimated_tier: Optional[str] = None,
    image_ratio: Optional[float] = None,
    video_ratio: Optional[float] = None,
    exposure_power: Optional[float] = None,
    # v7.2 신규
    content_authority: Optional[float] = None,
    search_presence: Optional[float] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO bloggers(
          blogger_id, blog_url, last_post_date,
          activity_interval_days, sponsor_signal_rate, food_bias_rate,
          posts_sample_json, base_score, tier_score, tier_grade,
          region_power_hits, broad_query_hits,
          rss_interval_avg, rss_originality, rss_diversity, rss_richness,
          keyword_match_ratio, queries_hit_ratio,
          popularity_cross_score, topic_focus, topic_continuity,
          game_defense, quality_floor, days_since_last_post,
          rss_originality_v7, rss_diversity_smoothed,
          neighbor_count, blog_years, estimated_tier,
          image_ratio, video_ratio, exposure_power,
          content_authority, search_presence,
          first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(blogger_id) DO UPDATE SET
          blog_url=excluded.blog_url,
          last_post_date=COALESCE(excluded.last_post_date, bloggers.last_post_date),
          activity_interval_days=COALESCE(excluded.activity_interval_days, bloggers.activity_interval_days),
          sponsor_signal_rate=COALESCE(excluded.sponsor_signal_rate, bloggers.sponsor_signal_rate),
          food_bias_rate=COALESCE(excluded.food_bias_rate, bloggers.food_bias_rate),
          posts_sample_json=COALESCE(excluded.posts_sample_json, bloggers.posts_sample_json),
          base_score=COALESCE(excluded.base_score, bloggers.base_score),
          tier_score=COALESCE(excluded.tier_score, bloggers.tier_score),
          tier_grade=COALESCE(excluded.tier_grade, bloggers.tier_grade),
          region_power_hits=COALESCE(excluded.region_power_hits, bloggers.region_power_hits),
          broad_query_hits=COALESCE(excluded.broad_query_hits, bloggers.broad_query_hits),
          rss_interval_avg=COALESCE(excluded.rss_interval_avg, bloggers.rss_interval_avg),
          rss_originality=COALESCE(excluded.rss_originality, bloggers.rss_originality),
          rss_diversity=COALESCE(excluded.rss_diversity, bloggers.rss_diversity),
          rss_richness=COALESCE(excluded.rss_richness, bloggers.rss_richness),
          keyword_match_ratio=COALESCE(excluded.keyword_match_ratio, bloggers.keyword_match_ratio),
          queries_hit_ratio=COALESCE(excluded.queries_hit_ratio, bloggers.queries_hit_ratio),
          popularity_cross_score=COALESCE(excluded.popularity_cross_score, bloggers.popularity_cross_score),
          topic_focus=COALESCE(excluded.topic_focus, bloggers.topic_focus),
          topic_continuity=COALESCE(excluded.topic_continuity, bloggers.topic_continuity),
          game_defense=COALESCE(excluded.game_defense, bloggers.game_defense),
          quality_floor=COALESCE(excluded.quality_floor, bloggers.quality_floor),
          days_since_last_post=COALESCE(excluded.days_since_last_post, bloggers.days_since_last_post),
          rss_originality_v7=COALESCE(excluded.rss_originality_v7, bloggers.rss_originality_v7),
          rss_diversity_smoothed=COALESCE(excluded.rss_diversity_smoothed, bloggers.rss_diversity_smoothed),
          neighbor_count=COALESCE(excluded.neighbor_count, bloggers.neighbor_count),
          blog_years=COALESCE(excluded.blog_years, bloggers.blog_years),
          estimated_tier=COALESCE(excluded.estimated_tier, bloggers.estimated_tier),
          image_ratio=COALESCE(excluded.image_ratio, bloggers.image_ratio),
          video_ratio=COALESCE(excluded.video_ratio, bloggers.video_ratio),
          exposure_power=COALESCE(excluded.exposure_power, bloggers.exposure_power),
          content_authority=COALESCE(excluded.content_authority, bloggers.content_authority),
          search_presence=COALESCE(excluded.search_presence, bloggers.search_presence),
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
            base_score,
            tier_score,
            tier_grade,
            region_power_hits,
            broad_query_hits,
            rss_interval_avg,
            rss_originality,
            rss_diversity,
            rss_richness,
            keyword_match_ratio,
            queries_hit_ratio,
            popularity_cross_score,
            topic_focus,
            topic_continuity,
            game_defense,
            quality_floor,
            days_since_last_post,
            rss_originality_v7,
            rss_diversity_smoothed,
            neighbor_count,
            blog_years,
            estimated_tier,
            image_ratio,
            video_ratio,
            exposure_power,
            content_authority,
            search_presence,
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


def insert_blog_analysis(
    conn: sqlite3.Connection,
    blogger_id: str,
    blog_url: str,
    analysis_mode: str,
    store_id: Optional[int],
    blog_score: float,
    grade: str,
    result_json: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO blog_analyses(
          blogger_id, blog_url, analysis_mode, store_id,
          blog_score, grade, result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (blogger_id, blog_url, analysis_mode, store_id, blog_score, grade, result_json),
    )
    return int(cur.lastrowid)
