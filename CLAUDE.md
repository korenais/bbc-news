# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Automated daily newsletter for **Baltic Business Club** (https://balticbusinessclub.com/).

Each run (daily at 10:30 via cron on local laptop):
1. Collects news from 14 RSS feeds (global + Baltic)
2. Selects the best topic using Ollama (category priority rotation)
3. Generates a **Russian-language** newsletter via OpenAI GPT
4. Optionally attaches an Unsplash photo
5. Publishes to Telegram channel + Facebook page
6. Logs to Google Sheets (`newsletters` tab) and updates `category_stats` tab

## Running

```bash
./run_local.sh              # full run (publish + track)
./run_local.sh --dry-run    # generate only, save to output/, no publish
python -m src.main --dry-run
```

Cron (local laptop):
```
30 10 * * * cd /Users/korenaisenstadt/git/bbc-news && ./run_local.sh
```

## Architecture

```
main.py
  ├── ollama_manager     — start/stop local Ollama server
  ├── collector.py       — fetch RSS feeds → list[Article], 36h window
  ├── selector.py        — group by topic, sort by category priority, ask Ollama to pick best
  ├── generator.py       — build prompt from prompt.txt, call OpenAI GPT (fallback: Ollama)
  ├── photo_fetcher.py   — Unsplash API (only if SEND_UNSPLASH_PHOTO=true)
  ├── publisher.py       — post to Telegram + Facebook
  ├── tracker.py         — Google Sheets read/write (primary store)
  └── rotation.py        — priority manager; uses Sheets if configured, else rotation.json
```

## LLM Usage

- **Selector**: Ollama `llama3.1:8b` (local) — JSON output, picks best topic from top 20 candidates
- **Generator**: OpenAI GPT (primary) — uses `prompt.txt` as the prompt template; falls back to Ollama if no `OPENAI_API_KEY`

`prompt.txt` is user-editable. It contains `{sources_block}` and `{breaking_note}` placeholders replaced at runtime.

## Category Rotation (Priority System)

Categories: `technology`, `finance`, `real_estate`, `industry`, `geopolitics`, `baltic`

After each publish, `tracker.py._refresh_category_stats()` recalculates priorities:
- Fewer total posts → higher priority (lower score)
- Last posted category → always priority 9999 (never picked back-to-back)

Priorities stored in Google Sheets `category_stats` tab (user can manually edit the `priority` column between runs). Local fallback: `rotation.json`.

Breaking news override: ≥5 sources covering the same topic within 48h → bypasses rotation.

## Google Sheets Schema

**`newsletters` tab** — source of truth:
`date, topic_slug, category, headline_ru, source_urls, telegram_msg_id, facebook_post_id, tg_views, tg_reactions, fb_likes, fb_comments, fb_shares, engagement_score`

**`category_stats` tab** — computed cache, user-editable:
`category, total_posts, last_posted, avg_engagement_score, priority`

Engagement score formula: `(tg_reactions×3 + fb_likes + fb_comments×5 + fb_shares×4) / max(tg_views, 1)`

Stats for the previous post are updated at the start of each new run.

## Environment Variables

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
UNSPLASH_ACCESS_KEY=
SEND_UNSPLASH_PHOTO=false     # set to true to attach photos
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_TOKEN=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=  # absolute path to service account JSON file
```

All publishing/tracking vars degrade gracefully if empty.

## RSS Sources

| Category | Source | URL |
|----------|--------|-----|
| general | CNN | `http://rss.cnn.com/rss/edition.rss` (http — SSL broken on https) |
| general | WSJ World | `https://feeds.content.dowjones.io/public/rss/wsj_world_news` |
| general | Sky News | `https://feeds.skynews.com/feeds/rss/world.xml` |
| general | Washington Post | `https://feeds.washingtonpost.com/rss/world` |
| general | NYT World | `https://rss.nytimes.com/services/xml/rss/nyt/World.xml` |
| finance | Bloomberg | `https://feeds.bloomberg.com/markets/news.rss` |
| finance | Yahoo Finance | `https://finance.yahoo.com/news/rssindex` |
| finance | Financial Times | `https://www.ft.com/world?format=rss` |
| technology | TechCrunch | `https://techcrunch.com/feed/` |
| technology | Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` |
| technology | MIT Tech Review | `https://www.technologyreview.com/feed/` |
| technology | The Verge | `https://www.theverge.com/rss/index.xml` |
| baltic | ERR News | `https://news.err.ee/rss` |
| baltic | Baltic Times | `https://www.baltictimes.com/rss/` |

## Known Issues / Past Fixes

- CNN: must use `http://` (https gives `SSL: UNEXPECTED_EOF`)
- Reuters `feeds.reuters.com/reuters/businessNews` is dead → replaced with Yahoo Finance
- ERR: old `feeds.err.ee/en/news` is dead → use `news.err.ee/rss`
- Ollama selector sometimes wraps JSON in array → regex `r"\{[^{}]*\}"` + `isinstance(result, dict)` check in `selector.py`
