"""Fetch articles from all RSS feeds."""
import logging
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from html import unescape

import feedparser
import httpx

from .config import RSS_FEEDS

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 15  # seconds
MAX_AGE_HOURS = 36  # ignore articles older than this


@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: datetime
    source_category: str  # feed-level hint, not final classification
    source_name: str


def _clean_text(value: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_summary(entry) -> str:
    candidates: list[str] = []

    for attr in ("summary", "description"):
        value = entry.get(attr, "")
        if value:
            candidates.append(value)

    for item in entry.get("content", []) or []:
        if isinstance(item, dict):
            value = item.get("value", "")
            if value:
                candidates.append(value)

    for raw in candidates:
        cleaned = _clean_text(raw)
        if len(cleaned) >= 40:
            return cleaned[:800]

    return ""


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_all() -> list[Article]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    articles: list[Article] = []

    for source_category, url in RSS_FEEDS:
        try:
            resp = httpx.get(url, timeout=FETCH_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": "BalticBusinessClub-Newsletter/1.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            source_name = feed.feed.get("title", url)

            for entry in feed.entries:
                pub = _parse_date(entry)
                if pub < cutoff:
                    continue
                title = _clean_text(entry.get("title", ""))
                summary = _extract_summary(entry)
                url = entry.get("link", "")
                if not title or not url or not summary:
                    continue
                articles.append(Article(
                    title=title,
                    url=url,
                    summary=summary,
                    published=pub,
                    source_category=source_category,
                    source_name=source_name,
                ))

            log.info("Fetched %d articles from %s", len(feed.entries), source_name)
        except Exception as exc:
            log.warning("Failed to fetch %s: %s", url, exc)

    articles.sort(key=lambda a: a.published, reverse=True)
    log.info("Total articles collected: %d", len(articles))
    return articles
