"""
pipeline/ingestion/sources.py
───────────────────────────────
All news source fetchers in one place.
Each function returns a list of raw article dicts.

Sources:
  1. NewsAPI      — requires NEWS_API_KEY in .env
  2. GDELT        — free, no key needed, 3 months history
  3. RSS feeds    — free, no key needed
  4. Sample data  — bundled offline fallback for development
"""

import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config.settings import settings
from pipeline.utils.text import clean_html, make_hash

# ── Geopolitical search queries (shared by NewsAPI + GDELT) ──
_QUERIES = [
    "geopolitical conflict war",
    "sanctions diplomacy",
    "military tensions nuclear",
    "trade war tariffs",
    "election crisis political unrest",
    "NATO Ukraine Russia",
    "Middle East conflict Gaza",
    "China Taiwan South China Sea",
]

# ── GDELT Doc API base URL (free, no key) ─────────────────────
_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# ── RSS feeds (no auth) ───────────────────────────────────────
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.reuters.com/Reuters/worldNews",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.skynews.com/feeds/rss/world.xml",
]


# ── Article builder ───────────────────────────────────────────

def _build(title: str, description: str, url: str,
           published: str, source: str) -> dict:
    title = clean_html(title)
    description = clean_html(description)
    return {
        "title": title,
        "description": description,
        "url": url,
        "published_at": published,
        "source": source,
        "hash": make_hash(url, title),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    }


# ── Source 1: NewsAPI ─────────────────────────────────────────

def fetch_newsapi(from_date: str) -> list[dict]:
    """Fetch from NewsAPI /v2/everything for all geopolitical queries."""
    if not settings.NEWS_API_KEY:
        return []

    articles = []
    for query in _QUERIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 50,
                    "apiKey": settings.NEWS_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for art in resp.json().get("articles", []):
                articles.append(_build(
                    title=art.get("title", ""),
                    description=art.get("description") or art.get("content", ""),
                    url=art.get("url", ""),
                    published=art.get("publishedAt", ""),
                    source=f"newsapi:{art.get('source', {}).get('name', 'unknown')}",
                ))
            time.sleep(0.25)
        except Exception as e:
            print(f"    [NewsAPI] '{query}': {e}")

    return articles


# ── Source 2: GDELT Doc API ─────────────────────────────────

