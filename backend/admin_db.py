"""
광고/관리자/분석 SQLite DB — 6개 테이블 + CRUD 함수.

테이블: ads, ad_events, page_views, search_logs, user_events, daily_stats
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


# ────────────────────────────────────────────
# 스키마 / 초기화
# ────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ads (
    ad_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT NOT NULL DEFAULT '',
    contact_name    TEXT NOT NULL DEFAULT '',
    contact_phone   TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    image_url       TEXT NOT NULL DEFAULT '',
    link_url        TEXT NOT NULL DEFAULT '',
    cta_text        TEXT NOT NULL DEFAULT '자세히 보기',
    ad_type         TEXT NOT NULL DEFAULT 'native_card',
    placement       TEXT NOT NULL DEFAULT 'search_top',
    biz_types_json  TEXT NOT NULL DEFAULT '["all"]',
    regions_json    TEXT NOT NULL DEFAULT '[]',
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    billing_model   TEXT NOT NULL DEFAULT 'monthly',
    billing_amount  INTEGER NOT NULL DEFAULT 0,
    priority        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ad_events (
    ad_id        INTEGER NOT NULL,
    event_date   TEXT NOT NULL,
    impressions  INTEGER NOT NULL DEFAULT 0,
    clicks       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ad_id, event_date),
    FOREIGN KEY (ad_id) REFERENCES ads(ad_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS page_views (
    pv_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    section     TEXT NOT NULL DEFAULT 'dashboard',
    referrer    TEXT,
    user_agent  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pv_date ON page_views(created_at);

CREATE TABLE IF NOT EXISTS search_logs (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    region       TEXT NOT NULL,
    topic        TEXT,
    keyword      TEXT,
    store_name   TEXT,
    result_count INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sl_date ON search_logs(created_at);

CREATE TABLE IF NOT EXISTS user_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    event_data  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ue_date ON user_events(created_at);

CREATE TABLE IF NOT EXISTS daily_stats (
    stat_date       TEXT PRIMARY KEY,
    page_views      INTEGER NOT NULL DEFAULT 0,
    unique_sessions INTEGER NOT NULL DEFAULT 0,
    searches        INTEGER NOT NULL DEFAULT 0,
    blog_analyses   INTEGER NOT NULL DEFAULT 0,
    ad_impressions  INTEGER NOT NULL DEFAULT 0,
    ad_clicks       INTEGER NOT NULL DEFAULT 0,
    ad_revenue      INTEGER NOT NULL DEFAULT 0
);
"""


def init_admin_db(conn: sqlite3.Connection) -> None:
    """6개 테이블 + 인덱스 생성."""
    conn.executescript(_SCHEMA_SQL)


# ────────────────────────────────────────────
# 광고 CRUD
# ────────────────────────────────────────────

