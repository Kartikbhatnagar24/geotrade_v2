# GeoTrade

> **Geopolitical intelligence platform** — ingests global news, classifies events with NLP, scores country-level tension, forecasts 7-day trends, and visualizes everything on an interactive 3D globe with AI-powered market briefings.

---

## What It Does

```
News Sources          NLP Pipeline          Scoring            Intelligence
─────────────         ────────────          ───────            ───────────
GDELT (free)    ──►   Event type      ──►   Tension score  ──► 3D Globe
16 RSS feeds    ──►   Sentiment       ──►   Smoothed score ──► 7-day Forecast
NewsAPI (opt.)  ──►   Country NER     ──►   daily_signals  ──► Gemini Briefings
Guardian (opt.) ──►   Intensity       ──►   tension_       ──► Stock Signals
                       score               forecasts       ──► Market Model
```

The globe colors each country by tension (red = high, amber = medium, green = low). Click any country to get:
- Recent geopolitical headlines
- Stock/ETF signals (LONG / SHORT / WATCH)
- 7-day tension forecast with sparkline
- Gemini AI market briefing with trade ideas

---

## Project Structure

```
geotrade/
├── .env                        ← your secrets (copy from .env.example)
├── requirements.txt            ← all Python dependencies
├── config/
│   └── settings.py             ← single source of all env vars
│
├── pipeline/
│   ├── ingestion/
│   │   ├── sources.py          ← 5 fetchers: GDELT, RSS x16, NewsAPI, Guardian, samples
│   │   └── store.py            ← dedup by hash, insert into raw_articles
│   ├── nlp/
│   │   ├── models.py           ← HuggingFace model loader (cached after first run)
│   │   ├── classify.py         ← BART zero-shot event type + DistilBERT sentiment
│   │   ├── ner.py              ← 130+ country/city/actor keyword matcher + intensity_score()
│   │   └── store.py            ← write processed_events, mark articles done
│   ├── scoring/
│   │   ├── scorer.py           ← tension_score, smoothed_score, intensity weighting
│   │   ├── stocks.py           ← country ISO → tickers → LONG/SHORT/WATCH signals
│   │   └── store.py            ← upsert daily_signals, export CSV
│   ├── forecasting/
│   │   └── forecaster.py       ← numpy linear trend → 7-day forecast + confidence
│   └── modeling/
│       ├── features.py         ← merge tension signals + yfinance market data
│       ├── train.py            ← RandomForest + LightGBM, save_best_model()
│       └── plots.py            ← 4 thesis-ready dark-theme charts
│
├── scripts/                    ← run in order (or use run_all.py)
│   ├── step1_ingest.py         ← fetch news → raw_articles
│   ├── step2_nlp.py            ← NLP → processed_events
│   ├── step3_score.py          ← scoring → daily_signals
│   ├── step4_model.py          ← train ML model → data/models/
│   ├── step5_forecast.py       ← forecast cache → tension_forecasts
│   └── run_all.py              ← runs all steps, supports --from / --skip / --only
│
├── backend/
│   ├── main.py                 ← FastAPI app with CORS for localhost:3000
│   ├── core/database.py        ← MongoDB singleton
│   ├── models/schemas.py       ← Pydantic response models
│   └── routes/
│       ├── events.py           ← GET /events, GET /events/{iso}
│       ├── signals.py          ← GET /signals
│       ├── trading.py          ← GET /trading/{iso}
│       ├── forecast.py         ← GET /forecast/{iso}
│       └── briefing.py         ← GET /briefing/{iso}  (Gemini API)
│
├── frontend/
│   ├── pages/index.tsx         ← main page, wires all components
│   ├── components/
│   │   ├── globe/GlobeViewer.tsx
│   │   └── panels/
│   │       ├── CountryTradingPanel.tsx  ← 4-tab drawer (News/Stocks/Forecast/AI)
│   │       ├── FilterPanel.tsx
│   │       ├── TensionChart.tsx
│   │       ├── LegendPanel.tsx
│   │       └── HoverTooltip.tsx
│   ├── lib/api.ts              ← all fetch() calls
│   └── types/index.ts          ← TypeScript interfaces
│
└── data/
    ├── processed/              ← daily_signals.csv, merged_dataset.csv
    ├── plots/                  ← PNG charts from step 4
    └── models/                 ← best_model.joblib (saved by step 4)
```

---

## Quick Start

### 1. Clone and enter

```bash
cd geotrade
```

### 2. Virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Windows / slow PyTorch install:** run this first:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### 4. Configure `.env`

