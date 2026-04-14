// frontend/types/index.ts
// Shared TypeScript types used across all components.

export interface GeoEvent {
  country: string;
  iso: string;
  latitude: number;
  longitude: number;
  tension_score: number;
  tension_label: TensionLabel;
  event_label: EventLabel;
  event_count: number;
  date: string;
  sample_title: string;
  sample_url: string;
}

export interface DailySignal {
  date: string;
  global_tension: number;
  max_tension: number;
  total_events: number;
  countries_affected: number;
}

export interface StatsData {
  counts: {
    raw_articles: number;
    processed_events: number;
    daily_signals: number;
  };
  event_labels: Record<string, number>;
  tension_labels: Record<string, number>;
  top_countries_by_tension: Array<{
    country: string;
    iso: string;
    avg_tension: number;
  }>;
}

export type TensionLabel = "high" | "medium" | "low";
export type EventLabel = "conflict" | "diplomacy" | "sanctions" | "elections" | "trade" | "unknown";
export type FilterType = "all" | TensionLabel;

export interface StockSignal {
  ticker: string;
  name: string;
  type: string;
  direction: "LONG" | "SHORT" | "WATCH";
  rationale: string;
  price: number | null;
  change_5d: number | null;
  error?: string;
}

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  date: string;
  news_type: string;
  event_label: string;
  sentiment_label?: string;   // "NEGATIVE" | "NEUTRAL" | "POSITIVE"
  sentiment_score?: number;   // 0-1
  intensity_score?: number;   // 0-1
}

export interface TensionMomentum {
  change_3d: number;           // e.g. +0.08 or -0.05
  change_7d: number;
  acceleration: "rising" | "steady" | "falling";
  signal_strength: "strong" | "moderate" | "weak";
  scores?: number[];
  dates?: string[];
}

export interface MarketSignal {
  asset_class: string;         // "Safe Havens", "Energy/Oil", etc.
  tickers: string[];           // ["GLD", "TLT"]
  direction: "LONG" | "SHORT" | "WATCH";
  conviction: number;          // 1-5
  rationale: string;
}

export interface TradingPrediction {
  vix_direction: "increase" | "decrease" | "uncertain";
  confidence: number;
  confidence_pct: string;
  news_type_context: string;
  trade_idea: string;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  model_source?: string;
  tension_momentum?: TensionMomentum;
  market_signals?: MarketSignal[];
  key_risks?: string[];
  positioning_summary?: string;
}

export interface TradingData {
  country_iso: string;
  tension: {
    tension_score: number;
    tension_label: string;
    date: string;
    event_count: number;
    top_event_label: string;
    sample_title: string;
    sample_url: string;
  };
  dominant_news_type: string;
  recent_news: NewsItem[];
  stock_signals: StockSignal[];
  prediction: TradingPrediction;
}

// ── /forecast ─────────────────────────────────────────────────────

export interface ForecastData {
  iso:              string;
  current_score:    number;
  history_scores:   number[];   // last 7 actuals
  history_dates:    string[];
  predictions:      number[];   // next 7 projected
  forecast_dates:   string[];
  direction:        "escalating" | "stable" | "de-escalating";
  pct_change:       number;
  slope_per_day:    number;
  confidence_r2:    number;
  confidence_level: "high" | "medium" | "low";
  confidence_note:  string;
  data_points_used: number;
  computed_at:      string;
  from_cache:       boolean;
}

// ── /briefing ─────────────────────────────────────────────────────

export interface TradeIdea {
  asset:     string;
  direction: "LONG" | "SHORT";
  reasoning: string;
}

export interface BriefingAnalysis {
  geopolitical_summary: string;
  market_impact:        string;
  affected_assets:      string[];
  trade_ideas:          TradeIdea[];
  risk_level:           "high" | "medium" | "low";
  confidence_note:      string;
}

export interface BriefingData {
  iso:     string;
  country: string;
  tension_snapshot: {
    score: number | null;
    label: string | null;
    date:  string | null;
  };
  analysis:   BriefingAnalysis;
  created_at: string;
  model:      string;
  from_cache: boolean;
}
