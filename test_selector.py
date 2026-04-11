"""
Test topic selection only (Ollama) — no OpenAI calls, no publishing.

Usage:
  python test_selector.py
"""
import logging
import sys

sys.path.insert(0, ".")

from src import ollama_manager
from src.collector import fetch_all
from src.selector import select_topic
from src.tracker import get_recent_categories, get_sent_slugs, get_recent_slugs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

try:
    ollama_manager.start()
    ollama_manager.ensure_model()

    log.info("Collecting articles...")
    articles = fetch_all()
    log.info("Collected %d articles total", len(articles))

    sent_slugs = get_sent_slugs()
    recent_categories = get_recent_categories(n=2)
    recent_slugs = get_recent_slugs(n=5)

    log.info("Recent categories: %s", recent_categories or "none")
    log.info("Recent slugs:      %s", recent_slugs or "none")

    topic = select_topic(articles, sent_slugs, recent_categories, recent_slugs)

    print("\n" + "=" * 60)
    print(f"Category:  {topic.category}")
    print(f"Slug:      {topic.topic_slug}")
    print(f"Breaking:  {topic.is_breaking}")
    print(f"Articles:  {len(topic.articles)}")
    for a in topic.articles[:3]:
        print(f"  - {a.title} ({a.source_name})")
    print("=" * 60)

finally:
    ollama_manager.stop()
