import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
SEND_UNSPLASH_PHOTO = os.environ.get("SEND_UNSPLASH_PHOTO", "").lower() in {"1", "true", "yes", "on"}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
FACEBOOK_PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "")

GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

RSS_FEEDS = [
    # World — General
    ("general",    "http://rss.cnn.com/rss/edition.rss"),
    ("general",    "https://feeds.content.dowjones.io/public/rss/wsj_world_news"),
    ("general",    "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("general",    "https://feeds.washingtonpost.com/rss/world"),
    ("general",    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    # World — Business & Finance
    ("finance",    "https://feeds.bloomberg.com/markets/news.rss"),
    ("finance",    "https://finance.yahoo.com/news/rssindex"),
    ("finance",    "https://www.ft.com/world?format=rss"),
    # World — Technology
    ("technology", "https://techcrunch.com/feed/"),
    ("technology", "https://feeds.arstechnica.com/arstechnica/index"),
    ("technology", "https://www.technologyreview.com/feed/"),
    ("technology", "https://www.theverge.com/rss/index.xml"),
    # Baltic
    ("baltic",     "https://news.err.ee/rss"),
    ("baltic",     "https://www.baltictimes.com/rss/"),
]

CATEGORIES = ["technology", "finance", "real_estate", "industry", "geopolitics", "baltic"]

# Breaking news: if a topic appears in this many sources within 48h, bypass rotation
BREAKING_NEWS_SOURCE_THRESHOLD = 999