def create_ad(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
    cur = conn.execute(
        """INSERT INTO ads
           (company, contact_name, contact_phone,
            title, description, image_url, link_url, cta_text,
            ad_type, placement, biz_types_json, regions_json,
            start_date, end_date, is_active,
            billing_model, billing_amount, priority)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("company", ""),
            data.get("contact_name", ""),
            data.get("contact_phone", ""),
            data["title"],
            data.get("description", ""),
            data.get("image_url", ""),
            data.get("link_url", ""),
            data.get("cta_text", "자세히 보기"),
            data.get("ad_type", "native_card"),
            data.get("placement", "search_top"),
            json.dumps(data.get("biz_types", ["all"]), ensure_ascii=False),
            json.dumps(data.get("regions", []), ensure_ascii=False),
            data.get("start_date", date.today().isoformat()),
            data.get("end_date", (date.today() + timedelta(days=30)).isoformat()),
            1 if data.get("is_active", True) else 0,
            data.get("billing_model", "monthly"),
            data.get("billing_amount", 0),
            data.get("priority", 0),
        ),
    )
    conn.commit()
    return cur.lastrowid


def update_ad(conn: sqlite3.Connection, ad_id: int, data: Dict[str, Any]) -> None:
    sets: List[str] = []
    vals: List[Any] = []
    field_map = {
        "company": "company", "contact_name": "contact_name", "contact_phone": "contact_phone",
        "title": "title", "description": "description", "image_url": "image_url",
        "link_url": "link_url", "cta_text": "cta_text", "ad_type": "ad_type",
        "placement": "placement", "start_date": "start_date", "end_date": "end_date",
        "billing_model": "billing_model", "billing_amount": "billing_amount",
        "priority": "priority",
    }
    for key, col in field_map.items():
        if key in data:
            sets.append(f"{col}=?")
            vals.append(data[key])
    if "is_active" in data:
        sets.append("is_active=?")
        vals.append(1 if data["is_active"] else 0)
    if "biz_types" in data:
        sets.append("biz_types_json=?")
        vals.append(json.dumps(data["biz_types"], ensure_ascii=False))
    if "regions" in data:
        sets.append("regions_json=?")
        vals.append(json.dumps(data["regions"], ensure_ascii=False))
    if not sets:
        return
    vals.append(ad_id)
    conn.execute(f"UPDATE ads SET {', '.join(sets)} WHERE ad_id=?", vals)
    conn.commit()


def delete_ad(conn: sqlite3.Connection, ad_id: int) -> None:
    conn.execute("DELETE FROM ads WHERE ad_id=?", (ad_id,))
    conn.commit()


def _row_to_ad(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["_id"] = str(d["ad_id"])
    d["isActive"] = bool(d["is_active"])
    d["imageUrl"] = d["image_url"]
    d["linkUrl"] = d["link_url"]
    d["ctaText"] = d["cta_text"]
    d["type"] = d["ad_type"]
    d["advertiser"] = {
        "company": d["company"],
        "name": d["contact_name"],
        "phone": d["contact_phone"],
    }
    d["targeting"] = {
        "businessTypes": json.loads(d["biz_types_json"]),
        "regions": json.loads(d["regions_json"]),
    }
    d["billing"] = {
        "model": d["billing_model"],
        "amount": d["billing_amount"],
    }
    d["startDate"] = d["start_date"]
    d["endDate"] = d["end_date"]
    return d


def get_ad(conn: sqlite3.Connection, ad_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM ads WHERE ad_id=?", (ad_id,)).fetchone()
    if not row:
        return None
    ad = _row_to_ad(row)
    # 통계 추가
    stats = conn.execute(
        "SELECT COALESCE(SUM(impressions),0) as imp, COALESCE(SUM(clicks),0) as clk FROM ad_events WHERE ad_id=?",
        (ad_id,),
    ).fetchone()
    ad["stats"] = {"impressions": stats["imp"], "clicks": stats["clk"]}
    return ad


def list_ads(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM ads ORDER BY priority DESC, created_at DESC").fetchall()
    result = []
    for row in rows:
        ad = _row_to_ad(row)
        stats = conn.execute(
            "SELECT COALESCE(SUM(impressions),0) as imp, COALESCE(SUM(clicks),0) as clk FROM ad_events WHERE ad_id=?",
            (ad["ad_id"],),
        ).fetchone()
        ad["stats"] = {"impressions": stats["imp"], "clicks": stats["clk"]}
        result.append(ad)
    return result


def match_ads(
    conn: sqlite3.Connection,
    placement: str,
    biz_type: str = "all",
    region: str = "",
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """방문자에게 매칭되는 광고 반환."""
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT * FROM ads
           WHERE is_active = 1
             AND ? BETWEEN start_date AND end_date
             AND placement = ?
           ORDER BY priority DESC, created_at DESC""",
        (today, placement),
    ).fetchall()

    matched = []
    for row in rows:
        ad = _row_to_ad(row)
        biz_list = json.loads(row["biz_types_json"])
        region_list = json.loads(row["regions_json"])
        # 업종 매칭
        if "all" not in biz_list and biz_type and biz_type != "all":
            if not any(bt in biz_type or biz_type in bt for bt in biz_list):
                continue
        # 지역 매칭
        if region_list and region:
            if not any(r in region or region in r for r in region_list):
                continue
        matched.append(ad)
        if len(matched) >= limit:
            break
    return matched


# ────────────────────────────────────────────
# 광고 이벤트 (노출/클릭)
# ────────────────────────────────────────────

def record_impression(conn: sqlite3.Connection, ad_id: int) -> None:
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO ad_events (ad_id, event_date, impressions, clicks)
           VALUES (?, ?, 1, 0)
           ON CONFLICT(ad_id, event_date) DO UPDATE SET impressions = impressions + 1""",
        (ad_id, today),
    )
    conn.commit()


def record_click(conn: sqlite3.Connection, ad_id: int) -> Dict[str, Any]:
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO ad_events (ad_id, event_date, impressions, clicks)
           VALUES (?, ?, 0, 1)
           ON CONFLICT(ad_id, event_date) DO UPDATE SET clicks = clicks + 1""",
        (ad_id, today),
    )
    conn.commit()
    # 리다이렉트 URL 반환
    row = conn.execute("SELECT link_url FROM ads WHERE ad_id=?", (ad_id,)).fetchone()
    return {"redirectUrl": row["link_url"] if row else ""}