```bash
copy .env.example .env    # Windows
cp .env.example .env      # macOS / Linux
```

Open `.env` and fill in at minimum:

```env
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net
MONGODB_DB=geotrade

# Optional — adds more data sources:
NEWS_API_KEY=your_newsapi_key          # newsapi.org (free tier)
GUARDIAN_API_KEY=your_guardian_key     # open-platform.theguardian.com (free)
GEMINI_API_KEY=your_gemini_key         # aistudio.google.com (free)
```

### 5. Run the pipeline

```bash
# All 5 steps in sequence (recommended for first run)
python scripts/run_all.py

# Skip step 4 (ML modeling) — faster, globe still works fully
python scripts/run_all.py --skip 4

# Resume from a specific step after a failure
python scripts/run_all.py --from 3

# Run only specific steps
python scripts/run_all.py --only 1 3 5
```

### 6. Start the API

```bash
uvicorn backend.main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open: [http://localhost:3000](http://localhost:3000)

---

## What Each Step Does

### Step 1 — News Ingestion (`step1_ingest.py`)

**What it does:**
Fetches geopolitical news articles from multiple sources and stores them in MongoDB after deduplication.

**Sources used (in order):**
| Source | Key required | Articles/run | Notes |
|--------|-------------|-------------|-------|
| GDELT Doc API | No (free) | ~2,000 | 90-day history, global coverage |
| 16 RSS feeds | No (free) | ~400 | BBC, Reuters, Al Jazeera, France24, DW, Guardian, NHK, Dawn, Times of India, VOA, AP, Africanews + more |
| NewsAPI | `NEWS_API_KEY` | ~1,000 | 20 targeted geopolitical queries |
| Guardian API | `GUARDIAN_API_KEY` | ~150 | Full article body text — best quality |
| Sample dataset | No | 30 | Bundled fallback articles |

**What gets stored in MongoDB (`raw_articles`):**
```
title, description, url, published_at, source, hash, ingested_at, processed=False
```

**Deduplication:** SHA-256 hash of `url + title`. Duplicate URLs are silently skipped.

**Time:** ~2–5 minutes (mostly GDELT rate-limiting at 1.5s per query)

---

### Step 2 — NLP Processing (`step2_nlp.py`)

**What it does:**
Reads every unprocessed article from `raw_articles` and runs three NLP tasks on the combined `title + description` text.

**Task 1 — Event Classification (BART)**
Uses `facebook/bart-large-mnli` (zero-shot) to classify into one of:
- `conflict` — war, battle, invasion, attack
- `diplomacy` — summit, treaty, agreement, negotiation
- `sanctions` — embargo, ban, export restriction
- `elections` — vote, coup, political unrest
- `trade` — tariff, trade war, GDP dispute

**Task 2 — Sentiment Analysis (DistilBERT)**
Uses `distilbert-base-uncased-finetuned-sst-2-english` to score POSITIVE / NEGATIVE with confidence. Converts to `neg_sentiment_score` (0–1, higher = more negative).

**Task 3 — Country NER (keyword matching)**
Scans text for 130+ country names, city names, and actor aliases (e.g. "Taliban" → AF, "Kremlin" → RU, "Houthi" → YE). Returns lat/lon/ISO for each match.

**Task 4 — Intensity Scoring (keyword-based)**
Scores how severe the article is on 0–1: nuclear/invasion/massacre → 0.8+, sanctions/coup/attack → 0.5, diplomatic talks → 0.2.

**What gets stored in MongoDB (`processed_events`):**
```
article_id, title, description, url, source, published_at,
event_label, event_score, sentiment_label, sentiment_score,
neg_sentiment_score, intensity_score, countries[], has_country_match,
processed_at
```

> **First run downloads ~1 GB of model weights from HuggingFace.** Cached locally after that.

**Time:** ~10–30 minutes depending on article count and whether GPU is available.

---

### Step 3 — Tension Scoring (`step3_score.py`)

**What it does:**
Aggregates all `processed_events` by `(date, country ISO)` and computes a daily tension score for each country.

**Formula:**
```
tension_score = α × avg_neg_sentiment  +  β × conflict_ratio

