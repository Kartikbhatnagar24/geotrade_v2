// frontend/pages/index.tsx
// Main page — orchestrates data fetching and lays out all UI panels.

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";

import type { GeoEvent, DailySignal, StatsData, FilterType } from "@/types";
import { fetchEvents, fetchSignals, fetchStats, checkHealth } from "@/lib/api";
import { DEMO_EVENTS } from "@/lib/constants";

import LoadingScreen  from "@/components/ui/LoadingScreen";
import StatBadge      from "@/components/ui/StatBadge";
import FilterPanel    from "@/components/panels/FilterPanel";
import TensionChart   from "@/components/panels/TensionChart";
import LegendPanel    from "@/components/panels/LegendPanel";
import HoverTooltip   from "@/components/panels/HoverTooltip";
import CountryTradingPanel from "@/components/panels/CountryTradingPanel";

// GlobeViewer must be client-only (WebGL APIs don't exist in Node.js SSR)
const GlobeViewer = dynamic(() => import("@/components/globe/GlobeViewer"), {
  ssr: false,
});

export default function Home() {
  // ── Data ────────────────────────────────────────────────────
  const [events,  setEvents]  = useState<GeoEvent[]>([]);
  const [signals, setSignals] = useState<DailySignal[]>([]);
  const [stats,   setStats]   = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiLive, setApiLive] = useState(true);

  // ── UI state ────────────────────────────────────────────────
  const [filter,        setFilter]        = useState<FilterType>("all");
  const [selectedEvent, setSelectedEvent] = useState<GeoEvent | null>(null);
  const [hoveredEvent,  setHoveredEvent]  = useState<GeoEvent | null>(null);
  const [mousePos,      setMousePos]      = useState({ x: 0, y: 0 });

  // ── Track mouse for tooltip positioning ─────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => setMousePos({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  // ── Fetch data from API ──────────────────────────────────────
  useEffect(() => {
    async function load() {
      const alive = await checkHealth();
      setApiLive(alive);

      if (alive) {
        const [ev, sig, st] = await Promise.all([
          fetchEvents(),
          fetchSignals(),
          fetchStats(),
        ]);
        setEvents(ev.length  > 0 ? ev  : DEMO_EVENTS);
        setSignals(sig);
        setStats(st);
      } else {
        // API offline — use demo data so the globe still renders
        setEvents(DEMO_EVENTS);
      }

      setLoading(false);
    }
    load();
  }, []);

  // ── Derived ─────────────────────────────────────────────────
  const visibleEvents =
    filter === "all" ? events : events.filter((e) => e.tension_label === filter);

  if (loading) return <LoadingScreen />;

  return (
    <>
      <Head>
        <title>GeoTrade — Geopolitical Intelligence Globe</title>
        <meta name="description" content="Geopolitical tension signal visualization" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* ── Globe (full-screen background) ──────────────────── */}
      <GlobeViewer
        events={events}
        filter={filter}
        onHover={setHoveredEvent}
        onClick={(ev) => {
          setSelectedEvent(ev);
          setHoveredEvent(null);
        }}
      />

      {/* ── Header bar ──────────────────────────────────────── */}
      <header className="fixed top-0 left-0 right-0 z-20 flex items-center justify-between px-5 py-3 pointer-events-none">
        {/* Logo */}
        <div className="flex items-center gap-3 pointer-events-auto">
          <div className="relative w-8 h-8">
            <div className="absolute inset-0 rounded-full border border-accent/20 animate-pulse-slow" />
            <div className="absolute inset-1.5 rounded-full border border-accent/50" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-mono text-accent text-[9px] font-bold">GT</span>
            </div>
          </div>
          <div>
            <p className="font-mono text-white font-bold text-sm tracking-widest leading-none">
              GEOTRADE
            </p>
            <p className="font-mono text-geo-text text-[9px] tracking-[0.3em]">
              INTELLIGENCE GLOBE
            </p>
          </div>
        </div>

        {/* Stats (hidden on small screens) */}
        <div className="hidden md:flex items-center gap-2 pointer-events-auto">
          {stats ? (
            <>
              <StatBadge label="ARTICLES"  value={stats.counts.raw_articles} />
              <StatBadge label="EVENTS"    value={stats.counts.processed_events} />
              <StatBadge label="SIGNALS"   value={stats.counts.daily_signals} />
            </>
          ) : (
            <div className="glass-panel px-3 py-1.5">
              <span className="font-mono text-[10px] text-geo-text">
                {visibleEvents.length} signals loaded
              </span>
            </div>
          )}

          {/* API status pill */}
          {!apiLive && (
            <div className="glass-panel px-3 py-1.5 border-yellow-500/30">
              <span className="font-mono text-[10px] text-yellow-400">
                ⚠ DEMO MODE — start the API
              </span>
            </div>
          )}
        </div>
      </header>

      {/* ── Left sidebar ────────────────────────────────────── */}
      <aside className="fixed left-3 top-16 bottom-16 z-20 w-56 flex flex-col gap-3 overflow-y-auto scrollbar-thin pointer-events-auto">
        <FilterPanel
          filter={filter}
          events={events}
          onChange={(f) => {
            setFilter(f);
            setSelectedEvent(null);
          }}
        />
        {signals.length > 0 && <TensionChart signals={signals} />}
        <LegendPanel />
      </aside>

      {/* ── Country Trading Panel (full right drawer) ────────── */}
      {selectedEvent ? (
        <CountryTradingPanel
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      ) : (
        <aside className="fixed right-3 top-16 z-20 w-60 pointer-events-auto">
          <div className="glass-panel p-4 text-center">
            <div className="text-[10px] font-mono text-geo-text tracking-widest mb-2">
              HOW TO USE
            </div>
            <p className="text-xs text-white/60 leading-relaxed">
              Click any <span className="text-white/90 font-semibold">country</span> on the globe for full trading analysis.
            </p>
            <p className="text-xs text-geo-text mt-2 leading-relaxed">
              News · Stocks · Prediction
            </p>
            <div className="mt-3 pt-3 border-t border-geo-border flex items-center justify-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <p className="text-[10px] font-mono text-geo-text ml-1">
                {visibleEvents.length} signals
              </p>
            </div>
          </div>
        </aside>
      )}

      {/* ── Hover tooltip ───────────────────────────────────── */}
      {hoveredEvent && !selectedEvent && (
        <HoverTooltip
          event={hoveredEvent}
          x={mousePos.x}
          y={mousePos.y}
        />
      )}

      {/* ── Bottom status bar ───────────────────────────────── */}
      <footer className="fixed bottom-3 left-0 right-0 z-20 flex justify-center pointer-events-none">
        <div className="glass-panel px-5 py-2 flex items-center gap-4">
          <span
            className={`w-1.5 h-1.5 rounded-full ${apiLive ? "bg-tension-low animate-pulse" : "bg-yellow-500"}`}
          />
          <span className="font-mono text-[10px] text-geo-text">
            {visibleEvents.length} SIGNALS
          </span>
          <span className="text-geo-border">|</span>
          <span className="font-mono text-[10px] text-geo-text">
            {apiLive ? "API LIVE" : "DEMO MODE"}
          </span>
          <span className="text-geo-border">|</span>
          <span className="font-mono text-[10px] text-geo-text hidden sm:block">
            {new Date().toUTCString().replace(" GMT", " UTC")}
          </span>
        </div>
      </footer>
    </>
  );
}
