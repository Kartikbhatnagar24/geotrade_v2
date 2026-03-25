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
}

export interface TradingPrediction {
  vix_direction: "increase" | "decrease" | "uncertain";
  confidence: number;
  confidence_pct: string;
  news_type_context: string;
  trade_idea: string;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
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