Default: α = 0.6, β = 0.4   (tunable via TENSION_ALPHA / TENSION_BETA in .env)
```

**Improvements in v2:**
- **Intensity-weighted average** — articles with nuclear/invasion keywords count more than routine diplomatic articles when computing the sentiment average
- **Smoothed score** — applies Bayesian shrinkage toward 0.5 when a country has few articles, reducing noise from single-article spikes
- **WLD filtering** — articles that matched no country are excluded from scoring (previously created phantom "World" globe entries)

**Thresholds:**
```
score ≥ 0.65 → HIGH   (red on globe)
score ≥ 0.35 → MEDIUM (amber on globe)
score  < 0.35 → LOW    (green on globe)
```

**What gets stored in MongoDB (`daily_signals`):**
```
date, country, iso, lat, lon,
tension_score, smoothed_score, tension_label,
avg_neg_sentiment, conflict_ratio, conflict_count,
event_count, article_count_log, top_event_label,
sample_title, sample_url, computed_at, alpha, beta
```

**Time:** ~5–30 seconds.

---

### Step 4 — Market Modeling (`step4_model.py`)

**What it does:**
Downloads VIX and S&P 500 data via yfinance, merges with daily tension signals, trains two classifiers to predict whether VIX will increase the next day, and saves the best model.

**Models trained:**
- `RandomForest` (200 trees, balanced class weights)
- `LightGBM` (300 estimators, learning rate 0.05)

**Features used:**
- `tension_score`, `conflict_ratio`, `event_count`
- Lagged tension (1d, 3d, 7d rolling avg)
- Event label one-hot encoding

**Target:** `vix_up` — binary, 1 if VIX increases next trading day

**Outputs:**
- `data/plots/` — 4 dark-theme charts (tension vs volatility, feature importance, ROC curves, model comparison)
- `data/models/best_model.joblib` — the better model (by AUC), loaded by the API
- `data/models/best_model_meta.joblib` — feature list, model name, AUC score

**The API (`/trading/{iso}`) automatically uses this model** for VIX direction predictions. If the model file doesn't exist yet (step 4 not run), it falls back to the heuristic.

> **Step 4 is optional for the globe to work.** The globe, forecasts, and Gemini briefings all work without it. Skip it with `--skip 4` to save time.

**Time:** ~5–15 minutes (yfinance download + training).

---

### Step 5 — Forecast Cache (`step5_forecast.py`)

**What it does:**
Pre-computes 7-day tension forecasts for every country in `daily_signals` and writes them to `tension_forecasts`.

**How the forecast works:**
1. Fetches the last 30 days of `tension_score` for the country
2. Fits a linear trend (numpy `polyfit`) on the last 14 days
3. Projects 7 days forward, clips to [0, 1]
4. Computes R² of the fit as a confidence signal

**Output per country:**
```
direction:         escalating | stable | de-escalating
pct_change:        % change from today to day 7
predictions:       [7 floats]  — one score per day
confidence_level:  high | medium | low
confidence_note:   plain-English explanation
```

**Note:** The API endpoint `GET /forecast/{iso}` computes this on-demand with a 60-minute cache. Step 5 just pre-warms the cache for all countries at once.

**Time:** ~5–10 seconds.

---

## Can I Just Use `run_all.py`?

**Yes — but read these notes first:**

| Scenario | Command |
|----------|---------|
| First time, everything | `python scripts/run_all.py` |
| First time, skip modeling | `python scripts/run_all.py --skip 4` |
| Step 2 failed (NLP error) | `python scripts/run_all.py --from 2` |
| Just re-ingest new articles | `python scripts/run_all.py --only 1 2 3 5` |
| Only refresh forecasts | `python scripts/run_all.py --only 5` |
| Nightly refresh (no retraining) | `python scripts/run_all.py --skip 4` |

**Common pitfall — step 2 is slow on first run:**
The first time step 2 runs it downloads ~1 GB of BART + DistilBERT weights from HuggingFace. This can take 5–20 minutes depending on your connection. Subsequent runs load from cache in ~10 seconds.

**Common pitfall — step 4 needs enough data:**
Step 4 needs at least 20 merged rows (tension + VIX on the same dates) to produce meaningful models. If you get a warning like "Very few data points", run steps 1–3 with `INGESTION_DAYS_BACK=90` in `.env` first, then retry step 4.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | MongoDB connectivity + collection counts |
| GET | `/stats` | Event label distribution, top countries by tension |
| GET | `/events` | All signals with lat/lon — consumed by the globe |
| GET | `/events/{iso}` | Signals for one country, e.g. `/events/RU` |
| GET | `/signals` | Daily global tension time series (30–90 day) |
| GET | `/trading/{iso}` | Stock signals + VIX prediction for a country |
| GET | `/forecast/{iso}` | 7-day tension forecast + sparkline data |
| GET | `/briefing/{iso}` | Gemini AI market briefing (cached 24h) |
| GET | `/docs` | Interactive Swagger UI |

**Query parameters on `/events`:**
- `tension_label=high|medium|low` — filter by tension level
- `date_from=YYYY-MM-DD` — earliest date
- `date_to=YYYY-MM-DD` — latest date
- `limit=500` — max results

---

## MongoDB Collections

| Collection | Written by | Key fields |
|------------|-----------|-----------|
| `raw_articles` | Step 1 | title, url, hash, source, processed |
| `processed_events` | Step 2 | event_label, sentiment, neg_sentiment_score, intensity_score, countries[], has_country_match |
| `daily_signals` | Step 3 | tension_score, smoothed_score, tension_label, lat, lon, iso |
| `tension_forecasts` | Step 5 / API | predictions[], direction, confidence_level, computed_at |
| `llm_briefings` | API `/briefing` | analysis{}, created_at (24h cache) |

---

## Adding More Data

### Free sources — no code changes needed

| Source | Setup | Coverage |
|--------|-------|---------|
| **GDELT** | Already enabled (free, no key) | Global, 90-day |
| **16 RSS feeds** | Already enabled | International + regional |
| **Guardian API** | Add `GUARDIAN_API_KEY` to `.env` → free at [open-platform.theguardian.com](https://open-platform.theguardian.com) | Full article body text |
| **NewsAPI** | Add `NEWS_API_KEY` to `.env` → free tier at [newsapi.org](https://newsapi.org) | 20 targeted geopolitical queries |

### Premium / research sources

| Source | Setup | Best for |
|--------|-------|---------|
| **ACLED** | Register at [acleddata.com](https://acleddata.com) (free for academic) → download CSV → `mongoimport` | Structured conflict events with exact locations + fatality counts |
| **ReliefWeb API** | Free, no key — `https://api.reliefweb.int/v1/reports` | UN humanitarian crises, displacement data |
| **EventRegistry** | Free tier at [eventregistry.org](https://eventregistry.org) | Cross-lingual news, event clustering |

### Add more RSS feeds

Open `pipeline/ingestion/sources.py` and append any feed URL to `RSS_FEEDS`:

```python
RSS_FEEDS = [
    ...
    "https://your-new-source.com/rss.xml",
]
```

### Increase history depth

In `.env`:
```env
INGESTION_DAYS_BACK=90   # default is 30 — increase for more historical data
MAX_ARTICLES_PER_RUN=2000
```

---

## Tension Score Formula

```
tension_score = α × intensity_weighted_neg_sentiment  +  β × conflict_ratio

Default: α = 0.6, β = 0.4

smoothed_score = tension_score × reliability  +  0.5 × (1 − reliability)
  where reliability = 1 − exp(−event_count / 5)
  → shrinks toward 0.5 when article count is low (< 5 events)
  → reaches full weight at ~20+ events

Thresholds:
  score ≥ 0.65  →  HIGH    (red globe marker)
  score ≥ 0.35  →  MEDIUM  (amber globe marker)
  score  < 0.35  →  LOW     (green globe marker)
```

---

## Environment Variables

```env
# Required
MONGODB_URI=mongodb+srv://...
MONGODB_DB=geotrade

# Optional — enables richer data sources
NEWS_API_KEY=...          # newsapi.org
GUARDIAN_API_KEY=...      # open-platform.theguardian.com
GEMINI_API_KEY=...        # aistudio.google.com

# Pipeline tuning
INGESTION_DAYS_BACK=30    # how far back to fetch news (increase for more data)
MAX_ARTICLES_PER_RUN=500  # cap total articles per ingestion run
NLP_BATCH_SIZE=8          # articles per HuggingFace batch

# Tension scoring weights (must sum to 1.0 for best results)
TENSION_ALPHA=0.6         # weight of neg sentiment
TENSION_BETA=0.4          # weight of conflict ratio

# API
API_HOST=0.0.0.0
API_PORT=8000
```

---

## Thesis Notes

- **NER is keyword-based** — extend `pipeline/nlp/ner.py` with spaCy `en_core_web_trf` for better entity detection in ambiguous contexts.
- **Sentiment model (SST-2)** is trained on movie reviews — consider swapping for `ProsusAI/finbert` or `yiyanghkust/finbert-tone` for financial news.
- **The globe falls back to 15 bundled demo events** when the API is offline — useful for presentations without a live backend.
- **All plots** are saved to `data/plots/` as high-DPI PNGs ready for thesis inclusion.
- **The ML model (step 4)** is intentionally simple — thesis-grade, not production. The LightGBM AUC of ~0.6–0.7 on limited data is expected and honest.
