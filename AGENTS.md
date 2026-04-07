# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Purpose

Automated newsletter generation tool for **Baltic Business Club** (https://balticbusinessclub.com/).

Every newsletter (published twice a week, fully autonomous):
1. Collects news from public RSS feeds and news APIs
2. Selects the most relevant topic for the club's audience (IT, manufacturing, real estate, investments)
3. Generates a **Russian-language** newsletter with emphasis on **Baltic/Estonia impact**
4. Attaches a free-stock photo relevant to the topic
5. Publishes to the club's **Telegram channel** and **Facebook page**
6. Logs the post to **Google Sheets** for deduplication and analytics tracking

## Tech Stack

- **Language**: Python 3.11+
- **LLM**: Ollama (local, `llama3.1:8b`) — started by cron, stopped after job completes
- **Containerization**: Docker + docker-compose (runs on VPS)
- **Scheduling**: System cron (outside Docker, triggers `docker-compose run`)
- **News sources**: RSS feeds (no paid APIs required)
- **Photos**: Unsplash API (free tier, attribution included in post)
- **Publishing**: Telegram Bot API + Facebook Pages API (Graph API)
- **Tracking**: Google Sheets via `gspread` + service account

## Architecture

```
cron (VPS)
  └─► docker-compose run app
        ├── 1. start_ollama.sh          # starts ollama server + pulls model if needed
        ├── 2. collector.py             # fetches RSS feeds, returns raw articles
        ├── 3. deduplicator.py          # checks Google Sheets history, filters seen topics
        ├── 4. selector.py              # asks Ollama to rank & pick best topic for audience
        ├── 5. generator.py             # asks Ollama to write Russian newsletter (see format)
        ├── 6. photo_fetcher.py         # fetches relevant photo from Unsplash API
        ├── 7. publisher.py             # posts to Telegram + Facebook
        ├── 8. tracker.py              # writes result row to Google Sheets
        └── stop_ollama.sh             # stops ollama process
```

## News Sources (RSS)

World — General:
- CNN: `https://rss.cnn.com/rss/edition.rss`
- WSJ World: `https://feeds.content.dowjones.io/public/rss/wsj_world_news`
- Sky News World: `https://feeds.skynews.com/feeds/rss/world.xml`
- Washington Post World: `https://feeds.washingtonpost.com/rss/world`
- NYT World: `https://rss.nytimes.com/services/xml/rss/nyt/World.xml`

World — Business & Finance:
- Reuters Business: `https://feeds.reuters.com/reuters/businessNews`
- Financial Times (World): `https://www.ft.com/world?format=rss`
- Bloomberg Markets: `https://feeds.bloomberg.com/markets/news.rss`

World — Technology:
- TechCrunch: `https://techcrunch.com/feed/`
- Ars Technica: `https://feeds.arstechnica.com/arstechnica/index`
- MIT Technology Review: `https://www.technologyreview.com/feed/`
- The Verge: `https://www.theverge.com/rss/index.xml`

Baltic/Local (2 authoritative sources only):
- ERR News (English): `https://feeds.err.ee/en/news`
- The Baltic Times: `https://www.baltictimes.com/rss/`

## Newsletter Format (Russian)

```
📰 [ТЕМА — короткий цепляющий заголовок]

[Лид: 2–3 предложения — суть события]

🌍 Что произошло
[3–5 абзацев: контекст, факты, ключевые игроки. Ссылки на источники inline]

🇪🇪 Влияние на Балтийский регион
[Обязательный раздел: конкретные последствия для Эстонии/Латвии/Литвы —
 бизнес, инвестиции, регулирование, рынок труда и т.д.]

💼 Что это значит для бизнеса
[Практический вывод для аудитории клуба: IT, производство, недвижимость, инвестиции]

📎 Источники
- [Название] → URL
- ...

📷 Фото: Unsplash / [author name]
```

## Topic Categories & Rotation

Every article is classified into one of these categories:

| Category | Description |
|----------|-------------|
| `technology` | AI, software, cybersecurity, digital infrastructure |
| `finance` | Markets, stocks, bonds, crypto, monetary policy |
| `real_estate` | Property markets, construction, proptech |
| `industry` | Manufacturing, energy, supply chains, logistics |
| `geopolitics` | International relations, sanctions, trade wars |
| `baltic` | Estonia/Latvia/Lithuania specific significant events |

**Freshness**: only articles published in the last **24 hours** are considered.

**Rotation rule**: the selector must not pick the same category as either of the **two previous newsletters**. The last 2 categories are read from Google Sheets before topic selection.

**Breaking news override**: if a story scores above a "urgency threshold" (≥ 5 independent sources covering it within 48h, or ERR/Reuters mark it as breaking), rotation is bypassed and the story is published regardless of category.

The selector prompt to Ollama includes the last 2 categories explicitly and instructs it to avoid them unless urgency override applies.

## Google Sheets Tracking Schema

Sheet: `newsletters`

| Column | Description |
|--------|-------------|
| `date` | ISO date of publication |
| `topic_slug` | Short English slug for deduplication |
| `category` | One of: technology, finance, real_estate, industry, geopolitics, baltic |
| `headline_ru` | Russian headline |
| `source_urls` | Comma-separated source URLs |
| `telegram_msg_id` | Telegram message ID |
| `facebook_post_id` | Facebook post ID |
| `tg_views` | Telegram views (updated on next run) |
| `tg_reactions` | Telegram reactions count |
| `fb_likes` | Facebook likes |
| `fb_comments` | Facebook comments |
| `fb_shares` | Facebook shares |
| `engagement_score` | Computed: `(tg_reactions*3 + fb_likes + fb_comments*5 + fb_shares*4) / max(tg_views,1)` |

On each run, **before** publishing, the previous post's stats are updated (Telegram Stats API + Facebook Graph API).

## Success Metrics

`engagement_score` is the primary KPI. Weights rationale:
- Comments × 5: highest intent signal
- Shares × 4: reach amplifier
- Reactions × 3: easy positive signal
- Views are the denominator (normalises for channel size growth)

Topics with `engagement_score > 0.05` are considered "resonating" with the audience.
The selector uses past scores to bias toward similar topic categories.

## Copyright Rules

- **Never reproduce** full article text — summarise only
- Always cite original source with a working URL
- Unsplash photos: always include author credit in the post
- AI-generated summaries are transformative; direct quotes must be short (≤ 2 sentences) and attributed

## Environment Variables (`.env`)

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
UNSPLASH_ACCESS_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_TOKEN=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=/run/secrets/google_sa.json
```

## Cron Schedule (EET timezone)

VPS timezone must be set to `Europe/Tallinn`. Then cron runs at exactly 09:00 year-round, DST handled automatically.

```bash
# On VPS: set timezone once
timedatectl set-timezone Europe/Tallinn
```

```cron
# Tuesday 09:00 Tallinn time
0 9 * * 2 cd /opt/bbc-news && docker-compose run --rm app

# Friday 09:00 Tallinn time
0 9 * * 5 cd /opt/bbc-news && docker-compose run --rm app
```

## Development Phases

**Phase 1 (current)** — core pipeline only, no external services needed except Ollama:
- Only `OLLAMA_HOST`, `OLLAMA_MODEL`, `UNSPLASH_ACCESS_KEY` required
- Google Sheets / Telegram / Facebook vars can be left empty — system degrades gracefully

**Phase 2** — add Google Sheets tracking, then Telegram + Facebook publishing

## Running Locally

```bash
cp .env.example .env        # fill in UNSPLASH_ACCESS_KEY at minimum
./run_local.sh --dry-run    # creates venv, installs deps, runs pipeline, prints result
./run_local.sh              # full run (requires phase 2 vars)
```

Via Docker:
```bash
docker-compose build
docker-compose run --rm app --dry-run
```
