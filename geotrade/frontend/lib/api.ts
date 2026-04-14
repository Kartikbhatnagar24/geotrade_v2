// frontend/lib/api.ts
// All backend API calls. Import from here — never fetch() inline in components.

import type { GeoEvent, DailySignal, StatsData, TradingData, ForecastData, BriefingData } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

export async function fetchEvents(filter?: string): Promise<GeoEvent[]> {
  const qs = filter && filter !== "all" ? `?tension_label=${filter}` : "";
  const data = await get<{ events: GeoEvent[] }>(`/events${qs}?limit=500`);
  return data?.events ?? [];
}

export async function fetchSignals(): Promise<DailySignal[]> {
  const data = await get<{ signals: DailySignal[] }>("/signals?limit=90");
  return data?.signals ?? [];
}

export async function fetchStats(): Promise<StatsData | null> {
  return get<StatsData>("/stats");
}

export async function checkHealth(): Promise<boolean> {
  const data = await get<{ status: string }>("/health");
  return data?.status === "ok";
}

export async function fetchTradingSignals(iso: string): Promise<TradingData | null> {
  return get<TradingData>(`/trading/${iso}`);
}

export async function fetchCountrySignals(iso: string): Promise<DailySignal[]> {
  const data = await get<{ signals: DailySignal[] }>(`/events/${iso}`);
  return (data as any)?.signals ?? [];
}

export async function fetchForecast(iso: string): Promise<ForecastData | null> {
  return get<ForecastData>(`/forecast/${iso}`);
}

export async function fetchBriefing(iso: string): Promise<BriefingData | null> {
  return get<BriefingData>(`/briefing/${iso}`);
}
