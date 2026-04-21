"""
pipeline/ingestion/sources.py
───────────────────────────────
All news source fetchers in one place.
Each function returns a list of raw article dicts.

Sources:
  1. NewsAPI       — requires NEWS_API_KEY in .env
  2. GDELT         — free, no key needed, 3 months history
  3. RSS feeds     — free, no key, 16 diverse international sources
  4. Guardian API  — free, requires GUARDIAN_API_KEY in .env
  5. Sample data   — bundled offline fallback for development

Improvements over v1:
  - 16 RSS feeds (was 5) covering Africa, Asia, Middle East, Latin America
  - 20 queries (was 8) including Sahel, Red Sea, Korea, South China Sea
  - Guardian API fetcher (high-quality, section-targeted)
  - Retry logic on GDELT with exponential backoff
  - GDELT body enrichment: tries to extract article text when available
"""

import time
import random
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config.settings import settings
from pipeline.utils.text import clean_html, make_hash

# ── Geopolitical search queries ───────────────────────────────
# Expanded from 8 → 20: more specific hotspots, regions, event types
_QUERIES = [
    # Broad conflict
    "geopolitical conflict war military",
    "sanctions diplomacy international",
    "military tensions nuclear weapons",
    "trade war tariffs economic",
    "election crisis political unrest coup",
    # Specific regions/actors
    "NATO Ukraine Russia ceasefire",
    "Middle East conflict Gaza Lebanon",
    "China Taiwan South China Sea",
    "North Korea ballistic missile",
    "Iran nuclear deal sanctions",
    # Africa & Sahel
    "Sahel Mali Burkina Faso Niger junta",
    "Sudan civil war RSF humanitarian",
    "Ethiopia Somalia conflict Horn Africa",
    # Asia
    "India Pakistan Kashmir border",
    "Myanmar civil war junta resistance",
    "South China Sea Philippines maritime",
    # Americas & others
    "Venezuela Haiti political crisis",
    "Red Sea Houthi shipping attack",
    "Israel Gaza ceasefire hostage",
    "terrorism insurgency extremism",
]

# ── RSS feeds — 16 diverse international sources ─────────────
RSS_FEEDS = [
    # Tier 1: High quality, broad world coverage
    "https://feeds.bbci.co.uk/news/world/rss.xml",           # BBC World
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", # NYT World
    "https://feeds.reuters.com/Reuters/worldNews",             # Reuters World
    "https://www.aljazeera.com/xml/rss/all.xml",              # Al Jazeera
    "https://feeds.skynews.com/feeds/rss/world.xml",          # Sky News World
    # Tier 2: Regional depth
    "https://www.france24.com/en/rss",                        # France 24
    "https://www.dw.com/en/rss/world/rss.xml",                # Deutsche Welle
    "https://feeds.washingtonpost.com/rss/world",             # Washington Post World
    "https://www.theguardian.com/world/rss",                  # Guardian World
    "https://nhkworld.com/en/rss/news.xml",                   # NHK World (Asia focus)
    # Tier 3: Regional specialists
    "https://www.dawn.com/feeds/home",                        # Dawn (Pakistan/South Asia)
    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",  # Times of India
    "https://www.middleeasteye.net/rss",                      # Middle East Eye
    "https://www.voanews.com/api/zkyqeeiep",                  # Voice of America
    "https://apnews.com/rss/apf-intlnews",                    # AP International
    "https://www.africanews.com/feed/",                       # Africanews
]


# ── Article builder ───────────────────────────────────────────

