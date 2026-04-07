"""Generate Russian newsletter text via OpenAI (preferred) or Ollama (fallback)."""
import logging
import os
import re
from dataclasses import dataclass

import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL, OPENAI_API_KEY, OPENAI_MODEL
from .selector import SelectedTopic

log = logging.getLogger(__name__)


@dataclass
class Newsletter:
    text: str          # full Telegram/Facebook post in Russian
    headline_ru: str   # extracted headline for tracking
    source_urls: list[str]
    topic_slug: str = ""  # slug derived from Russian headline


def _load_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompt.txt")
    with open(os.path.abspath(prompt_path), encoding="utf-8") as f:
        return f.read()


def _generate_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def _generate_ollama(prompt: str) -> str:
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def generate(topic: SelectedTopic) -> Newsletter:
    articles = topic.articles[:5]  # limit context
    sources_block = "\n".join(
        f"- {a.title} ({a.source_name}): {a.url}\n  Summary: {a.summary}"
        for a in articles
    )
    source_urls = [a.url for a in articles]

    breaking_note = "СРОЧНО: экстренная новость — отрази срочность в заголовке и интро.\n" if topic.is_breaking else ""

    prompt_template = _load_prompt()
    prompt = prompt_template.replace("{sources_block}", sources_block).replace("{breaking_note}", breaking_note)

    if OPENAI_API_KEY:
        text = _generate_openai(prompt)
    else:
        text = _generate_ollama(prompt)

    # First non-empty line is the headline (strip bold markers for clean storage)
    headline_ru = re.sub(r"^\*\*|\*\*$", "", next((l.strip() for l in text.splitlines() if l.strip()), topic.topic_slug))

    # Derive English slug from the actual source article titles used by GPT
    slug = _slug_from_titles([a.title for a in articles]) or topic.topic_slug

    log.info("Newsletter generated: %s", headline_ru)
    return Newsletter(text=text, headline_ru=headline_ru, source_urls=source_urls, topic_slug=slug)


_SLUG_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to",
    "of", "for", "and", "or", "but", "with", "as", "by", "from", "its",
    "it", "this", "that", "how", "what", "why", "who", "over", "up",
}


def _slug_from_titles(titles: list[str]) -> str:
    """Build a 4-5 word English slug from the most common meaningful words across titles."""
    all_words: list[str] = []
    for title in titles:
        words = re.sub(r"[^a-zA-Z0-9 ]", "", title.lower()).split()
        all_words.extend(w for w in words if w not in _SLUG_STOPWORDS and len(w) > 2)

    # Pick top words by frequency, preserving first-appearance order
    seen: dict[str, int] = {}
    for w in all_words:
        seen[w] = seen.get(w, 0) + 1
    top = sorted(seen, key=lambda w: -seen[w])[:5]
    # Restore natural title order
    ordered = [w for w in all_words if w in top and top.__contains__(w)]
    unique: list[str] = []
    for w in ordered:
        if w not in unique:
            unique.append(w)
        if len(unique) == 5:
            break
    return "-".join(unique)