def get_ad_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    active = conn.execute("SELECT COUNT(*) as cnt FROM ads WHERE is_active=1").fetchone()["cnt"]
    totals = conn.execute(
        "SELECT COALESCE(SUM(impressions),0) as imp, COALESCE(SUM(clicks),0) as clk FROM ad_events"
    ).fetchone()
    imp = totals["imp"]
    clk = totals["clk"]
    ctr = round((clk / imp) * 100, 1) if imp > 0 else 0

    # 월별 수익 추정
    now = date.today()
    month_start = now.replace(day=1).isoformat()
    revenue = conn.execute(
        """SELECT COALESCE(SUM(a.billing_amount), 0) as rev
           FROM ads a WHERE a.is_active=1 AND a.start_date <= ? AND a.end_date >= ?""",
        (now.isoformat(), month_start),
    ).fetchone()["rev"]

    return {
        "activeCount": active,
        "totalImpressions": imp,
        "totalClicks": clk,
        "avgCtr": ctr,
        "monthlyRevenue": revenue,
    }


def get_ad_report(conn: sqlite3.Connection, ad_id: int) -> Dict[str, Any]:
    ad = get_ad(conn, ad_id)
    if not ad:
        return {}
    daily = conn.execute(
        "SELECT event_date, impressions, clicks FROM ad_events WHERE ad_id=? ORDER BY event_date DESC LIMIT 30",
        (ad_id,),
    ).fetchall()
    return {
        "ad": ad,
        "daily": [dict(r) for r in daily],
    }


# ────────────────────────────────────────────
# 분석 수집
# ────────────────────────────────────────────

def log_page_view(
    conn: sqlite3.Connection,
    session_id: str,
    section: str = "dashboard",
    referrer: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO page_views (session_id, section, referrer, user_agent) VALUES (?,?,?,?)",
        (session_id, section, referrer, user_agent),
    )
    conn.commit()


def log_search(
    conn: sqlite3.Connection,
    session_id: str,
    region: str,
    topic: Optional[str] = None,
    keyword: Optional[str] = None,
    store_name: Optional[str] = None,
    result_count: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO search_logs (session_id, region, topic, keyword, store_name, result_count) VALUES (?,?,?,?,?,?)",
        (session_id, region, topic, keyword, store_name, result_count),
    )
    conn.commit()


def log_event(
    conn: sqlite3.Connection,
    session_id: str,
    event_type: str,
    event_data: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO user_events (session_id, event_type, event_data) VALUES (?,?,?)",
        (session_id, event_type, event_data),
    )
    conn.commit()


# ────────────────────────────────────────────
# 통계 조회
# ────────────────────────────────────────────

def get_today_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    today = date.today().isoformat()
    pv = conn.execute(
        "SELECT COUNT(*) as cnt FROM page_views WHERE created_at >= ?", (today,)
    ).fetchone()["cnt"]
    searches = conn.execute(
        "SELECT COUNT(*) as cnt FROM search_logs WHERE created_at >= ?", (today,)
    ).fetchone()["cnt"]
    # 최근 5분 세션 수 → 추정 온라인
    five_min_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    online = conn.execute(
        "SELECT COUNT(DISTINCT session_id) as cnt FROM page_views WHERE created_at >= ?",
        (five_min_ago,),
    ).fetchone()["cnt"]

    return {
        "pageViews": pv,
        "searches": searches,
        "estimatedOnline": online,
    }


def get_hourly_stats(conn: sqlite3.Connection) -> List[int]:
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT CAST(strftime('%%H', created_at) AS INTEGER) as hr, COUNT(*) as cnt
           FROM page_views WHERE created_at >= ?
           GROUP BY hr ORDER BY hr""",
        (today,),
    ).fetchall()
    hourly = [0] * 24
    for r in rows:
        hourly[r["hr"]] = r["cnt"]
    return hourly


def get_range_stats(conn: sqlite3.Connection, days: int = 7) -> Dict[str, Any]:
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT DATE(created_at) as d,
                  COUNT(*) as pv,
                  COUNT(DISTINCT session_id) as sessions
           FROM page_views WHERE created_at >= ?
           GROUP BY d ORDER BY d""",
        (start,),
    ).fetchall()

    search_rows = conn.execute(
        """SELECT DATE(created_at) as d, COUNT(*) as cnt
           FROM search_logs WHERE created_at >= ?
           GROUP BY d ORDER BY d""",
        (start,),
    ).fetchall()
    search_map = {r["d"]: r["cnt"] for r in search_rows}

    data = []
    total_pv = 0
    total_searches = 0
    for r in rows:
        s = search_map.get(r["d"], 0)
        data.append({
            "date": r["d"],
            "pageViews": r["pv"],
            "searches": s,
            "newUsers": 0,
        })
        total_pv += r["pv"]
        total_searches += s

    return {
        "data": data,
        "totals": {"pageViews": total_pv, "searches": total_searches, "newUsers": 0},
    }