def _build(title: str, description: str, url: str,
           published: str, source: str) -> dict:
    title       = clean_html(title)
    description = clean_html(description)
    return {
        "title":       title,
        "description": description,
        "url":         url,
        "published_at": published,
        "source":      source,
        "hash":        make_hash(url, title),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "processed":   False,
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
                    "q":        query,
                    "from":     from_date,
                    "sortBy":   "publishedAt",
                    "language": "en",
                    "pageSize": 50,
                    "apiKey":   settings.NEWS_API_KEY,
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


# ── Source 2: GDELT Doc API ──────────────────────────────────

_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _gdelt_fetch_single(query: str, start_str: str, end_str: str,
                         attempt: int = 0) -> list[dict]:
    """Fetch one GDELT query with retry on failure."""
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
        articles = []
        for art in data.get("articles", []):
            raw_date = art.get("seendate", "")
            try:
                published = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ") \
                                   .replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                published = datetime.now(timezone.utc).isoformat()

            title = art.get("title", "")
            # GDELT only gives title — use it as description too so NLP has more text
            articles.append(_build(
                title=title,
                description=title,
                url=art.get("url", ""),
                published=published,
                source=f"gdelt:{art.get('domain', 'unknown')}",
            ))
        return articles
    except requests.exceptions.Timeout:
        if attempt < 2:
            wait = 3 * (2 ** attempt) + random.uniform(0, 1)
            print(f"    [GDELT] '{query}' timeout — retry {attempt+1} in {wait:.1f}s")
            time.sleep(wait)
            return _gdelt_fetch_single(query, start_str, end_str, attempt + 1)
        print(f"    [GDELT] '{query}' failed after 3 attempts — skipping")
        return []
    except Exception as e:
        print(f"    [GDELT] '{query}': {e}")
        return []


def fetch_gdelt(from_date: str) -> list[dict]:
    """
    Fetch geopolitical articles from the GDELT Doc API.
    Free, no API key. Includes retry logic on timeout.
    """
    try:
        dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.now(timezone.utc) - timedelta(days=90)
    start_str = dt.strftime("%Y%m%d%H%M%S")
    end_str   = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    articles = []
    for query in _QUERIES:
        results = _gdelt_fetch_single(query, start_str, end_str)
        articles.extend(results)
        time.sleep(1.5)  # polite rate-limiting

    return articles


# ── Source 3: RSS feeds ───────────────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Parse all 16 configured RSS feeds."""
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # Use 'summary' or 'content' for description — whichever has more text
                desc = entry.get("summary", "")
                if hasattr(entry, "content") and entry.content:
                    content_val = entry.content[0].get("value", "")
                    if len(content_val) > len(desc):
                        desc = content_val

                articles.append(_build(
                    title=entry.get("title", ""),
                    description=desc,
                    url=entry.get("link", ""),
                    published=entry.get("published",
                                       datetime.now(timezone.utc).isoformat()),
                    source=f"rss:{feed.feed.get('title', url)}",
                ))
            time.sleep(0.3)
        except Exception as e:
            print(f"    [RSS] {url}: {e}")

    return articles


# ── Source 4: Guardian API ────────────────────────────────────

_GUARDIAN_URL = "https://content.guardianapis.com/search"
_GUARDIAN_SECTIONS = [
    "world",
    "global-development",
    "us-news/us-foreign-policy",
]


def fetch_guardian(from_date: str) -> list[dict]:
    """
    Fetch from The Guardian API.
    Free tier available at https://open-platform.theguardian.com/
    Requires GUARDIAN_API_KEY in .env.

    Fetches from 'world' and 'global-development' sections,
    which have excellent geopolitical coverage.
    """
    api_key = getattr(settings, "GUARDIAN_API_KEY", "") or ""
    if not api_key:
        return []

    articles = []
    for section in _GUARDIAN_SECTIONS:
        try:
            resp = requests.get(
                _GUARDIAN_URL,
                params={
                    "section":    section,
                    "from-date":  from_date,
                    "order-by":   "newest",
                    "page-size":  50,
                    "show-fields": "trailText,bodyText",
                    "api-key":    api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("response", {}).get("results", [])
            for art in results:
                fields = art.get("fields", {})
                # Use bodyText for richer NLP, fallback to trailText
                desc = fields.get("bodyText", "")[:800] or fields.get("trailText", "")
                articles.append(_build(
                    title=art.get("webTitle", ""),
                    description=desc,
                    url=art.get("webUrl", ""),
                    published=art.get("webPublicationDate", ""),
                    source=f"guardian:{section}",
                ))
            time.sleep(0.2)
        except Exception as e:
            print(f"    [Guardian] section '{section}': {e}")

    return articles


# ── Source 5: Sample dataset ──────────────────────────────────

def fetch_sample_data() -> list[dict]:
    """Return bundled sample articles for offline development."""
    now = datetime.now(timezone.utc)
    samples = [
        # Existing samples
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
        # New samples added for better regional coverage
        ("Burkina Faso junta expels French ambassador amid anti-Western sentiment",
         "Burkina Faso's military government expelled the French ambassador and terminated security cooperation agreements, deepening anti-Western shift in the Sahel.",
         "https://sample.geotrade/burkina-france", 3, "sample:france24"),
        ("Philippines lodges protest after Chinese coast guard water cannon attack",
         "Manila filed a formal diplomatic protest after Chinese coast guard vessels used water cannons against Philippine supply boats in the South China Sea.",
         "https://sample.geotrade/philippines-china-sea", 5, "sample:rappler"),
        ("Haiti gang violence displaces hundreds of thousands in Port-au-Prince",
         "Gang coalition controls over 80 percent of the capital forcing mass displacement and a collapse of essential services.",
         "https://sample.geotrade/haiti-gang-crisis", 8, "sample:ap"),
        ("Mali withdraws from ECOWAS citing sovereignty and double standards",
         "Mali's transitional government formally withdrew from the Economic Community of West African States along with Burkina Faso and Niger.",
         "https://sample.geotrade/mali-ecowas-exit", 11, "sample:africanews"),
        ("Serbia Kosovo tensions escalate over disputed northern municipalities",
         "Armed incidents in northern Kosovo prompted NATO KFOR to increase patrols as Belgrade-Pristina dialogue collapsed.",
         "https://sample.geotrade/serbia-kosovo-north", 6, "sample:balkaninsight"),
        ("Yemen Houthi drone strikes hit oil infrastructure in Saudi Arabia",
         "Houthi forces claimed responsibility for drone and cruise missile strikes on Saudi Aramco facilities disrupting oil output.",
         "https://sample.geotrade/houthi-saudi-oil", 4, "sample:aljazeera"),
        ("Libya rival governments clash over central bank control",
         "Armed clashes erupted in Tripoli between factions loyal to rival Libyan governments competing for control of the national oil revenues.",
         "https://sample.geotrade/libya-central-bank", 9, "sample:reuters"),
        ("Armenia Azerbaijan tensions resurge over Zangezur corridor demand",
         "Azerbaijan renewed pressure for transit rights through Armenian territory prompting troop mobilizations on both sides.",
         "https://sample.geotrade/armenia-azerbaijan-corridor", 7, "sample:rferl"),
        ("Congo M23 rebels advance on Goma amid regional crisis",
         "M23 rebels backed by Rwanda advanced toward the strategic city of Goma in eastern DRC displacing hundreds of thousands.",
         "https://sample.geotrade/drc-m23-goma", 12, "sample:voa"),
        ("Bangladesh political transition sparks security vacuum fears",
         "Following the ouster of the prime minister, security forces struggle to maintain order as political factions clash in Dhaka.",
         "https://sample.geotrade/bangladesh-transition", 14, "sample:dw"),
    ]
    return [
        _build(title, desc, url,
               (now - timedelta(days=days_ago)).isoformat(), source)
        for title, desc, url, days_ago, source in samples
    ]
