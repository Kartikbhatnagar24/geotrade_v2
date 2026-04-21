# GeoTrade Thesis System

> End-to-end pipeline: geopolitical news → NLP → tension scores → market volatility model → 3D globe.

---

## Project Structure

```
geotrade/
│
├── .env.example              ← copy to .env and fill in your Atlas URI
├── requirements.txt          ← all Python dependencies
│
├── config/
│   └── settings.py           ← single source of all env vars (import from here)
│
├── pipeline/
│   ├── utils/
│   │   ├── db.py             ← MongoDB connection (Atlas-ready)
│   │   ├── text.py           ← clean_html, make_hash, truncate
│   │   └── logger.py         ← StepLogger used by all scripts
│   ├── ingestion/
│   │   ├── sources.py        ← NewsAPI + RSS feeds + bundled sample data
│   │   └── store.py          ← dedup + insert into raw_articles
│   ├── nlp/
│   │   ├── models.py         ← HuggingFace model cache (loaded once)
│   │   ├── classify.py       ← zero-shot event type + sentiment
│   │   ├── ner.py            ← country extraction via keyword matching
│   │   └── store.py          ← read raw_articles, write processed_events
│   ├── scoring/
│   │   ├── scorer.py         ← tension_score = α×neg_sentiment + β×conflict
│   │   └── store.py          ← upsert daily_signals, export CSV
│   └── modeling/
│       ├── features.py       ← load signals + yfinance, build feature matrix
│       ├── train.py          ← RandomForest + LightGBM trainers
│       └── plots.py          ← 4 thesis-ready dark-theme charts
│
├── scripts/                  ← run these in order
│   ├── step1_ingest.py
│   ├── step2_nlp.py
│   ├── step3_score.py
│   ├── step4_model.py
│   └── run_all.py            ← runs all 4 steps in sequence
│
├── backend/
│   ├── main.py               ← FastAPI app entry point
│   ├── core/
│   │   └── database.py       ← MongoDB connection for the API
│   ├── models/
│   │   └── schemas.py        ← Pydantic response models
│   └── routes/
│       ├── events.py         ← GET /events, GET /events/{iso}
│       └── signals.py        ← GET /signals
│
├── frontend/
│   ├── pages/
│   │   ├── _app.tsx
│   │   └── index.tsx         ← main page, wires all components together
│   ├── components/
│   │   ├── globe/
│   │   │   └── GlobeViewer.tsx   ← globe.gl 3D globe (client-only)
│   │   ├── panels/
│   │   │   ├── EventCard.tsx     ← right sidebar: selected event detail
│   │   │   ├── FilterPanel.tsx   ← left sidebar: tension filter buttons
│   │   │   ├── TensionChart.tsx  ← left sidebar: 30-day bar chart
│   │   │   ├── LegendPanel.tsx   ← left sidebar: colour legend
│   │   │   └── HoverTooltip.tsx  ← mouse-following hover card
│   │   └── ui/
│   │       ├── LoadingScreen.tsx
│   │       └── StatBadge.tsx
│   ├── lib/
│   │   ├── api.ts            ← all fetch() calls (never inline in components)
│   │   └── constants.ts      ← colours, formatters, demo data
│   ├── types/
│   │   └── index.ts          ← shared TypeScript interfaces
│   └── styles/
│       └── globals.css       ← Tailwind base + glass-panel + tooltip styles
│
├── data/
│   ├── raw/                  ← reserved for downloaded datasets
│   ├── processed/            ← daily_signals.csv, merged_dataset.csv
│   └── plots/                ← PNG charts from step 4
│
└── notebooks/
    └── analysis.ipynb        ← exploratory analysis, correlation plots
```

---

## Quick Start (Windows + MongoDB Atlas)

### 1 — Clone and enter the project

```
cd geotrade
```

### 2 — Create and activate a virtual environment

```cmd
python -m venv venv
venv\Scripts\activate
```

### 3 — Install Python dependencies

```cmd
pip install -r requirements.txt
```

> **Note — PyTorch on Windows:** if the above is slow, install PyTorch first:
> `pip install torch --index-url https://download.pytorch.org/whl/cpu`

### 4 — Configure environment

```cmd
copy .env.example .env
```

Open `.env` in any editor and set your Atlas URI:

```
MONGODB_URI=mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net
MONGODB_DB=geotrade
```

Optionally set a free NewsAPI key for richer data:

```
NEWS_API_KEY=your_key_here
```

### 5 — Run the pipeline

```cmd
python ml/scripts/run_all.py
```

Or step-by-step:

```cmd
python ml/scripts/step1_ingest.py
python ml/scripts/step2_nlp.py
python ml/scripts/step3_score.py
python ml/scripts/step4_model.py
```

Step 2 downloads ~1 GB of HuggingFace model weights on first run.

### 6 — Start the API

```cmd
uvicorn backend.main:app --reload --port 8000
```

Visit [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API docs.

### 7 — Start the frontend

```cmd
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## API Endpoints

| Method | Endpoint              | Description                                      |
|--------|-----------------------|--------------------------------------------------|
| GET    | `/health`             | MongoDB connectivity + collection counts         |
| GET    | `/stats`              | Label distributions, top countries by tension    |
| GET    | `/events`             | All signals with lat/lon (consumed by globe)     |
| GET    | `/events/{iso}`       | Signals for one country (e.g. `/events/RU`)      |
| GET    | `/signals`            | Daily global tension time series                 |
| GET    | `/docs`               | Auto-generated Swagger UI                        |

Query parameters on `/events`: `tension_label`, `date_from`, `date_to`, `limit`.

---

## MongoDB Collections

| Collection          | Written by  | Content                                      |
|---------------------|-------------|----------------------------------------------|
| `raw_articles`      | step 1      | Title, body, URL, hash, source, processed    |
| `processed_events`  | step 2      | Event label, sentiment, neg score, countries |
| `daily_signals`     | step 3      | tension_score, tension_label, lat/lon        |

---

## Tension Score Formula

```
tension_score = α × avg_neg_sentiment  +  β × conflict_ratio

Default: α = 0.6, β = 0.4   (tunable in .env)

Thresholds:
  score ≥ 0.65  →  HIGH    (red marker)
  score ≥ 0.35  →  MEDIUM  (amber marker)
  score  < 0.35  →  LOW     (green marker)
```

---

## Thesis Notes

- Models are intentionally simple (thesis-grade, not production).
- NER is keyword-based — extend `ml/pipeline/nlp/ner.py` to add spaCy for higher accuracy.
- The globe falls back to bundled demo data when the API is offline — useful for presentations.
- All plots are saved to `data/plots/` as high-DPI PNGs suitable for inclusion in a thesis PDF.
