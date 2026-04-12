"""
Main entrypoint.

Usage:
  python -m src.main               # full run (publish + track)
  python -m src.main --dry-run     # generate only, print to stdout, no publish/track
"""
import argparse
import logging
import sys

from . import ollama_manager
from .collector import fetch_all
from .config import SEND_UNSPLASH_PHOTO
from .generator import generate
from .photo_fetcher import fetch_photo_for_topic, save_photo
from .publisher import post_telegram, post_facebook, get_telegram_stats, get_facebook_stats
from .rotation import record as rotation_record
from .selector import select_topic
from .tracker import (
    get_recent_categories, get_sent_slugs, get_recent_slugs,
    append_newsletter, update_stats,
    _sheets_configured,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def main(dry_run: bool = False) -> None:
    try:
        # 1. Start Ollama
        ollama_manager.start()
        ollama_manager.ensure_model()

        # 2. Update stats for previous post (only if tracking configured)
        if _sheets_configured():
            _update_previous_stats()

        # 3. Collect news
        log.info("Collecting articles...")
        articles = fetch_all()
        if not articles:
            log.error("No articles collected — aborting")
            sys.exit(1)
        log.info("Collected %d articles total", len(articles))

        # 4. Load tracking data (empty defaults if sheets not configured)
        sent_slugs = get_sent_slugs()
        recent_categories = get_recent_categories(n=2)
        recent_slugs = get_recent_slugs(n=5)
        log.info("Recent categories (for rotation): %s", recent_categories or "none")
        log.info("Recent slugs (for topic dedup): %s", recent_slugs or "none")

        # 5. Select topic
        topic = select_topic(articles, sent_slugs, recent_categories, recent_slugs)
        log.info(
            "Selected: [%s] %s  breaking=%s",
            topic.category, topic.topic_slug, topic.is_breaking,
        )

        if topic.topic_slug in sent_slugs:
            log.warning("Topic '%s' already sent — skipping", topic.topic_slug)
            sys.exit(0)

        # 8a. Dry-run: print selected topic only, no generation
        if dry_run:
            print("\n" + "=" * 70)
            print(f"Category:  {topic.category}")
            print(f"Slug:      {topic.topic_slug}")
            print(f"Breaking:  {topic.is_breaking}")
            print(f"Articles:  {len(topic.articles)}")
            for a in topic.articles[:5]:
                print(f"  - {a.title} ({a.source_name})")
            print("=" * 70)
            log.info("Dry-run complete — topic selected, no newsletter generated")
            return

        # 6. Generate newsletter text
        newsletter = generate(topic)
        if newsletter.topic_slug:
            topic.topic_slug = newsletter.topic_slug

        # 7. Fetch photo
        photo = None
        photo_url = None
        credit = ""
        if SEND_UNSPLASH_PHOTO:
            photo = fetch_photo_for_topic(topic.topic_slug, topic.category)
            photo_url = photo["url"] if photo else None
            credit = photo["credit"] if photo else ""

        full_text = newsletter.text
        if credit:
            full_text += f"\n\n{credit}"

        # 8b. Publish
        tg_msg_id = post_telegram(full_text, photo_url)
        fb_post_id = post_facebook(full_text, photo_url)

        # 9. Track
        if _sheets_configured():
            append_newsletter(
                topic_slug=topic.topic_slug,
                category=topic.category,
                headline_ru=newsletter.headline_ru,
                source_urls=newsletter.source_urls,
                telegram_msg_id=tg_msg_id,
                facebook_post_id=fb_post_id,
            )
        else:
            log.info("Google Sheets not configured — skipping tracking")

        rotation_record(topic.category, topic.topic_slug)
        log.info("Done. Newsletter '%s' published.", topic.topic_slug)

    finally:
        ollama_manager.stop()


def _update_previous_stats() -> None:
    """Pull engagement stats for the most recent published newsletter."""
    try:
        from .config import GOOGLE_SHEETS_SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON
        import gspread
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        ws = gc.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID).worksheet("newsletters")
        rows = ws.get_all_records()
        if not rows:
            return

        last = rows[-1]
        slug = last.get("topic_slug", "")
        tg_id = last.get("telegram_msg_id", "")
        fb_id = last.get("facebook_post_id", "")
        if not slug:
            return

        tg_stats = get_telegram_stats(tg_id) if tg_id else {}
        fb_stats = get_facebook_stats(fb_id) if fb_id else {}

        update_stats(
            topic_slug=slug,
            tg_views=tg_stats.get("tg_views", 0),
            tg_reactions=tg_stats.get("tg_reactions", 0),
            fb_likes=fb_stats.get("fb_likes", 0),
            fb_comments=fb_stats.get("fb_comments", 0),
            fb_shares=fb_stats.get("fb_shares", 0),
        )
    except Exception as exc:
        log.warning("Could not update previous stats: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baltic Business Club Newsletter Generator")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate and print newsletter without publishing or tracking",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