def fetch_gdelt(from_date: str) -> list[dict]:
    """
    Fetch geopolitical articles from the GDELT Doc API.
    Completely free, no API key required.
    Covers the last ~3 months of global English-language news.
    """
    # Convert from_date (YYYY-MM-DD) to GDELT format (YYYYMMDDHHMMSS)
    try:
        dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.now(timezone.utc) - timedelta(days=90)
    start_str = dt.strftime("%Y%m%d%H%M%S")
    end_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    articles = []
    for query in _QUERIES:
        try:
            resp = requests.get(
                _GDELT_URL,
                params={
                    "query":         query,
                    "mode":          "artlist",
                    "maxrecords":    250,
                    "sort":          "DateDesc",
                    "format":        "json",
                    "startdatetime": start_str,
                    "enddatetime":   end_str,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for art in data.get("articles", []):
                # GDELT seendate format: 20260101T120000Z
                raw_date = art.get("seendate", "")
                try:
                    published = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ") \
                                       .replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    published = datetime.now(timezone.utc).isoformat()

                articles.append(_build(
                    title=art.get("title", ""),
                    description=art.get("title", ""),  # GDELT only gives title
                    url=art.get("url", ""),
                    published=published,
                    source=f"gdelt:{art.get('domain', 'unknown')}",
                ))
            time.sleep(1.5)  # be polite to GDELT — avoids 429 rate-limit
        except Exception as e:
            print(f"    [GDELT] '{query}': {e}")

    return articles


# ── Source 2: RSS feeds ───────────────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Parse all configured RSS feeds."""
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                articles.append(_build(
                    title=entry.get("title", ""),
                    description=entry.get("summary", ""),
                    url=entry.get("link", ""),
                    published=entry.get("published", datetime.now(timezone.utc).isoformat()),
                    source=f"rss:{feed.feed.get('title', url)}",
                ))
            time.sleep(0.3)
        except Exception as e:
            print(f"    [RSS] {url}: {e}")

    return articles


# ── Source 3: Sample dataset ──────────────────────────────────

def fetch_sample_data() -> list[dict]:
    """Return bundled sample articles for offline development."""
    now = datetime.now(timezone.utc)
    samples = [
        ("US imposes new sanctions on Russia over Ukraine conflict",
         "The administration announced sweeping economic sanctions targeting Russian energy exports and financial institutions following escalating military actions in eastern Ukraine.",
         "https://sample.geotrade/us-russia-sanctions", 2, "sample:reuters"),
        ("China and Taiwan tensions rise as military drills intensify",
         "China conducted large-scale military exercises near Taiwan involving dozens of warships and aircraft in the most significant show of force in years.",
         "https://sample.geotrade/china-taiwan-drills", 3, "sample:bbc"),
        ("Iran nuclear talks reach critical juncture in Vienna",
         "Diplomatic negotiations stalled again as Western powers demand stringent inspection protocols while Tehran insists on guaranteed sanctions relief.",
         "https://sample.geotrade/iran-nuclear-talks", 4, "sample:aljazeera"),
        ("North Korea fires ballistic missiles into Sea of Japan",
         "North Korea launched two intercontinental ballistic missiles drawing immediate condemnation from South Korea, Japan, and the United States.",
         "https://sample.geotrade/north-korea-missiles", 1, "sample:nytimes"),
        ("India-Pakistan diplomatic crisis deepens after border incident",
         "Relations deteriorated sharply following a cross-border incident in Kashmir prompting both countries to recall their ambassadors.",
         "https://sample.geotrade/india-pakistan-crisis", 5, "sample:reuters"),
        ("EU agrees on seventh package of sanctions against Russia",
         "EU member states reached consensus on new sanctions targeting Russian oil revenues, technology exports, and key Kremlin individuals.",
         "https://sample.geotrade/eu-russia-sanctions-7", 6, "sample:euronews"),
        ("Sudan civil war displaces millions amid humanitarian crisis",
         "Armed conflict between Sudanese Armed Forces and Rapid Support Forces has displaced over 4 million people creating one of the world's worst crises.",
         "https://sample.geotrade/sudan-civil-war", 7, "sample:un_news"),
        ("Israel-Gaza ceasefire talks collapse in Cairo",
         "Negotiations mediated by Egypt and Qatar broke down after Israeli and Hamas delegations failed to agree on hostage-for-prisoner exchange terms.",
         "https://sample.geotrade/israel-gaza-ceasefire", 2, "sample:aljazeera"),
        ("NATO enlargement prompts Russian military buildup near Baltic states",
         "Russia significantly increased military deployments along its northern flank raising alarms among Baltic state governments.",
         "https://sample.geotrade/nato-russia-baltic", 10, "sample:reuters"),
        ("US-China trade war escalates with new semiconductor tariffs",
         "The US announced steep tariffs on Chinese semiconductor imports while Beijing restricted exports of rare earth materials critical to electronics manufacturing.",
         "https://sample.geotrade/us-china-semiconductor", 11, "sample:ft"),
        ("Myanmar junta extends emergency amid intensifying civil war",
         "Myanmar's military extended its state of emergency as resistance forces advanced on multiple fronts capturing key towns in the northwest.",
         "https://sample.geotrade/myanmar-junta", 12, "sample:irrawaddy"),
        ("Venezuela election results disputed triggering political turmoil",
         "Presidential election results were disputed by opposition and international observers leading to street protests and calls for an independent recount.",
         "https://sample.geotrade/venezuela-election", 9, "sample:reuters"),
        ("UN Security Council emergency session on Red Sea shipping attacks",
         "The UN convened after Houthi rebels conducted coordinated drone and missile attacks on commercial shipping in the Red Sea.",
         "https://sample.geotrade/red-sea-attacks-un", 14, "sample:reuters"),
        ("South Korea declares emergency law amid political standoff",
         "South Korean President declared a short-lived state of emergency in a legislative standoff triggering a constitutional crisis leading to impeachment.",
         "https://sample.geotrade/south-korea-emergency", 15, "sample:koreatimes"),
        ("Pakistan political crisis deepens as Imran Khan sentenced",
         "Pakistan's former prime minister was convicted on treason charges stemming from his handling of a diplomatic cypher, widely criticized as politically motivated.",
         "https://sample.geotrade/pakistan-imran-khan", 19, "sample:dawn"),
        ("Nigeria security crisis deepens as Boko Haram attacks surge",
         "Boko Haram militants conducted multiple attacks in northeastern Nigeria killing hundreds and displacing thousands in the Lake Chad basin region.",
         "https://sample.geotrade/nigeria-boko-haram", 17, "sample:guardian"),
        ("Ethiopia Somalia border tensions flare into armed clashes",
         "Border tensions escalated into armed conflict following disputed territorial claims drawing regional powers into the standoff.",
         "https://sample.geotrade/ethiopia-somalia", 13, "sample:aljazeera"),
        ("Turkey Greece in diplomatic row over Aegean Sea drilling rights",
         "A longstanding dispute over hydrocarbon exploration rights in the Aegean Sea flared again after Ankara authorized new drilling surveys.",
         "https://sample.geotrade/turkey-greece-aegean", 18, "sample:ekathimerini"),
        ("G7 discusses coordinated response to rising geopolitical tensions",
         "Leaders met in emergency session to coordinate diplomatic and economic responses to regional conflicts threatening global stability.",
         "https://sample.geotrade/g7-geopolitical-response", 8, "sample:bbc"),
        ("Brazil Argentina push back on IMF structural adjustment terms",
         "Both nations rejected key IMF conditions tied to debt restructuring packages sparking fears of sovereign defaults cascading through emerging markets.",
         "https://sample.geotrade/latam-imf-standoff", 16, "sample:bloomberg"),
    ]
    return [
        _build(title, desc, url,
               (now - timedelta(days=days_ago)).isoformat(), source)
        for title, desc, url, days_ago, source in samples
    ]
