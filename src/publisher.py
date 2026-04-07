"""Publish newsletter to Telegram and Facebook."""
import html
import logging
import re
import httpx

from .config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN,
)

log = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FACEBOOK_API = "https://graph.facebook.com/v19.0"
TELEGRAM_CAPTION_LIMIT = 1024


def _telegram_request(method: str, payload: dict) -> dict:
    resp = httpx.post(f"{TELEGRAM_API}/{method}", json=payload, timeout=30)
    data = resp.json()
    if not resp.is_success:
        description = data.get("description", resp.text)
        raise httpx.HTTPStatusError(
            f"Telegram API error on {method}: {description}",
            request=resp.request,
            response=resp,
        )
    return data


def _short_caption(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) > TELEGRAM_CAPTION_LIMIT:
        return first_line[: TELEGRAM_CAPTION_LIMIT - 1].rstrip() + "…"
    return first_line


def _markdown_to_telegram_html(text: str) -> str:
    placeholders: list[str] = []

    def stash(replacement: str) -> str:
        placeholders.append(replacement)
        return f"__HTML_PLACEHOLDER_{len(placeholders) - 1}__"

    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: stash(f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(m.group(1))}</a>'),
        text,
    )
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: stash(f"<b>{html.escape(m.group(1))}</b>"),
        text,
        flags=re.DOTALL,
    )
    escaped = html.escape(text)
    for idx, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"__HTML_PLACEHOLDER_{idx}__", replacement)
    return escaped


def post_telegram(text: str, photo_url: str | None = None) -> str:
    """Returns message_id string."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        log.info("Telegram not configured — skipping publish")
        return ""

    if photo_url:
        photo_data = _telegram_request(
            "sendPhoto",
            {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "photo": photo_url,
                "caption": _short_caption(text),
            },
        )
        data = _telegram_request(
            "sendMessage",
            {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": _markdown_to_telegram_html(text),
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )
        log.info(
            "Posted photo to Telegram, photo_message_id=%s",
            photo_data["result"]["message_id"],
        )
    else:
        data = _telegram_request(
            "sendMessage",
            {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": _markdown_to_telegram_html(text),
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )

    msg_id = str(data["result"]["message_id"])
    log.info("Posted to Telegram, message_id=%s", msg_id)
    return msg_id


def get_telegram_stats(message_id: str) -> dict:
    """
    Telegram Bot API does not expose view counts for channel posts.
    Views are only available via Telegram Stats for large channels.
    We store what we can: reactions via getMessageReactions (Bot API 7.x).
    """
    try:
        resp = httpx.post(
            f"{TELEGRAM_API}/getMessageReactionCount",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "message_id": int(message_id)},
            timeout=15,
        )
        if resp.status_code == 200:
            reactions = resp.json().get("result", {}).get("reactions", [])
            total = sum(r.get("count", 0) for r in reactions)
            return {"tg_reactions": total, "tg_views": 0}
    except Exception as exc:
        log.warning("Failed to fetch Telegram stats: %s", exc)
    return {"tg_reactions": 0, "tg_views": 0}


def post_facebook(text: str, photo_url: str | None = None) -> str:
    """Returns post_id string."""
    if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_TOKEN:
        log.info("Facebook not configured — skipping publish")
        return ""

    if photo_url:
        resp = httpx.post(
            f"{FACEBOOK_API}/{FACEBOOK_PAGE_ID}/photos",
            params={
                "url": photo_url,
                "caption": text,
                "access_token": FACEBOOK_PAGE_TOKEN,
            },
            timeout=30,
        )
    else:
        resp = httpx.post(
            f"{FACEBOOK_API}/{FACEBOOK_PAGE_ID}/feed",
            params={
                "message": text,
                "access_token": FACEBOOK_PAGE_TOKEN,
            },
            timeout=30,
        )

    resp.raise_for_status()
    post_id = resp.json().get("id", "")
    log.info("Posted to Facebook, post_id=%s", post_id)
    return post_id


def get_facebook_stats(post_id: str) -> dict:
    try:
        resp = httpx.get(
            f"{FACEBOOK_API}/{post_id}",
            params={
                "fields": "likes.summary(true),comments.summary(true),shares",
                "access_token": FACEBOOK_PAGE_TOKEN,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "fb_likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
                "fb_comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
                "fb_shares": data.get("shares", {}).get("count", 0),
            }
    except Exception as exc:
        log.warning("Failed to fetch Facebook stats: %s", exc)
    return {"fb_likes": 0, "fb_comments": 0, "fb_shares": 0}
