from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional, Any, Dict, List

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


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """ALTER TABLE ADD COLUMN — 이미 존재하면 무시 (워커 경합 조건 안전)"""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass


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

    # 마이그레이션: _safe_add_column으로 워커 경합 조건 안전 처리
    # exposures 테이블
    _safe_add_column(conn, "exposures", "post_link", "TEXT")
    _safe_add_column(conn, "exposures", "post_title", "TEXT")

    # bloggers 테이블: base_score, tier_score, tier_grade
    _safe_add_column(conn, "bloggers", "base_score", "REAL")
    _safe_add_column(conn, "bloggers", "tier_score", "REAL")
    _safe_add_column(conn, "bloggers", "tier_grade", "TEXT")

    # v5.0: RSS 메트릭 + 교차카테고리
    _safe_add_column(conn, "bloggers", "region_power_hits", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "broad_query_hits", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "rss_interval_avg", "REAL")
    _safe_add_column(conn, "bloggers", "rss_originality", "REAL")
    _safe_add_column(conn, "bloggers", "rss_diversity", "REAL")
    _safe_add_column(conn, "bloggers", "rss_richness", "REAL")

    # v6.0: 키워드 적합도
    _safe_add_column(conn, "bloggers", "keyword_match_ratio", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "queries_hit_ratio", "REAL DEFAULT 0")

    # v7.0: 9축 통합
    _safe_add_column(conn, "bloggers", "popularity_cross_score", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "topic_focus", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "topic_continuity", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "game_defense", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "quality_floor", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "days_since_last_post", "INTEGER")
    _safe_add_column(conn, "bloggers", "rss_originality_v7", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "rss_diversity_smoothed", "REAL DEFAULT 0")

    # v7.1: 블로거 메트릭
    _safe_add_column(conn, "bloggers", "neighbor_count", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "blog_years", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "estimated_tier", "TEXT DEFAULT 'unknown'")
    _safe_add_column(conn, "bloggers", "image_ratio", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "video_ratio", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "exposure_power", "REAL DEFAULT 0")

    # v7.2: ContentAuthority + SearchPresence
    _safe_add_column(conn, "bloggers", "content_authority", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "search_presence", "REAL DEFAULT 0")
    _safe_add_column(conn, "bloggers", "avg_image_count", "REAL DEFAULT 0")

    # v7.2 BlogPower
    _safe_add_column(conn, "bloggers", "total_posts", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "total_visitors", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "total_subscribers", "INTEGER DEFAULT 0")
    _safe_add_column(conn, "bloggers", "ranking_percentile", "REAL DEFAULT 100")
    _safe_add_column(conn, "bloggers", "blog_power", "REAL DEFAULT 0")

    # stores 테이블: topic 컬럼
    _safe_add_column(conn, "stores", "topic", "TEXT")

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

    # api_cache 테이블: 네이버 검색 API 응답 캐시 (TTL 6시간)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_cache (
          cache_key      TEXT PRIMARY KEY,
          query_text     TEXT NOT NULL,
          response_json  TEXT NOT NULL,
          item_count     INTEGER NOT NULL DEFAULT 0,
          created_at     TEXT NOT NULL DEFAULT (datetime('now')),
          expires_at     TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at)")

    # search_snapshots 테이블: 매장별 전체 검색 결과 스냅샷 (TTL 24시간)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_snapshots (
          snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
          store_id       INTEGER NOT NULL,
          snapshot_json  TEXT NOT NULL,
          api_calls_used INTEGER NOT NULL DEFAULT 0,
          created_at     TEXT NOT NULL DEFAULT (datetime('now')),
          expires_at     TEXT NOT NULL,
          FOREIGN KEY(store_id) REFERENCES stores(store_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_store ON search_snapshots(store_id, created_at DESC)"
    )

    # ── PRD 신규 테이블: 인플루언서 프로필 ──
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS influencer_profiles (
          profile_id        INTEGER PRIMARY KEY AUTOINCREMENT,
          user_mongo_id     TEXT NOT NULL UNIQUE,
          blog_id           TEXT NOT NULL,
          blog_url          TEXT,
          golden_score      REAL DEFAULT 0,
          grade             TEXT DEFAULT 'F',
          grade_label       TEXT DEFAULT '',
          base_score        REAL DEFAULT 0,
          bp_score          REAL DEFAULT 0,
          ep_score          REAL DEFAULT 0,
          ca_score          REAL DEFAULT 0,
          rq_score          REAL DEFAULT 0,
          fr_score          REAL DEFAULT 0,
          sp_score          REAL DEFAULT 0,
          total_posts       INTEGER DEFAULT 0,
          total_visitors    INTEGER DEFAULT 0,
          total_subscribers INTEGER DEFAULT 0,
          desired_rate      INTEGER DEFAULT 0,
          bio               TEXT,
          specialties       TEXT,
          is_public         INTEGER DEFAULT 1,
          verified_at       TEXT,
          last_analysis     TEXT,
          created_at        TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inf_blog ON influencer_profiles(blog_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inf_score ON influencer_profiles(golden_score DESC)")

    # ── PRD 신규 테이블: 매칭 ──
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
          match_id           INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_user_id      TEXT NOT NULL,
          owner_display_name TEXT,
          store_id           INTEGER,
          influencer_user_id TEXT NOT NULL,
          influencer_blog_id TEXT NOT NULL,
          campaign_type      TEXT DEFAULT 'experience',
          status             TEXT DEFAULT 'pending',
          message            TEXT,
          guide_json         TEXT,
          offered_rate       INTEGER DEFAULT 0,
          decline_reason     TEXT,
          requested_at       TEXT DEFAULT (datetime('now')),
          responded_at       TEXT,
          completed_at       TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_owner ON matches(owner_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_inf ON matches(influencer_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_status ON matches(status)")

    # ── PRD 신규 테이블: 알림 ──
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
          notif_id    INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id     TEXT NOT NULL,
          type        TEXT NOT NULL,
          title       TEXT NOT NULL,
          message     TEXT,
          link        TEXT,
          is_read     INTEGER DEFAULT 0,
          created_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read)")

    # ── PRD 신규 테이블: 서베이 ──
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS surveys (
          survey_id   INTEGER PRIMARY KEY AUTOINCREMENT,
          title       TEXT NOT NULL,
          questions   TEXT NOT NULL,
          target      TEXT DEFAULT 'all',
          is_active   INTEGER DEFAULT 1,
          created_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS survey_responses (
          response_id   INTEGER PRIMARY KEY AUTOINCREMENT,
          survey_id     INTEGER NOT NULL,
          user_mongo_id TEXT,
          answers       TEXT NOT NULL,
          created_at    TEXT DEFAULT (datetime('now')),
          FOREIGN KEY(survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
        )
        """
    )

    # influencer_profiles: email 컬럼 마이그레이션
    _safe_add_column(conn, "influencer_profiles", "email", "TEXT DEFAULT ''")
    # matches: owner_email 컬럼 마이그레이션
    _safe_add_column(conn, "matches", "owner_email", "TEXT DEFAULT ''")

    # blog_profiles 캐시 테이블: 블로그 프로필 스크래핑 결과 (TTL 7일)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_profiles (
          blogger_id   TEXT PRIMARY KEY,
          profile_json TEXT NOT NULL,
          created_at   TEXT NOT NULL DEFAULT (datetime('now')),
          expires_at   TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blog_profiles_expires ON blog_profiles(expires_at)")


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
    avg_image_count: Optional[float] = None,
    # v7.2 BlogPower 신규
    total_posts: Optional[int] = None,
    total_visitors: Optional[int] = None,
    total_subscribers: Optional[int] = None,
    ranking_percentile: Optional[float] = None,
    blog_power: Optional[float] = None,
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
          content_authority, search_presence, avg_image_count,
          total_posts, total_visitors, total_subscribers,
          ranking_percentile, blog_power,
          first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
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
          avg_image_count=COALESCE(excluded.avg_image_count, bloggers.avg_image_count),
          total_posts=COALESCE(excluded.total_posts, bloggers.total_posts),
          total_visitors=COALESCE(excluded.total_visitors, bloggers.total_visitors),
          total_subscribers=COALESCE(excluded.total_subscribers, bloggers.total_subscribers),
          ranking_percentile=COALESCE(excluded.ranking_percentile, bloggers.ranking_percentile),
          blog_power=COALESCE(excluded.blog_power, bloggers.blog_power),
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
            avg_image_count,
            total_posts,
            total_visitors,
            total_subscribers,
            ranking_percentile,
            blog_power,
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


# ============================
# 캐시 함수 (api_cache + search_snapshots + blog_analyses)
# ============================

def get_cached_api_response(conn: sqlite3.Connection, cache_key: str) -> Optional[str]:
    """만료되지 않은 API 캐시 응답 JSON을 반환. 없거나 만료 시 None."""
    row = conn.execute(
        "SELECT response_json FROM api_cache WHERE cache_key = ? AND expires_at > datetime('now')",
        (cache_key,),
    ).fetchone()
    return row["response_json"] if row else None


def set_cached_api_response(
    conn: sqlite3.Connection,
    cache_key: str,
    query: str,
    response_json: str,
    item_count: int,
    ttl_hours: int = 6,
) -> None:
    """API 응답을 캐시에 저장 (ON CONFLICT UPDATE)."""
    expires = (datetime.utcnow() + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO api_cache(cache_key, query_text, response_json, item_count, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          response_json=excluded.response_json,
          item_count=excluded.item_count,
          created_at=datetime('now'),
          expires_at=excluded.expires_at
        """,
        (cache_key, query, response_json, item_count, expires),
    )


def save_search_snapshot(
    conn: sqlite3.Connection,
    store_id: int,
    snapshot_json: str,
    api_calls: int,
    ttl_hours: int = 24,
) -> int:
    """검색 결과 스냅샷 저장. snapshot_id 반환."""
    expires = (datetime.utcnow() + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """
        INSERT INTO search_snapshots(store_id, snapshot_json, api_calls_used, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (store_id, snapshot_json, api_calls, expires),
    )
    return int(cur.lastrowid)


def get_latest_search_snapshot(conn: sqlite3.Connection, store_id: int) -> Optional[Dict[str, Any]]:
    """매장의 최신 유효 스냅샷을 반환. 없거나 만료 시 None."""
    row = conn.execute(
        """
        SELECT snapshot_json, created_at, api_calls_used
        FROM search_snapshots
        WHERE store_id = ? AND expires_at > datetime('now')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (store_id,),
    ).fetchone()
    return dict(row) if row else None


def get_latest_blog_analysis(
    conn: sqlite3.Connection,
    blogger_id: str,
    store_id: Optional[int],
    ttl_hours: int = 48,
) -> Optional[Dict[str, Any]]:
    """블로그 분석 캐시 조회. 기존 blog_analyses 테이블 활용."""
    if store_id:
        row = conn.execute(
            """
            SELECT result_json, created_at
            FROM blog_analyses
            WHERE blogger_id = ? AND store_id = ?
              AND created_at > datetime('now', ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (blogger_id, store_id, f"-{ttl_hours} hours"),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT result_json, created_at
            FROM blog_analyses
            WHERE blogger_id = ? AND store_id IS NULL
              AND created_at > datetime('now', ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (blogger_id, f"-{ttl_hours} hours"),
        ).fetchone()
    return dict(row) if row else None


def get_cached_profile(conn: sqlite3.Connection, blogger_id: str) -> Optional[Dict[str, Any]]:
    """7일 이내 캐시된 프로필 반환, 없으면 None."""
    row = conn.execute(
        "SELECT profile_json FROM blog_profiles WHERE blogger_id=? AND expires_at > datetime('now')",
        (blogger_id,),
    ).fetchone()
    return json.loads(row["profile_json"]) if row else None


def set_cached_profile(conn: sqlite3.Connection, blogger_id: str, profile_data: Dict[str, Any]) -> None:
    """프로필 캐시 저장 (TTL 7일)."""
    # blog_start_date는 datetime 객체일 수 있으므로 직렬화 전 변환
    data = dict(profile_data)
    if "blog_start_date" in data and data["blog_start_date"] is not None:
        if hasattr(data["blog_start_date"], "isoformat"):
            data["blog_start_date"] = data["blog_start_date"].isoformat()
    conn.execute(
        """
        INSERT INTO blog_profiles (blogger_id, profile_json, expires_at)
        VALUES (?, ?, datetime('now', '+7 days'))
        ON CONFLICT(blogger_id) DO UPDATE SET
          profile_json=excluded.profile_json,
          expires_at=excluded.expires_at,
          created_at=datetime('now')
        """,
        (blogger_id, json.dumps(data, ensure_ascii=False)),
    )


def cleanup_expired_cache(conn: sqlite3.Connection) -> Dict[str, int]:
    """만료된 api_cache + search_snapshots + blog_profiles 일괄 삭제. 삭제 건수 반환."""
    c1 = conn.execute("DELETE FROM api_cache WHERE expires_at <= datetime('now')").rowcount
    c2 = conn.execute("DELETE FROM search_snapshots WHERE expires_at <= datetime('now')").rowcount
    c3 = conn.execute("DELETE FROM blog_profiles WHERE expires_at <= datetime('now')").rowcount
    return {"api_cache_deleted": c1, "snapshots_deleted": c2, "profiles_deleted": c3}


# ============================
# 인플루언서 프로필 CRUD
# ============================

def upsert_influencer_profile(
    conn: sqlite3.Connection,
    user_mongo_id: str,
    blog_id: str,
    blog_url: str = "",
    golden_score: float = 0,
    grade: str = "F",
    grade_label: str = "",
    base_score: float = 0,
    bp_score: float = 0,
    ep_score: float = 0,
    ca_score: float = 0,
    rq_score: float = 0,
    fr_score: float = 0,
    sp_score: float = 0,
    total_posts: int = 0,
    total_visitors: int = 0,
    total_subscribers: int = 0,
    desired_rate: int = 0,
    bio: str = "",
    specialties: str = "",
    is_public: int = 1,
    email: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO influencer_profiles(
          user_mongo_id, blog_id, blog_url, golden_score, grade, grade_label,
          base_score, bp_score, ep_score, ca_score, rq_score, fr_score, sp_score,
          total_posts, total_visitors, total_subscribers,
          desired_rate, bio, specialties, is_public, email, last_analysis
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_mongo_id) DO UPDATE SET
          blog_id=excluded.blog_id,
          blog_url=excluded.blog_url,
          golden_score=excluded.golden_score,
          grade=excluded.grade,
          grade_label=excluded.grade_label,
          base_score=excluded.base_score,
          bp_score=excluded.bp_score,
          ep_score=excluded.ep_score,
          ca_score=excluded.ca_score,
          rq_score=excluded.rq_score,
          fr_score=excluded.fr_score,
          sp_score=excluded.sp_score,
          total_posts=excluded.total_posts,
          total_visitors=excluded.total_visitors,
          total_subscribers=excluded.total_subscribers,
          desired_rate=CASE WHEN excluded.desired_rate > 0 THEN excluded.desired_rate ELSE influencer_profiles.desired_rate END,
          bio=CASE WHEN excluded.bio != '' THEN excluded.bio ELSE influencer_profiles.bio END,
          specialties=CASE WHEN excluded.specialties != '' THEN excluded.specialties ELSE influencer_profiles.specialties END,
          is_public=excluded.is_public,
          email=CASE WHEN excluded.email != '' THEN excluded.email ELSE influencer_profiles.email END,
          last_analysis=datetime('now')
        """,
        (
            user_mongo_id, blog_id, blog_url, golden_score, grade, grade_label,
            base_score, bp_score, ep_score, ca_score, rq_score, fr_score, sp_score,
            total_posts, total_visitors, total_subscribers,
            desired_rate, bio, specialties, is_public, email,
        ),
    )
    return cur.lastrowid or conn.execute(
        "SELECT profile_id FROM influencer_profiles WHERE user_mongo_id=?", (user_mongo_id,)
    ).fetchone()["profile_id"]


def get_influencer_profile(conn: sqlite3.Connection, user_mongo_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM influencer_profiles WHERE user_mongo_id=?", (user_mongo_id,)
    ).fetchone()
    return dict(row) if row else None


def get_influencer_by_blog_id(conn: sqlite3.Connection, blog_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM influencer_profiles WHERE blog_id=?", (blog_id,)
    ).fetchone()
    return dict(row) if row else None


def update_influencer_fields(
    conn: sqlite3.Connection,
    user_mongo_id: str,
    fields: Dict[str, Any],
) -> None:
    allowed = {"desired_rate", "bio", "specialties", "is_public"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(user_mongo_id)
    conn.execute(
        f"UPDATE influencer_profiles SET {', '.join(sets)} WHERE user_mongo_id=?",
        vals,
    )


def list_influencer_profiles(
    conn: sqlite3.Connection,
    offset: int = 0,
    limit: int = 20,
    min_score: float = 0,
    specialty: str = "",
) -> List[Dict[str, Any]]:
    sql = """
        SELECT profile_id, user_mongo_id, blog_id, blog_url, golden_score, grade, grade_label,
               base_score, bp_score, ep_score, ca_score, rq_score, fr_score, sp_score,
               total_posts, total_visitors, total_subscribers,
               desired_rate, bio, specialties, last_analysis
        FROM influencer_profiles
        WHERE is_public = 1 AND golden_score >= ?
    """
    params: list = [min_score]
    if specialty:
        sql += " AND specialties LIKE ?"
        params.append(f"%{specialty}%")
    sql += " ORDER BY golden_score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_influencer_profiles(conn: sqlite3.Connection, min_score: float = 0, specialty: str = "") -> int:
    sql = "SELECT COUNT(*) as cnt FROM influencer_profiles WHERE is_public=1 AND golden_score>=?"
    params: list = [min_score]
    if specialty:
        sql += " AND specialties LIKE ?"
        params.append(f"%{specialty}%")
    return conn.execute(sql, params).fetchone()["cnt"]


# ============================
# 매칭 CRUD
# ============================

def create_match(
    conn: sqlite3.Connection,
    owner_user_id: str,
    owner_display_name: str,
    influencer_user_id: str,
    influencer_blog_id: str,
    store_id: Optional[int] = None,
    campaign_type: str = "experience",
    message: str = "",
    offered_rate: int = 0,
    owner_email: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO matches(
          owner_user_id, owner_display_name, store_id,
          influencer_user_id, influencer_blog_id,
          campaign_type, message, offered_rate, owner_email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (owner_user_id, owner_display_name, store_id,
         influencer_user_id, influencer_blog_id,
         campaign_type, message, offered_rate, owner_email),
    )
    return int(cur.lastrowid)


def list_matches(
    conn: sqlite3.Connection,
    user_id: str,
    role: str = "sent",
    status: str = "",
) -> List[Dict[str, Any]]:
    if role == "received":
        sql = "SELECT * FROM matches WHERE influencer_user_id=?"
    else:
        sql = "SELECT * FROM matches WHERE owner_user_id=?"
    params: list = [user_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY requested_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_match(conn: sqlite3.Connection, match_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
    return dict(row) if row else None


def update_match_status(
    conn: sqlite3.Connection,
    match_id: int,
    status: str,
    decline_reason: str = "",
) -> None:
    valid = {"pending", "accepted", "declined", "completed", "cancelled"}
    if status not in valid:
        raise ValueError(f"유효하지 않은 상태: {status}")
    now = "datetime('now')"
    if status in ("accepted", "declined"):
        conn.execute(
            f"UPDATE matches SET status=?, decline_reason=?, responded_at={now} WHERE match_id=?",
            (status, decline_reason, match_id),
        )
    elif status == "completed":
        conn.execute(
            f"UPDATE matches SET status=?, completed_at={now} WHERE match_id=?",
            (status, match_id),
        )
    else:
        conn.execute("UPDATE matches SET status=? WHERE match_id=?", (status, match_id))


# ============================
# 알림 CRUD
# ============================

def create_notification(
    conn: sqlite3.Connection,
    user_id: str,
    ntype: str,
    title: str,
    message: str = "",
    link: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO notifications(user_id, type, title, message, link) VALUES (?, ?, ?, ?, ?)",
        (user_id, ntype, title, message, link),
    )
    return int(cur.lastrowid)


def list_notifications(conn: sqlite3.Connection, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_notification_read(conn: sqlite3.Connection, notif_id: int) -> None:
    conn.execute("UPDATE notifications SET is_read=1 WHERE notif_id=?", (notif_id,))


def count_unread_notifications(conn: sqlite3.Connection, user_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) as cnt FROM notifications WHERE user_id=? AND is_read=0",
        (user_id,),
    ).fetchone()["cnt"]


# ============================
# 서베이 CRUD
# ============================

def create_survey(conn: sqlite3.Connection, title: str, questions: str, target: str = "all") -> int:
    cur = conn.execute(
        "INSERT INTO surveys(title, questions, target) VALUES (?, ?, ?)",
        (title, questions, target),
    )
    return int(cur.lastrowid)


def list_surveys(conn: sqlite3.Connection, active_only: bool = True) -> List[Dict[str, Any]]:
    if active_only:
        rows = conn.execute("SELECT * FROM surveys WHERE is_active=1 ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM surveys ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_pending_surveys(conn: sqlite3.Connection, user_mongo_id: str) -> List[Dict[str, Any]]:
    """사용자가 아직 응답하지 않은 활성 설문 목록."""
    rows = conn.execute(
        """
        SELECT s.* FROM surveys s
        WHERE s.is_active = 1
          AND s.survey_id NOT IN (
            SELECT sr.survey_id FROM survey_responses sr WHERE sr.user_mongo_id = ?
          )
        ORDER BY s.created_at DESC
        """,
        (user_mongo_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def submit_survey_response(conn: sqlite3.Connection, survey_id: int, user_mongo_id: str, answers: str) -> int:
    cur = conn.execute(
        "INSERT INTO survey_responses(survey_id, user_mongo_id, answers) VALUES (?, ?, ?)",
        (survey_id, user_mongo_id, answers),
    )
    return int(cur.lastrowid)


def get_survey_responses(conn: sqlite3.Connection, survey_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM survey_responses WHERE survey_id=? ORDER BY created_at DESC",
        (survey_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_survey_active(conn: sqlite3.Connection, survey_id: int, is_active: bool) -> None:
    """설문 활성/비활성 토글."""
    conn.execute(
        "UPDATE surveys SET is_active=? WHERE survey_id=?",
        (1 if is_active else 0, survey_id),
    )


def get_influencer_email(conn: sqlite3.Connection, user_mongo_id: str) -> str:
    """인플루언서의 이메일 주소 반환. 없으면 빈 문자열."""
    row = conn.execute(
        "SELECT email FROM influencer_profiles WHERE user_mongo_id=?",
        (user_mongo_id,),
    ).fetchone()
    return row["email"] if row and row["email"] else ""
