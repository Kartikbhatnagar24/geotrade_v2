// frontend/pages/index.tsx

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";

import type { GeoEvent, DailySignal, StatsData, FilterType } from "@/types";
import { fetchEvents, fetchSignals, fetchStats, checkHealth } from "@/lib/api";
import { DEMO_EVENTS } from "@/lib/constants";

import LoadingScreen       from "@/components/ui/LoadingScreen";
import FilterPanel         from "@/components/panels/FilterPanel";
import TensionChart        from "@/components/panels/TensionChart";
import HoverTooltip        from "@/components/panels/HoverTooltip";
import CountryTradingPanel from "@/components/panels/CountryTradingPanel";

const GlobeViewer = dynamic(() => import("@/components/globe/GlobeViewer"), {
  ssr: false,
});

// ── Global overview panel (shown when no country is selected) ─────────────

function IntelOverview({ events }: { events: GeoEvent[] }) {
  const high   = events.filter((e) => e.tension_label === "high");
  const medium = events.filter((e) => e.tension_label === "medium");
  const low    = events.filter((e) => e.tension_label === "low");
  const total  = events.length || 1;

  const hotspots = [...events]
    .sort((a, b) => b.tension_score - a.tension_score)
    .slice(0, 5);

  const avgTension = events.length
    ? events.reduce((s, e) => s + e.tension_score, 0) / events.length
    : 0;

  const avgColor =
    avgTension >= 0.65 ? "var(--signal-high)" :
    avgTension >= 0.35 ? "var(--signal-mid)"  : "var(--signal-low)";

  const tlColor = (lbl: string) =>
    lbl === "high" ? "var(--signal-high)" :
    lbl === "medium" ? "var(--signal-mid)" : "var(--signal-low)";

  return (
    <aside className="fixed right-3 top-[4.5rem] z-20 w-64 pointer-events-auto flex flex-col gap-2.5 animate-fade-in">

      {/* Global gauge */}
      <div className="glass-panel p-4">
        <p className="font-mono text-[9px] tracking-[0.25em] mb-0.5" style={{ color: "var(--geo-text-2)" }}>
          GLOBAL TENSION
        </p>

        <div className="flex items-end justify-between mt-2 mb-2.5">
          <div>
            <p className="font-mono text-[8px] mb-0.5" style={{ color: "var(--geo-text)" }}>AVG SCORE</p>
            <p className="font-mono text-3xl font-bold leading-none" style={{ color: avgColor }}>
              {Math.round(avgTension * 100)}
              <span className="text-sm font-normal" style={{ color: "rgba(255,255,255,0.2)" }}>/100</span>
            </p>
          </div>
          <div className="text-right">
            <p className="font-mono text-[8px] mb-0.5" style={{ color: "var(--geo-text)" }}>COUNTRIES</p>
            <p className="font-mono text-3xl font-bold leading-none" style={{ color: "rgba(255,255,255,0.7)" }}>
              {events.length}
            </p>
          </div>
        </div>

        {/* Proportion bar */}
        <div className="flex h-1 rounded-full overflow-hidden gap-px mb-2">
          {[
            { count: high.length,   color: "var(--signal-high)" },
            { count: medium.length, color: "var(--signal-mid)"  },
            { count: low.length,    color: "var(--signal-low)"  },
          ].map(({ count, color }, i) => (
            <div
              key={i}
              className="transition-all duration-700"
              style={{ flex: count, background: color, opacity: 0.7 }}
            />
          ))}
        </div>

        <div className="flex justify-between font-mono text-[9px]">
          <span style={{ color: "var(--signal-high)" }}>{high.length} HIGH</span>
          <span style={{ color: "var(--signal-mid)" }}>{medium.length} MED</span>
          <span style={{ color: "var(--signal-low)" }}>{low.length} LOW</span>
        </div>
      </div>

      {/* Top hotspots */}
      <div className="glass-panel p-3">
        <p className="font-mono text-[9px] tracking-[0.25em] mb-3" style={{ color: "var(--geo-text-2)" }}>
          TOP HOTSPOTS
        </p>
        <div className="flex flex-col gap-2">
          {hotspots.map((e, i) => {
            const color = tlColor(e.tension_label);
            return (
              <div key={e.iso} className="flex items-center gap-2.5">
                <span className="font-mono text-[9px] w-3 shrink-0" style={{ color: "var(--geo-text)" }}>
                  {i + 1}
                </span>
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: color, boxShadow: `0 0 5px ${color}` }}
                />
                <span className="font-mono text-[10px] flex-1 truncate" style={{ color: "rgba(255,255,255,0.7)" }}>
                  {e.country}
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <div className="w-12 h-0.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${e.tension_score * 100}%`, background: color, opacity: 0.8 }}
                    />
                  </div>
                  <span className="font-mono text-[9px] w-5 text-right" style={{ color }}>
                    {Math.round(e.tension_score * 100)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

    </aside>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Home() {
  const [events,  setEvents]  = useState<GeoEvent[]>([]);
  const [signals, setSignals] = useState<DailySignal[]>([]);
  const [stats,   setStats]   = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiLive, setApiLive] = useState(true);

  const [filter,        setFilter]        = useState<FilterType>("all");
  const [selectedEvent, setSelectedEvent] = useState<GeoEvent | null>(null);
  const [hoveredEvent,  setHoveredEvent]  = useState<GeoEvent | null>(null);
  const [mousePos,      setMousePos]      = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handler = (e: MouseEvent) => setMousePos({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  useEffect(() => {
    async function load() {
      const alive = await checkHealth();
      setApiLive(alive);
      if (alive) {
        const [ev, sig, st] = await Promise.all([fetchEvents(), fetchSignals(), fetchStats()]);
        setEvents(ev.length > 0 ? ev : DEMO_EVENTS);
        setSignals(sig);
        setStats(st);
      } else {
        setEvents(DEMO_EVENTS);
      }
      setLoading(false);
    }
    load();
  }, []);

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

      {/* Globe */}
      <GlobeViewer
        events={events}
        filter={filter}
        onHover={setHoveredEvent}
        onClick={(ev) => {
          setSelectedEvent(ev);
          setHoveredEvent(null);
        }}
      />

      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-20 pointer-events-none">
        <div className="flex items-center justify-between px-5 py-3">
          {/* Logo */}
          <div className="flex items-center gap-3 pointer-events-auto">
            <div className="relative w-8 h-8">
              <div
                className="absolute inset-0 rounded-full border animate-pulse-slow"
                style={{ borderColor: "rgba(0,212,188,0.18)" }}
              />
              <div
                className="absolute inset-1.5 rounded-full border"
                style={{ borderColor: "rgba(0,212,188,0.45)" }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="font-mono text-[9px] font-bold" style={{ color: "var(--accent)" }}>GT</span>
              </div>
            </div>
            <div>
              <p className="font-bold text-sm tracking-widest leading-none" style={{ color: "rgba(255,255,255,0.92)" }}>
                GEOTRADE
              </p>
              <p className="font-mono text-[8px] tracking-[0.3em]" style={{ color: "var(--geo-text)" }}>
                INTELLIGENCE GLOBE
              </p>
            </div>
          </div>

          {/* Status */}
          <div className="pointer-events-auto">
            <div
              className="glass-panel px-3 py-1.5 flex items-center gap-1.5"
              style={{ borderColor: apiLive ? "rgba(0,200,74,0.2)" : "rgba(232,144,32,0.2)" }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: apiLive ? "var(--signal-low)" : "var(--signal-mid)",
                  animation: apiLive ? "pulseGlow 1.8s ease-in-out infinite" : "none",
                }}
              />
              <span
                className="font-mono text-[10px]"
                style={{ color: apiLive ? "var(--signal-low)" : "var(--signal-mid)" }}
              >
                {apiLive ? "LIVE" : "DEMO"}
              </span>
              {events.length > 0 && (
                <>
                  <span style={{ color: "var(--geo-border-2)" }}>·</span>
                  <span className="font-mono text-[10px]" style={{ color: "var(--geo-text)" }}>
                    {events.length} signals
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Tension indicator line */}
        {signals.length > 0 && (() => {
          const last  = signals[signals.length - 1];
          const v     = last?.global_tension ?? 0;
          const color = v >= 0.65 ? "var(--signal-high)" : v >= 0.35 ? "var(--signal-mid)" : "var(--signal-low)";
          return (
            <div className="h-px w-full" style={{ background: "rgba(255,255,255,0.03)" }}>
              <div
                className="h-full transition-all duration-1000"
                style={{ width: `${v * 100}%`, background: color, opacity: 0.45 }}
              />
            </div>
          );
        })()}
      </header>

      {/* Left sidebar */}
      <aside className="fixed left-3 top-16 bottom-4 z-20 w-56 flex flex-col gap-3 overflow-y-auto scrollbar-thin pointer-events-auto">
        <FilterPanel
          filter={filter}
          events={events}
          onChange={(f) => {
            setFilter(f);
            setSelectedEvent(null);
          }}
        />
        {signals.length > 0 && <TensionChart signals={signals} />}
      </aside>

      {/* Country panel or global overview */}
      {selectedEvent ? (
        <CountryTradingPanel
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      ) : (
        <IntelOverview events={events} />
      )}

      {/* Hover tooltip */}
      {hoveredEvent && !selectedEvent && (
        <HoverTooltip
          event={hoveredEvent}
          x={mousePos.x}
          y={mousePos.y}
        />
      )}
    </>
  );
}
