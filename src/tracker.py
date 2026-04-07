"""Google Sheets read/write for deduplication and analytics."""
import logging
from collections import Counter
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from .config import GOOGLE_SHEETS_SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, CATEGORIES

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NEWSLETTERS = "newsletters"
SHEET_STATS = "category_stats"

COLUMNS = [
    "date", "topic_slug", "category", "headline_ru", "source_urls",
    "telegram_msg_id", "facebook_post_id",
    "tg_views", "tg_reactions", "fb_likes", "fb_comments", "fb_shares",
    "engagement_score",
]
STATS_COLUMNS = ["category", "total_posts", "last_posted", "avg_engagement_score", "priority"]


def _sheets_configured() -> bool:
    return bool(GOOGLE_SHEETS_SPREADSHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON)


def _spreadsheet():
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID)


def _get_or_create(ss, name: str, cols: list[str]):
    try:
        return ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(name, rows=1000, cols=len(cols))
        ws.append_row(cols)
        return ws


def get_recent_categories(n: int = 3) -> list[str]:
    """Return categories of the last n newsletters (for rotation)."""
    if not _sheets_configured():
        return []
    try:
        ws = _get_or_create(_spreadsheet(), SHEET_NEWSLETTERS, COLUMNS)
        rows = ws.get_all_records()
        return [r["category"] for r in rows if r.get("category")][-n:]
    except Exception as exc:
        log.warning("Could not read recent categories: %s", exc)
        return []


def get_recent_slugs(n: int = 5) -> list[str]:
    """Return slugs of the last n newsletters in chronological order."""
    if not _sheets_configured():
        from .rotation import _load_local
        history = _load_local()
        return [e["topic_slug"] for e in history if e.get("topic_slug")][-n:]
    try:
        ws = _get_or_create(_spreadsheet(), SHEET_NEWSLETTERS, COLUMNS)
        rows = ws.get_all_records()
        return [r["topic_slug"] for r in rows if r.get("topic_slug")][-n:]
    except Exception as exc:
        log.warning("Could not read recent slugs: %s", exc)
        return []


def get_sent_slugs() -> set[str]:
    if not _sheets_configured():
        return set()
    try:
        ws = _get_or_create(_spreadsheet(), SHEET_NEWSLETTERS, COLUMNS)
        rows = ws.get_all_records()
        return {r["topic_slug"] for r in rows if r.get("topic_slug")}
    except Exception as exc:
        log.warning("Could not read sent slugs: %s", exc)
        return set()


def append_newsletter(
    *,
    topic_slug: str,
    category: str,
    headline_ru: str,
    source_urls: list[str],
    telegram_msg_id: str = "",
    facebook_post_id: str = "",
) -> None:
    if not _sheets_configured():
        return
    ss = _spreadsheet()
    ws = _get_or_create(ss, SHEET_NEWSLETTERS, COLUMNS)
    ws.append_row([
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        topic_slug,
        category,
        headline_ru,
        ", ".join(source_urls),
        telegram_msg_id,
        facebook_post_id,
        "", "", "", "", "", "",
    ])
    log.info("Logged newsletter '%s' to Google Sheets", topic_slug)
    _refresh_category_stats(ss)


def update_stats(
    *,
    topic_slug: str,
    tg_views: int = 0,
    tg_reactions: int = 0,
    fb_likes: int = 0,
    fb_comments: int = 0,
    fb_shares: int = 0,
) -> None:
    if not _sheets_configured():
        return
    try:
        ss = _spreadsheet()
        ws = _get_or_create(ss, SHEET_NEWSLETTERS, COLUMNS)
        rows = ws.get_all_records()
        for i, row in enumerate(rows, start=2):
            if row.get("topic_slug") == topic_slug:
                score = (tg_reactions * 3 + fb_likes + fb_comments * 5 + fb_shares * 4) / max(tg_views, 1)
                ws.update(f"H{i}:M{i}", [[
                    tg_views, tg_reactions, fb_likes,
                    fb_comments, fb_shares, round(score, 4),
                ]])
                log.info("Updated stats for '%s'", topic_slug)
                _refresh_category_stats(ss)
                return
        log.warning("topic_slug '%s' not found for stats update", topic_slug)
    except Exception as exc:
        log.warning("Could not update stats: %s", exc)


def get_category_priorities() -> list[str]:
    """Return categories sorted by priority (index 0 = highest).
    Falls back to CATEGORIES order if Sheets not configured."""
    if not _sheets_configured():
        return list(CATEGORIES)
    try:
        ss = _spreadsheet()
        stats_ws = _get_or_create(ss, SHEET_STATS, STATS_COLUMNS)
        rows = stats_ws.get_all_records()
        if not rows:
            return list(CATEGORIES)
        sorted_rows = sorted(rows, key=lambda r: int(r.get("priority", 99)))
        return [r["category"] for r in sorted_rows if r.get("category")]
    except Exception as exc:
        log.warning("Could not read category priorities: %s", exc)
        return list(CATEGORIES)


def _refresh_category_stats(ss) -> None:
    """Recompute category_stats tab and recalculate priorities."""
    try:
        nl_ws = _get_or_create(ss, SHEET_NEWSLETTERS, COLUMNS)
        rows = nl_ws.get_all_records()

        counts: Counter = Counter()
        last_posted: dict[str, str] = {}
        scores: dict[str, list[float]] = {}
        last_category = ""

        for r in rows:
            cat = r.get("category", "")
            if not cat:
                continue
            counts[cat] += 1
            date = r.get("date", "")
            if date > last_posted.get(cat, ""):
                last_posted[cat] = date
            score = r.get("engagement_score")
            if score:
                scores.setdefault(cat, []).append(float(score))
            last_category = cat  # last row = most recent post

        # Priority = rank by ascending post count (fewest posts = highest priority)
        # Last posted category always goes to bottom regardless of count
        max_posts = max(counts.values(), default=0)

        def priority_score(cat: str) -> int:
            if cat == last_category:
                return 9999  # always last
            return counts.get(cat, 0)  # fewer posts = lower score = higher priority

        sorted_cats = sorted(CATEGORIES, key=priority_score)
        priority_rank = {cat: i + 1 for i, cat in enumerate(sorted_cats)}

        stats_ws = _get_or_create(ss, SHEET_STATS, STATS_COLUMNS)
        stats_ws.clear()
        stats_ws.append_row(STATS_COLUMNS)

        for cat in sorted_cats:
            total = counts.get(cat, 0)
            last = last_posted.get(cat, "—")
            avg_score = round(sum(scores.get(cat, [0])) / max(len(scores.get(cat, [])), 1), 4)
            priority = priority_rank[cat]
            stats_ws.append_row([cat, total, last, avg_score, priority])

        log.info("category_stats refreshed. Priority order: %s", sorted_cats)
    except Exception as exc:
        log.warning("Could not refresh category stats: %s", exc)
