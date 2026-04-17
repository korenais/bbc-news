"""Pick the best topic using Ollama, respecting category rotation."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import httpx
import os

from .collector import Article
from .config import OLLAMA_HOST, OLLAMA_MODEL, BREAKING_NEWS_SOURCE_THRESHOLD, CATEGORIES

log = logging.getLogger(__name__)


@dataclass
class SelectedTopic:
    articles: list[Article]      # all articles about this topic (1+)
    category: str
    topic_slug: str              # short English slug
    is_breaking: bool = False


def _load_selector_prompt() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "selector_prompt.txt")
    with open(os.path.abspath(path), encoding="utf-8") as f:
        return f.read()


def _ollama(prompt: str) -> str:
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "it", "its", "this", "that", "and", "or", "but", "not", "has", "have",
    "had", "will", "would", "could", "should", "may", "might", "new", "says",
    "say", "said", "after", "over", "up", "how", "what", "why", "who",
    "more", "than", "into", "about", "his", "her", "their", "he", "she",
    "times", "news", "report", "latest", "top", "world",
}


def _group_by_topic(articles: list[Article]) -> list[list[Article]]:
    """
    Group articles that share 4+ meaningful keywords in their titles.
    Stopwords are excluded to avoid false matches like 'Times', 'News', etc.
    """
    def key_words(title: str) -> frozenset:
        words = re.sub(r"[^a-zA-Z0-9 ]", "", title.lower()).split()
        return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 2)

    groups: list[list[Article]] = []
    for article in articles:
        kw = key_words(article.title)
        matched = False
        for group in groups:
            if len(kw & key_words(group[0].title)) >= 4:
                group.append(article)
                matched = True
                break
        if not matched:
            groups.append([article])

    return sorted(groups, key=len, reverse=True)


def _is_breaking(group: list[Article]) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [a for a in group if a.published >= cutoff]
    return len(recent) >= BREAKING_NEWS_SOURCE_THRESHOLD


def _guess_category(group: list[Article]) -> str:
    """Map source_category hint to a proper CATEGORIES value.
    Prefers specific categories (technology, finance, baltic) over the
    generic 'geopolitics' fallback used for general news sources."""
    mapping = {
        "technology": "technology",
        "finance": "finance",
        "baltic": "baltic",
        "general": "geopolitics",  # broad default for general sources
    }
    categories = [mapping.get(a.source_category, "geopolitics") for a in group]
    for cat in categories:
        if cat != "geopolitics":
            return cat
    return "geopolitics"


def select_topic(
    articles: list[Article],
    sent_slugs: set[str],
    recent_categories: list[str],  # kept for API compat
    recent_slugs: list[str] | None = None,
) -> SelectedTopic:
    groups = _group_by_topic(articles)
    last_category = recent_categories[-1] if recent_categories else None
    categories = [c for c in CATEGORIES if c != last_category] + ([last_category] if last_category else [])

    # Assign a flat index to each group (used by Ollama to reference them)
    # Breaking news groups get their own section at the top
    # Last category is excluded here too — no back-to-back even for breaking news
    eligible_categories = [c for c in categories if c != last_category]
    breaking_groups = [g for g in groups if _is_breaking(g) and _guess_category(g) in eligible_categories]
    normal_groups = [g for g in groups if not _is_breaking(g)]

    # Build per-category buckets (normal groups only, up to 5 per category)
    buckets: dict[str, list[tuple[int, list[Article]]]] = {cat: [] for cat in eligible_categories}
    flat_list: list[list[Article]] = []

    # Breaking first
    for g in breaking_groups:
        flat_list.append(g)

    # Normal groups bucketed by category (last_category excluded entirely)
    for g in normal_groups:
        cat = _guess_category(g)
        if cat in buckets and len(buckets[cat]) < 5:
            buckets[cat].append((len(flat_list), g))
            flat_list.append(g)

    log.info("Eligible categories: %s", eligible_categories)

    # Build prompt sections
    breaking_section = ""
    if breaking_groups:
        lines = []
        for i, g in enumerate(breaking_groups):
            titles = " | ".join(a.title for a in g[:3])
            sources = list({a.source_name for a in g})
            lines.append(f'  [{i}] {titles}\n      sources: {", ".join(sources)}')
        breaking_section = "BREAKING NEWS (pick immediately if highly relevant):\n" + "\n".join(lines) + "\n\n"

    category_sections = []
    for cat in eligible_categories:
        items = buckets.get(cat, [])
        if not items:
            continue
        lines = []
        for idx, g in items:
            titles = " | ".join(a.title for a in g[:3])
            sources = list({a.source_name for a in g})
            lines.append(f'  [{idx}] {titles}\n      sources: {", ".join(sources)}')
        category_sections.append(f"## {cat.upper()}\n" + "\n".join(lines))

    log.info(
        "Candidates per category: %s",
        {cat: len(buckets[cat]) for cat in eligible_categories},
    )

    recent_topics_block = ""
    if recent_slugs:
        slugs_fmt = ", ".join(recent_slugs)
        recent_topics_block = f"RECENTLY PUBLISHED (do not cover the same story again, even from a different angle): {slugs_fmt}\n\n"

    prompt_template = _load_selector_prompt()
    prompt = (
        prompt_template
        .replace("{recent_topics_block}", recent_topics_block)
        .replace("{breaking_section}", breaking_section)
        .replace("{category_sections}", "\n".join(category_sections))
    )

    raw = _ollama(prompt)
    log.debug("Ollama selector response: %s", raw)

    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not parse selector JSON from: {raw}")
    result = json.loads(match.group())
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object, got: {type(result)}")

    idx = int(result["index"])
    selected_group = flat_list[idx]
    category = _guess_category(selected_group)

    log.info("Selected group index=%d category=%s title=%s", idx, category, selected_group[0].title[:60])

    return SelectedTopic(
        articles=selected_group,
        category=category,
        topic_slug=result["topic_slug"],
        is_breaking=_is_breaking(selected_group),
    )