def get_popular_searches(conn: sqlite3.Connection, days: int = 7) -> Dict[str, Any]:
    start = (date.today() - timedelta(days=days)).isoformat()
    regions = conn.execute(
        """SELECT region as name, COUNT(*) as count
           FROM search_logs WHERE created_at >= ? AND region != ''
           GROUP BY region ORDER BY count DESC LIMIT 10""",
        (start,),
    ).fetchall()
    topics = conn.execute(
        """SELECT COALESCE(topic, keyword) as name, COUNT(*) as count
           FROM search_logs WHERE created_at >= ? AND COALESCE(topic, keyword, '') != ''
           GROUP BY name ORDER BY count DESC LIMIT 10""",
        (start,),
    ).fetchall()
    return {
        "topRegions": [dict(r) for r in regions],
        "topTopics": [dict(r) for r in topics],
    }


def get_recent_searches(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT session_id, region, topic, keyword, store_name, result_count, created_at as time
           FROM search_logs ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_events(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT session_id, event_type as event, event_data, created_at as time
           FROM user_events ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_user_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    """세션 기반 사용자 통계 (OAuth 없이)."""
    total = conn.execute("SELECT COUNT(DISTINCT session_id) as cnt FROM page_views").fetchone()["cnt"]
    today = date.today().isoformat()
    new_today = conn.execute(
        """SELECT COUNT(DISTINCT session_id) as cnt FROM page_views
           WHERE created_at >= ? AND session_id NOT IN
             (SELECT DISTINCT session_id FROM page_views WHERE created_at < ?)""",
        (today, today),
    ).fetchone()["cnt"]
    return {
        "total": total,
        "newToday": new_today,
        "byProvider": [],
        "recentUsers": [],
    }


# ────────────────────────────────────────────
# 일별 집계
# ────────────────────────────────────────────

def refresh_daily_stats(conn: sqlite3.Connection, stat_date: Optional[str] = None) -> None:
    d = stat_date or date.today().isoformat()
    pv = conn.execute(
        "SELECT COUNT(*) as cnt FROM page_views WHERE DATE(created_at)=?", (d,)
    ).fetchone()["cnt"]
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT session_id) as cnt FROM page_views WHERE DATE(created_at)=?", (d,)
    ).fetchone()["cnt"]
    searches = conn.execute(
        "SELECT COUNT(*) as cnt FROM search_logs WHERE DATE(created_at)=?", (d,)
    ).fetchone()["cnt"]
    ad_imp = conn.execute(
        "SELECT COALESCE(SUM(impressions),0) as cnt FROM ad_events WHERE event_date=?", (d,)
    ).fetchone()["cnt"]
    ad_clk = conn.execute(
        "SELECT COALESCE(SUM(clicks),0) as cnt FROM ad_events WHERE event_date=?", (d,)
    ).fetchone()["cnt"]

    conn.execute(
        """INSERT INTO daily_stats (stat_date, page_views, unique_sessions, searches, ad_impressions, ad_clicks)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(stat_date) DO UPDATE SET
             page_views=?, unique_sessions=?, searches=?, ad_impressions=?, ad_clicks=?""",
        (d, pv, sessions, searches, ad_imp, ad_clk, pv, sessions, searches, ad_imp, ad_clk),
    )
    conn.commit()


# ────────────────────────────────────────────
# 정리
# ────────────────────────────────────────────

def cleanup_old_analytics(conn: sqlite3.Connection, keep_days: int = 90) -> Dict[str, int]:
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    pv = conn.execute("DELETE FROM page_views WHERE created_at < ?", (cutoff,)).rowcount
    sl = conn.execute("DELETE FROM search_logs WHERE created_at < ?", (cutoff,)).rowcount
    ue = conn.execute("DELETE FROM user_events WHERE created_at < ?", (cutoff,)).rowcount
    conn.commit()
    return {"page_views_deleted": pv, "search_logs_deleted": sl, "user_events_deleted": ue}
