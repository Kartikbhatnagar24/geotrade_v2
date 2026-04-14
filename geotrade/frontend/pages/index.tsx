// frontend/pages/index.tsx
// Main page — orchestrates data fetching and lays out all UI panels.

import { useEffect, useState } from "react";
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

// ── Intelligence Overview panel (default state, no country selected) ──────────

function IntelOverview({ events }: { events: GeoEvent[] }) {
  const high   = events.filter((e) => e.tension_label === "high");
  const medium = events.filter((e) => e.tension_label === "medium");
  const low    = events.filter((e) => e.tension_label === "low");
  const total  = events.length || 1;

  // Top 4 hotspots by tension score
  const hotspots = [...events]
    .sort((a, b) => b.tension_score - a.tension_score)
    .slice(0, 4);

  // Global average
  const avgTension = events.length
    ? events.reduce((s, e) => s + e.tension_score, 0) / events.length
    : 0;

  const avgColor =
    avgTension >= 0.65 ? "#ef4444" :
    avgTension >= 0.35 ? "#f59e0b" : "#22c55e";

  const tensionLabelColor = (lbl: string) =>
    lbl === "high" ? "#ef4444" : lbl === "medium" ? "#f59e0b" : "#22c55e";

  return (
    <aside className="fixed right-3 top-[4.5rem] z-20 w-64 pointer-events-auto flex flex-col gap-2.5 animate-fade-in">

      {/* Global Overview */}
      <div className="glass-panel p-4">
        <p className="text-[10px] font-mono text-geo-text tracking-widest mb-3">
          GLOBAL INTELLIGENCE
        </p>

        {/* Avg tension gauge */}
        <div className="flex items-end justify-between mb-2">
          <div>
            <p className="text-[9px] text-white/35 font-mono mb-0.5">Avg Tension</p>
            <p className="text-2xl font-mono font-bold" style={{ color: avgColor }}>
              {Math.round(avgTension * 100)}
              <span className="text-sm font-normal text-white/30">/100</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-[9px] text-white/35 font-mono mb-0.5">Countries</p>
            <p className="text-2xl font-mono font-bold text-white/80">{events.length}</p>
          </div>
        </div>

        {/* Stacked proportion bar */}
        <div className="flex h-1.5 rounded-full overflow-hidden gap-px mb-2">
          {[
            { count: high.length,   color: "#ef4444" },
            { count: medium.length, color: "#f59e0b" },
            { count: low.length,    color: "#22c55e" },
          ].map(({ count, color }, i) => (
            <div
              key={i}
              className="transition-all duration-700"
              style={{ flex: count, background: color, opacity: 0.8 }}
            />
          ))}
        </div>

        {/* Breakdown row */}
        <div className="flex justify-between text-[10px] font-mono">
          <span className="text-red-400/80">{high.length} high</span>
          <span className="text-amber-400/80">{medium.length} med</span>
          <span className="text-emerald-400/80">{low.length} low</span>
        </div>
      </div>

      {/* Top Hotspots */}
      <div className="glass-panel p-3">
        <p className="text-[10px] font-mono text-geo-text tracking-widest mb-2.5">
          TOP HOTSPOTS
        </p>
        <div className="flex flex-col gap-1.5">
          {hotspots.map((e, i) => {
            const color = tensionLabelColor(e.tension_label);
            return (
              <div key={e.iso} className="flex items-center gap-2.5">
                <span className="text-[9px] font-mono text-white/25 w-3 shrink-0">
                  {i + 1}
                </span>
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: color, boxShadow: `0 0 4px ${color}` }}
                />
                <span className="text-[11px] font-mono text-white/75 flex-1 truncate">
                  {e.country}
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <div className="w-12 h-1 bg-white/8 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${e.tension_score * 100}%`, background: color, opacity: 0.7 }}
                    />
                  </div>
                  <span className="text-[9px] font-mono w-5 text-right" style={{ color }}>
                    {Math.round(e.tension_score * 100)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Call to action */}
      <div
        className="glass-panel p-3 text-center"
        style={{ borderColor: "rgba(56,189,248,0.12)" }}
      >
        <p className="text-[10px] font-mono text-accent/60 mb-1">CLICK ANY COUNTRY</p>
        <p className="text-[10px] text-white/40 leading-relaxed">
          News · Signals · Forecast · AI Briefing
        </p>
      </div>
    </aside>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

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
      <header className="fixed top-0 left-0 right-0 z-20 pointer-events-none">
        {/* Main header row */}
        <div className="flex items-center justify-between px-5 py-3">
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

          {/* Stats + status */}
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

            {/* Live/demo pill */}
            <div
              className="glass-panel px-3 py-1.5 flex items-center gap-1.5"
              style={{ borderColor: apiLive ? "rgba(34,197,94,0.2)" : "rgba(234,179,8,0.2)" }}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${apiLive ? "bg-emerald-400 animate-pulse" : "bg-yellow-400"}`}
              />
              <span className={`font-mono text-[10px] ${apiLive ? "text-emerald-400" : "text-yellow-400"}`}>
                {apiLive ? "LIVE" : "DEMO"}
              </span>
            </div>
          </div>
        </div>

        {/* Thin tension indicator bar at very bottom of header */}
        {signals.length > 0 && (() => {
          const last   = signals[signals.length - 1];
          const v      = last?.global_tension ?? 0;
          const color  = v >= 0.65 ? "#ef4444" : v >= 0.35 ? "#f59e0b" : "#22c55e";
          return (
            <div className="h-px w-full" style={{ background: `rgba(255,255,255,0.04)` }}>
              <div
                className="h-full transition-all duration-1000"
                style={{ width: `${v * 100}%`, background: color, opacity: 0.5 }}
              />
            </div>
          );
        })()}
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
        <IntelOverview events={events} />
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
        <div className="glass-panel px-5 py-2 flex items-center gap-3">
          {/* Counts */}
          <span className="font-mono text-[10px] text-white/50">
            <span className="text-white/80 font-bold">{events.filter(e=>e.tension_label==="high").length}</span>
            <span className="text-red-400/70"> HIGH</span>
          </span>
          <span className="text-geo-border/60">·</span>
          <span className="font-mono text-[10px] text-white/50">
            <span className="text-white/80 font-bold">{events.filter(e=>e.tension_label==="medium").length}</span>
            <span className="text-amber-400/70"> MED</span>
          </span>
          <span className="text-geo-border/60">·</span>
          <span className="font-mono text-[10px] text-white/50">
            <span className="text-white/80 font-bold">{events.filter(e=>e.tension_label==="low").length}</span>
            <span className="text-emerald-400/70"> LOW</span>
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
