"""Fetch a relevant free photo from Unsplash."""
import logging
import os
import httpx

from .config import UNSPLASH_ACCESS_KEY

log = logging.getLogger(__name__)

UNSPLASH_API = "https://api.unsplash.com"
CATEGORY_FALLBACK_QUERIES = {
    "technology": ["technology", "cybersecurity", "data center"],
    "finance": ["finance", "stock market", "business"],
    "real_estate": ["real estate", "construction", "commercial property"],
    "industry": ["manufacturing", "factory", "logistics"],
    "geopolitics": ["global trade", "shipping", "economy"],
    "baltic": ["Tallinn", "Baltic business", "Europe skyline"],
}


def fetch_photo(query: str) -> dict | None:
    """
    Returns dict with keys: url (download URL), credit (attribution string).
    Returns None if no suitable photo found.
    """
    try:
        resp = httpx.get(
            f"{UNSPLASH_API}/search/photos",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            log.warning("No Unsplash photos found for query: %s", query)
            return None

        photo = results[0]
        # Trigger download tracking as required by Unsplash API guidelines
        httpx.get(photo["links"]["download_location"],
                  headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                  timeout=10)

        author = photo["user"]["name"]
        author_url = photo["user"]["links"]["html"]
        return {
            "url": photo["urls"]["regular"],
            "credit": f"Фото: [{author}]({author_url}) / Unsplash",
            "local_path": None,  # filled by save_photo()
        }
    except Exception as exc:
        log.warning("Unsplash fetch failed: %s", exc)
        return None


def fetch_photo_for_topic(topic_slug: str, category: str) -> dict | None:
    queries: list[str] = []

    primary_query = topic_slug.replace("-", " ").strip()
    if primary_query:
        queries.append(primary_query)

    for query in CATEGORY_FALLBACK_QUERIES.get(category, []):
        if query not in queries:
            queries.append(query)

    queries.extend(q for q in ["business", "economy"] if q not in queries)

    for query in queries:
        photo = fetch_photo(query)
        if photo:
            log.info("Selected Unsplash photo for query: %s", query)
            return photo

    log.warning("No Unsplash photo found for topic '%s' in category '%s'", topic_slug, category)
    return None


def save_photo(photo: dict, output_dir: str, slug: str) -> str | None:
    """Download photo to output_dir/<slug>.jpg. Returns local path or None."""
    try:
        resp = httpx.get(photo["url"], timeout=30, follow_redirects=True)
        resp.raise_for_status()
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{slug}.jpg")
        with open(path, "wb") as f:
            f.write(resp.content)
        photo["local_path"] = path
        log.info("Photo saved to %s", path)
        return path
    except Exception as exc:
        log.warning("Failed to save photo: %s", exc)
        return None
