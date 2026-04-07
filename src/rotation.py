"""
Category priority manager.
Primary source: Google Sheets (category_stats tab).
Fallback: local rotation.json when Sheets not configured.
"""
import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

ROTATION_FILE = os.path.join(os.path.dirname(__file__), "..", "rotation.json")


def get_category_priorities() -> list[str]:
    """Return categories sorted by priority, highest first."""
    from .tracker import _sheets_configured, get_category_priorities as sheets_priorities
    if _sheets_configured():
        return sheets_priorities()
    return _local_priorities()


def record(category: str, topic_slug: str) -> None:
    """Backup record to local JSON (Sheets is the primary record)."""
    history = _load_local()
    history.append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "category": category,
        "topic_slug": topic_slug,
    })
    _save_local(history)


def _local_priorities() -> list[str]:
    """Compute priorities from local rotation.json when Sheets unavailable."""
    from .config import CATEGORIES
    from collections import Counter
    history = _load_local()
    counts = Counter(e["category"] for e in history)
    last_cat = history[-1]["category"] if history else ""

    def score(cat):
        if cat == last_cat:
            return 9999
        return counts.get(cat, 0)

    return sorted(CATEGORIES, key=score)


def _load_local() -> list[dict]:
    try:
        with open(ROTATION_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_local(history: list[dict]) -> None:
    with open(ROTATION_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
