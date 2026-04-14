// frontend/components/panels/CountryTradingPanel.tsx
// Trading analysis drawer — slides in when a country is selected.
// Tabs: 📰 News | 💹 Signals | 📈 Forecast | 🤖 AI

import { useEffect, useState } from "react";
import type {
  GeoEvent, TradingData, StockSignal, NewsItem,
  ForecastData, BriefingData, TradeIdea,
  TensionMomentum, MarketSignal, TradingPrediction,
} from "@/types";
import { fetchTradingSignals, fetchForecast, fetchBriefing } from "@/lib/api";

// ── Shared micro-components ────────────────────────────────────────────────

function TensionBar({ score }: { score: number }) {
  const pct   = Math.round(score * 100);
  const color = score >= 0.65 ? "#ef4444" : score >= 0.35 ? "#f59e0b" : "#22c55e";
  return (
    <div className="w-full bg-white/5 rounded-full h-1.5 mt-1">
      <div
        className="h-1.5 rounded-full transition-all duration-700"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

function DirectionBadge({ dir }: { dir: "LONG" | "SHORT" | "WATCH" }) {
  const cfg = {
    LONG:  { bg: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", icon: "↑" },
    SHORT: { bg: "bg-red-500/15 text-red-400 border-red-500/30",             icon: "↓" },
    WATCH: { bg: "bg-amber-500/15 text-amber-400 border-amber-500/30",       icon: "◎" },
  }[dir];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${cfg.bg}`}>
      {cfg.icon} {dir}
    </span>
  );
}

function NewsTypePill({ type }: { type: string }) {
  const colorMap: Record<string, string> = {
    conflict:     "bg-red-500/20 text-red-300",
    military:     "bg-orange-500/20 text-orange-300",
    sanctions:    "bg-purple-500/20 text-purple-300",
    economic:     "bg-blue-500/20 text-blue-300",
    diplomatic:   "bg-cyan-500/20 text-cyan-300",
    humanitarian: "bg-pink-500/20 text-pink-300",
    other:        "bg-white/10 text-white/50",
  };
  return (
    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider ${colorMap[type] ?? colorMap.other}`}>
      {type}
    </span>
  );
}

function SentimentPill({ label, score }: { label?: string; score?: number }) {
  if (!label) return null;
  const lc = label.toLowerCase();
  const cfg =
    lc === "negative" ? "bg-red-500/15 text-red-400 border-red-500/25" :
    lc === "positive" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" :
                        "bg-white/8 text-white/40 border-white/10";
  const icon = lc === "negative" ? "▼" : lc === "positive" ? "▲" : "–";
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border text-[8px] font-mono ${cfg}`}>
      {icon} {label.slice(0, 3)}
      {score != null && <span className="opacity-60 ml-0.5">{Math.round(score * 100)}</span>}
    </span>
  );
}

function IntensityDot({ score }: { score?: number }) {
  if (score == null) return null;
  const color =
    score >= 0.5 ? "#ef4444" :
    score >= 0.25 ? "#f59e0b" : "rgba(255,255,255,0.2)";
  return (
    <span
      title={`Intensity: ${Math.round(score * 100)}%`}
      className="inline-block w-1.5 h-1.5 rounded-full shrink-0 mt-0.5"
      style={{ background: color, boxShadow: score >= 0.5 ? `0 0 4px ${color}` : "none" }}
    />
  );
}

function RiskBadge({ level }: { level: string }) {
  const cfg: Record<string, string> = {
    high:   "text-red-400 bg-red-500/15 border-red-500/30 animate-pulse",
    medium: "text-amber-400 bg-amber-500/15 border-amber-500/30",
    low:    "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
    HIGH:   "text-red-400 bg-red-500/15 border-red-500/30 animate-pulse",
    MEDIUM: "text-amber-400 bg-amber-500/15 border-amber-500/30",
    LOW:    "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded border text-[11px] font-mono font-bold ${cfg[level] ?? cfg.medium}`}>
      ⚠ RISK: {level.toUpperCase()}
    </span>
  );
}

function ConvictionStars({ n }: { n: number }) {
  return (
    <span className="font-mono text-[11px] tracking-[-1px]">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} style={{ color: i < n ? "#f59e0b" : "rgba(255,255,255,0.12)" }}>★</span>
      ))}
    </span>
  );
}

function AssetClassIcon({ name }: { name: string }) {
  const icons: Record<string, string> = {
    "Safe Havens":    "🛡",
    "Energy/Oil":     "⛽",
    "Defense":        "🎯",
    "Semiconductors": "💾",
    "Agriculture":    "🌾",
    "Local Equity":   "📊",
    "FX / Dollar":    "💱",
  };
  return <span className="text-[13px]">{icons[name] ?? "📌"}</span>;
}

function Spinner({ color }: { color: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-white/30">
      <div
        className="w-8 h-8 rounded-full border-2 border-white/10"
        style={{ borderTopColor: color, animation: "spin 1s linear infinite" }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <p className="text-[10px] font-mono">Loading…</p>
    </div>
  );
}

// ── Tab: News ──────────────────────────────────────────────────────────────

function NewsTab({ news }: { news: NewsItem[] }) {
  if (!news.length)
    return <p className="text-xs text-white/40 text-center py-6">No recent news found for this country.</p>;

  return (
    <div className="flex flex-col gap-2.5">
      {news.map((item, i) => (
        <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          {/* Row 1: type pill + sentiment + intensity dot + date */}
          <div className="flex items-center justify-between gap-1.5 mb-1.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              <NewsTypePill type={item.news_type} />
              <SentimentPill label={item.sentiment_label} score={item.sentiment_score} />
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <IntensityDot score={item.intensity_score} />
              <span className="text-[9px] text-white/35 font-mono">
                {item.date ? item.date.slice(0, 10) : "—"}
              </span>
            </div>
          </div>

          {/* Headline */}
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-white/80 hover:text-white leading-relaxed line-clamp-2 block transition-colors"
            >
              {item.title}
            </a>
          ) : (
            <p className="text-xs text-white/80 leading-relaxed line-clamp-2">{item.title}</p>
          )}

          {/* Source */}
          {item.source && (
            <p className="text-[9px] text-white/30 mt-1 font-mono">{item.source.split(":").pop()}</p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Tab: Signals (Stocks + Market Intelligence) ────────────────────────────

function PositioningSummaryCard({ summary }: { summary: string }) {
  const upper = summary.toUpperCase();
  const isDefensive   = upper.startsWith("DEFENSIVE");
  const isCautious    = upper.startsWith("CAUTIOUS");
  const isConstructive= upper.startsWith("CONSTRUCTIVE");

  const color =
    isDefensive    ? "#ef4444" :
    isCautious     ? "#f59e0b" :
    isConstructive ? "#22c55e" : "#94a3b8";

  const bg =
    isDefensive    ? "rgba(239,68,68,0.07)"  :
    isCautious     ? "rgba(245,158,11,0.07)" :
    isConstructive ? "rgba(34,197,94,0.07)"  : "rgba(255,255,255,0.04)";

  return (
    <div
      className="rounded-xl p-3 border"
      style={{ background: bg, borderColor: `${color}25` }}
    >
      <p className="text-[9px] font-mono uppercase tracking-wider mb-1.5" style={{ color: `${color}99` }}>
        Positioning
      </p>
      <p className="text-xs font-mono leading-relaxed" style={{ color }}>
        {summary}
      </p>
    </div>
  );
}

function MarketSignalCard({ signal }: { signal: MarketSignal }) {
  const dirColor =
    signal.direction === "LONG"  ? "#22c55e" :
    signal.direction === "SHORT" ? "#ef4444" : "#f59e0b";

  const dirBg =
    signal.direction === "LONG"  ? "rgba(34,197,94,0.08)"  :
    signal.direction === "SHORT" ? "rgba(239,68,68,0.08)"  : "rgba(245,158,11,0.08)";

  return (
    <div
      className="rounded-xl p-3 border transition-colors"
      style={{
        background:   dirBg,
        borderColor:  `${dirColor}20`,
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <AssetClassIcon name={signal.asset_class} />
          <span className="text-[11px] font-mono font-semibold text-white/80">
            {signal.asset_class}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ConvictionStars n={signal.conviction} />
          <DirectionBadge dir={signal.direction} />
        </div>
      </div>

      {/* Tickers */}
      <div className="flex flex-wrap gap-1 mb-2">
        {signal.tickers.map((t) => (
          <span
            key={t}
            className="text-[9px] font-mono px-1.5 py-0.5 rounded"
            style={{
              color:        dirColor,
              background:   `${dirColor}12`,
              border:       `1px solid ${dirColor}30`,
            }}
          >
            {t}
          </span>
        ))}
      </div>

      {/* Rationale */}
      <p className="text-[10px] text-white/50 leading-relaxed">{signal.rationale}</p>
    </div>
  );
}

function KeyRisksCard({ risks }: { risks: string[] }) {
  if (!risks.length) return null;
  return (
    <div className="bg-white/5 rounded-xl p-3 border border-red-500/15">
      <p className="text-[9px] text-red-400/70 font-mono uppercase tracking-wider mb-2">
        ⚡ Key Risks
      </p>
      <div className="flex flex-col gap-1.5">
        {risks.map((r, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="text-red-500/50 text-[10px] mt-0.5 shrink-0">▸</span>
            <p className="text-[10px] text-white/55 leading-relaxed">{r}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function SignalsTab({
  signals,
  prediction,
}: {
  signals: StockSignal[];
  prediction: TradingPrediction | null;
}) {
  const marketSignals = prediction?.market_signals ?? [];
  const keyRisks      = prediction?.key_risks ?? [];
  const positioning   = prediction?.positioning_summary ?? "";

  return (
    <div className="flex flex-col gap-3">

      {/* Positioning summary */}
      {positioning && <PositioningSummaryCard summary={positioning} />}

      {/* Market Signals */}
      {marketSignals.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[9px] text-white/35 font-mono uppercase tracking-wider px-0.5">
            Market Signals — {marketSignals.length} asset classes
          </p>
          {marketSignals.map((sig, i) => (
            <MarketSignalCard key={i} signal={sig} />
          ))}
        </div>
      )}

      {/* Key Risks */}
      <KeyRisksCard risks={keyRisks} />

      {/* Divider + individual stock prices */}
      {signals.length > 0 && (
        <>
          <div className="flex items-center gap-2 mt-1">
            <div className="flex-1 h-px bg-white/8" />
            <p className="text-[9px] text-white/25 font-mono uppercase tracking-wider shrink-0">
              Live Prices
            </p>
            <div className="flex-1 h-px bg-white/8" />
          </div>

          <div className="flex flex-col gap-2">
            {signals.map((s, i) => (
              <div
                key={i}
                className="bg-white/5 rounded-lg px-3 py-2 border border-white/5 hover:border-white/10 transition-colors flex items-center justify-between"
              >
                <div className="flex-1 min-w-0 pr-2">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-mono font-bold text-xs text-white">{s.ticker}</span>
                    <span className="text-[8px] text-white/30 font-mono truncate">{s.type}</span>
                  </div>
                  <p className="text-[9px] text-white/40 truncate">{s.name}</p>
                </div>
                <div className="text-right shrink-0">
                  {s.price != null && (
                    <p className="text-xs font-mono text-white/80">${s.price.toFixed(2)}</p>
                  )}
                  {s.change_5d != null && (
                    <p className={`text-[9px] font-mono ${s.change_5d >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {s.change_5d >= 0 ? "+" : ""}{s.change_5d.toFixed(2)}% 5d
                    </p>
                  )}
                  {s.error && <p className="text-[8px] text-white/20 font-mono">n/a</p>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Fallback if no signals at all */}
      {marketSignals.length === 0 && signals.length === 0 && (
        <p className="text-xs text-white/40 text-center py-6">No market signals available.</p>
      )}
    </div>
  );
}

// ── Tab: Forecast ──────────────────────────────────────────────────────────

function MomentumStrip({ momentum }: { momentum: TensionMomentum }) {
  const accelColor =
    momentum.acceleration === "rising"  ? "#ef4444" :
    momentum.acceleration === "falling" ? "#22c55e" : "#f59e0b";

  const accelIcon =
    momentum.acceleration === "rising"  ? "↑" :
    momentum.acceleration === "falling" ? "↓" : "→";

  const fmt = (v: number) =>
    `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}pts`;

  const color3d = momentum.change_3d > 0 ? "#ef4444" : momentum.change_3d < 0 ? "#22c55e" : "#94a3b8";
  const color7d = momentum.change_7d > 0 ? "#ef4444" : momentum.change_7d < 0 ? "#22c55e" : "#94a3b8";

  const strengthBg =
    momentum.signal_strength === "strong"   ? "rgba(239,68,68,0.12)"  :
    momentum.signal_strength === "moderate" ? "rgba(245,158,11,0.12)" : "rgba(255,255,255,0.06)";

  return (
    <div className="bg-white/5 rounded-xl p-3 border border-white/5">
      <p className="text-[9px] text-white/35 font-mono uppercase tracking-wider mb-2.5">
        Tension Momentum
      </p>
      <div className="grid grid-cols-3 gap-2">
        {/* 3-day change */}
        <div className="text-center">
          <p className="text-[8px] text-white/30 font-mono mb-1">3-Day Δ</p>
          <p className="text-sm font-mono font-bold" style={{ color: color3d }}>
            {fmt(momentum.change_3d)}
          </p>
        </div>
        {/* 7-day change */}
        <div className="text-center">
          <p className="text-[8px] text-white/30 font-mono mb-1">7-Day Δ</p>
          <p className="text-sm font-mono font-bold" style={{ color: color7d }}>
            {fmt(momentum.change_7d)}
          </p>
        </div>
        {/* Trend / acceleration */}
        <div className="text-center">
          <p className="text-[8px] text-white/30 font-mono mb-1">Trend</p>
          <p className="text-sm font-mono font-bold" style={{ color: accelColor }}>
            {accelIcon} {momentum.acceleration}
          </p>
        </div>
      </div>
      {/* Signal strength pill */}
      <div className="flex justify-center mt-2.5">
        <span
          className="text-[9px] font-mono uppercase px-2 py-0.5 rounded-full"
          style={{ background: strengthBg, color: accelColor, border: `1px solid ${accelColor}25` }}
        >
          {momentum.signal_strength} signal
        </span>
      </div>
    </div>
  );
}

function ForecastSparkline({ forecast, momentum }: { forecast: ForecastData; momentum?: TensionMomentum }) {
  const W = 294, H = 80, PAD = 8;

  const allScores = [...forecast.history_scores, ...forecast.predictions];
  const allDates  = [...forecast.history_dates,  ...forecast.forecast_dates];
  const splitIdx  = forecast.history_scores.length;
  const total     = allScores.length;

  const minV = Math.min(...allScores, 0);
  const maxV = Math.max(...allScores, 1);
  const range = maxV - minV || 1;

  const toX = (i: number) => PAD + (i / (total - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);

  const historyPoints  = forecast.history_scores.map((s, i) => `${toX(i)},${toY(s)}`);
  const forecastPoints = forecast.predictions.map((s, i) =>
    `${toX(splitIdx - 1 + i + 1)},${toY(s)}`
  );

  const histPath    = `M ${historyPoints.join(" L ")}`;
  const lastHistX   = toX(splitIdx - 1);
  const lastHistY   = toY(forecast.history_scores[forecast.history_scores.length - 1]);
  const fcastPath   = `M ${lastHistX},${lastHistY} L ${forecastPoints.join(" L ")}`;
  const todayX      = lastHistX;

  const dirColor =
    forecast.direction === "escalating"    ? "#ef4444" :
    forecast.direction === "de-escalating" ? "#22c55e" : "#f59e0b";

  const dirArrow =
    forecast.direction === "escalating"    ? "↑" :
    forecast.direction === "de-escalating" ? "↓" : "→";

  const confColor =
    forecast.confidence_level === "high"   ? "#22c55e" :
    forecast.confidence_level === "medium" ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col gap-3">

      {/* Momentum strip — shown at top of forecast if available */}
      {momentum && <MomentumStrip momentum={momentum} />}

      {/* Direction header */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5 flex items-center justify-between">
        <div>
          <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-1">
            7-Day Tension Forecast
          </p>
          <div className="flex items-center gap-2">
            <span className="text-xl font-mono font-bold" style={{ color: dirColor }}>
              {dirArrow}
            </span>
            <span className="text-sm font-mono font-bold" style={{ color: dirColor }}>
              {forecast.direction.charAt(0).toUpperCase() + forecast.direction.slice(1)}
            </span>
            <span className="text-xs font-mono text-white/50">
              {forecast.pct_change > 0 ? "+" : ""}{forecast.pct_change.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="text-right">
          <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-1">Confidence</p>
          <span className="text-xs font-mono font-bold uppercase" style={{ color: confColor }}>
            {forecast.confidence_level}
          </span>
        </div>
      </div>

      {/* SVG Sparkline */}
      <div className="bg-white/5 rounded-xl border border-white/5 overflow-hidden">
        <svg width={W} height={H} style={{ display: "block" }}>
          {[0.25, 0.5, 0.75].map((v) => (
            <line
              key={v}
              x1={PAD} y1={toY(v)} x2={W - PAD} y2={toY(v)}
              stroke="rgba(255,255,255,0.04)" strokeWidth="1"
            />
          ))}
          <line
            x1={todayX} y1={PAD} x2={todayX} y2={H - PAD}
            stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="3,3"
          />
          <text x={todayX + 3} y={PAD + 7} fill="rgba(255,255,255,0.3)" fontSize="7" fontFamily="monospace">
            today
          </text>
          <path
            d={histPath}
            fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round"
          />
          <path
            d={fcastPath}
            fill="none" stroke={dirColor} strokeWidth="1.5"
            strokeDasharray="4,3" strokeLinecap="round" strokeLinejoin="round"
            opacity="0.85"
          />
          {forecast.predictions.length > 0 && (() => {
            const pts = forecast.predictions.map((s, i) =>
              `${toX(splitIdx + i)},${toY(s)}`
            );
            const areaPath = `M ${lastHistX},${H - PAD} L ${lastHistX},${lastHistY} L ${pts.join(" L ")} L ${toX(total - 1)},${H - PAD} Z`;
            return <path d={areaPath} fill={dirColor} opacity="0.06" />;
          })()}
          {forecast.predictions.length > 0 && (
            <circle
              cx={toX(total - 1)}
              cy={toY(forecast.predictions[forecast.predictions.length - 1])}
              r="3" fill={dirColor} opacity="0.9"
            />
          )}
        </svg>

        <div className="flex justify-between px-2 pb-2 -mt-1">
          <span className="text-[8px] text-white/25 font-mono">
            {forecast.history_dates[0]?.slice(5) ?? ""}
          </span>
          <span className="text-[8px] font-mono" style={{ color: dirColor, opacity: 0.7 }}>
            +7d: {forecast.predictions[6]?.toFixed(2) ?? ""}
          </span>
        </div>
      </div>

      {/* Score Trajectory */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">Score Trajectory</p>
        <div className="flex items-center justify-between">
          <div className="text-center">
            <p className="text-[9px] text-white/35 font-mono">Today</p>
            <p className="text-sm font-mono font-bold text-white">
              {Math.round(forecast.current_score * 100)}
            </p>
          </div>
          <div className="flex-1 mx-3">
            <div className="h-px bg-white/10 relative">
              <div
                className="absolute top-0 left-0 h-px"
                style={{ width: "100%", background: `linear-gradient(to right, rgba(255,255,255,0.3), ${dirColor})` }}
              />
            </div>
          </div>
          <div className="text-center">
            <p className="text-[9px] text-white/35 font-mono">Day 7</p>
            <p className="text-sm font-mono font-bold" style={{ color: dirColor }}>
              {Math.round((forecast.predictions[6] ?? forecast.current_score) * 100)}
            </p>
          </div>
        </div>
      </div>

      {/* Confidence note */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-1">Confidence Note</p>
        <p className="text-xs text-white/65 leading-relaxed">{forecast.confidence_note}</p>
        <p className="text-[9px] text-white/25 font-mono mt-2">
          R² = {forecast.confidence_r2.toFixed(3)} · {forecast.data_points_used} data points
        </p>
      </div>

    </div>
  );
}

// ── Tab: Gemini AI Briefing ────────────────────────────────────────────────

function GeminiBriefingTab({ briefing }: { briefing: BriefingData }) {
  const a = briefing.analysis;
  const riskColor =
    a.risk_level === "high"   ? "#ef4444" :
    a.risk_level === "medium" ? "#f59e0b" : "#22c55e";
  const dirColor = (dir: string) => dir === "LONG" ? "#22c55e" : "#ef4444";

  return (
    <div className="flex flex-col gap-3">

      {/* Risk badge row */}
      <div className="flex items-center justify-between">
        <p className="text-[9px] text-white/30 font-mono">
          {briefing.from_cache ? "⌛ cached" : "✦ fresh"} · {briefing.created_at?.slice(0, 10)}
        </p>
        <RiskBadge level={a.risk_level} />
      </div>

      {/* Geopolitical Summary */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
          🌍 Geopolitical Summary
        </p>
        <p className="text-xs text-white/80 leading-relaxed">{a.geopolitical_summary}</p>
      </div>

      {/* Market Impact */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
          📊 Market Impact
        </p>
        <p className="text-xs text-white/75 leading-relaxed">{a.market_impact}</p>
      </div>

      {/* Affected Assets */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
          🎯 Affected Assets
        </p>
        <div className="flex flex-wrap gap-1.5">
          {a.affected_assets.map((asset, i) => (
            <span
              key={i}
              className="text-[10px] font-mono px-2 py-0.5 rounded"
              style={{
                background: "rgba(255,255,255,0.07)",
                color: "rgba(255,255,255,0.7)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              {asset}
            </span>
          ))}
        </div>
      </div>

      {/* Trade Ideas */}
      {a.trade_ideas.length > 0 && (
        <div className="bg-white/5 rounded-xl p-3 border border-white/5">
          <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
            💡 Trade Ideas
          </p>
          <div className="flex flex-col gap-2.5">
            {a.trade_ideas.map((idea: TradeIdea, i: number) => (
              <div key={i} className="flex items-start gap-2">
                <div className="shrink-0 mt-0.5">
                  <span
                    className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                    style={{
                      color: dirColor(idea.direction),
                      background: idea.direction === "LONG"
                        ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                      border: `1px solid ${idea.direction === "LONG"
                        ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`,
                    }}
                  >
                    {idea.direction === "LONG" ? "↑" : "↓"} {idea.asset}
                  </span>
                </div>
                <p className="text-[10px] text-white/55 leading-relaxed">{idea.reasoning}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analyst note */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-1">Analyst Note</p>
        <p className="text-[10px] text-white/50 leading-relaxed italic">{a.confidence_note}</p>
      </div>

      {/* Footer */}
      <p className="text-[8px] text-white/20 font-mono text-center pb-1">✦ {briefing.model}</p>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────

interface Props {
  event:   GeoEvent;
  onClose: () => void;
}

type TabId = "news" | "signals" | "forecast" | "gemini";

const TABS: { id: TabId; label: string }[] = [
  { id: "news",     label: "📰 News"    },
  { id: "signals",  label: "💹 Signals" },
  { id: "forecast", label: "📈 Forecast"},
  { id: "gemini",   label: "🤖 AI"      },
];

export default function CountryTradingPanel({ event, onClose }: Props) {
  const [tab,             setTab]             = useState<TabId>("news");
  const [trading,         setTrading]         = useState<TradingData | null>(null);
  const [forecast,        setForecast]        = useState<ForecastData | null>(null);
  const [briefing,        setBriefing]        = useState<BriefingData | null>(null);
  const [loadingTrading,  setLoadingTrading]  = useState(true);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [loadingBriefing, setLoadingBriefing] = useState(false);
  const [errorTrading,    setErrorTrading]    = useState(false);
  const [errorForecast,   setErrorForecast]   = useState(false);
  const [errorBriefing,   setErrorBriefing]   = useState(false);

  const tensionColor =
    event.tension_label === "high"   ? "#ef4444" :
    event.tension_label === "medium" ? "#f59e0b" : "#22c55e";

  // Load trading (news + stocks + prediction) on mount / country change
  useEffect(() => {
    setLoadingTrading(true);
    setTrading(null); setForecast(null); setBriefing(null);
    setErrorTrading(false); setErrorForecast(false); setErrorBriefing(false);
    setTab("news");

    fetchTradingSignals(event.iso).then((res) => {
      if (res) setTrading(res);
      else     setErrorTrading(true);
      setLoadingTrading(false);
    });
  }, [event.iso]);

  // Lazy-load forecast when Forecast tab opened
  useEffect(() => {
    if (tab !== "forecast" || forecast || loadingForecast) return;
    setLoadingForecast(true);
    setErrorForecast(false);
    fetchForecast(event.iso).then((res) => {
      if (res) setForecast(res);
      else     setErrorForecast(true);
      setLoadingForecast(false);
    });
  }, [tab, event.iso]);

  // Lazy-load Gemini briefing when AI tab opened
  useEffect(() => {
    if (tab !== "gemini" || briefing || loadingBriefing) return;
    setLoadingBriefing(true);
    setErrorBriefing(false);
    fetchBriefing(event.iso).then((res) => {
      if (res) setBriefing(res);
      else     setErrorBriefing(true);
      setLoadingBriefing(false);
    });
  }, [tab, event.iso]);

  const isLoading =
    (tab === "news" || tab === "signals") ? loadingTrading  :
    tab === "forecast"                    ? loadingForecast :
    loadingBriefing;

  const hasError =
    (tab === "news" || tab === "signals") ? errorTrading  :
    tab === "forecast"                    ? errorForecast :
    errorBriefing;

  // Derive momentum from prediction if available
  const momentum = trading?.prediction?.tension_momentum;

  return (
    <div
      className="fixed right-0 top-0 bottom-0 z-30 flex flex-col"
      style={{
        width:          "340px",
        background:     "rgba(5, 10, 20, 0.92)",
        backdropFilter: "blur(20px)",
        borderLeft:     "1px solid rgba(255,255,255,0.07)",
        animation:      "slideInRight 0.3s ease",
      }}
    >
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>

      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2.5">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: tensionColor, boxShadow: `0 0 8px ${tensionColor}` }}
          />
          <div>
            <p className="font-mono font-bold text-sm text-white leading-none">{event.country}</p>
            <p className="text-[9px] text-white/40 font-mono tracking-widest uppercase mt-0.5">
              {event.iso} · {event.tension_label} tension
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white text-lg leading-none transition-colors p-1 rounded"
        >
          ✕
        </button>
      </div>

      {/* ── Tension bar (full width, below header) ── */}
      <div className="px-4 pt-1.5 pb-2 shrink-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[8px] text-white/25 font-mono">tension</span>
          <span className="text-[8px] font-mono" style={{ color: tensionColor }}>
            {Math.round(event.tension_score * 100)}
          </span>
        </div>
        <TensionBar score={event.tension_score} />
      </div>

      {/* ── Tabs ── */}
      <div
        className="flex shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 py-2.5 text-[9px] font-mono uppercase tracking-wider transition-colors ${
              tab === id
                ? "text-white border-b-2"
                : "text-white/35 hover:text-white/60"
            }`}
            style={tab === id ? { borderColor: tensionColor } : {}}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Body ── */}
      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
        {isLoading && <Spinner color={tensionColor} />}

        {!isLoading && hasError && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-white/30">
            <p className="text-2xl">⚠</p>
            <p className="text-xs font-mono text-center">
              {tab === "gemini"
                ? <>No AI briefing available.<br />Check GEMINI_API_KEY in .env</>
                : tab === "forecast"
                ? <>No forecast data for {event.country}.<br />Need ≥ 3 days of signals.</>
                : <>No data for {event.country}.<br />Start the API to enable this panel.</>
              }
            </p>
          </div>
        )}

        {!isLoading && !hasError && (
          <>
            {tab === "news"     && trading  && <NewsTab  news={trading.recent_news} />}
            {tab === "signals"  && trading  && (
              <SignalsTab
                signals={trading.stock_signals}
                prediction={trading.prediction}
              />
            )}
            {tab === "forecast" && forecast && (
              <ForecastSparkline forecast={forecast} momentum={momentum} />
            )}
            {tab === "gemini"   && briefing && <GeminiBriefingTab briefing={briefing} />}
          </>
        )}
      </div>

      {/* ── Footer ── */}
      {trading && (
        <div
          className="px-4 py-2 shrink-0 flex items-center justify-between"
          style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}
        >
          <p className="text-[9px] text-white/25 font-mono">
            MongoDB · yfinance{briefing ? " · Gemini" : ""}
            {trading.prediction?.model_source === "ml" ? " · ML" : ""}
          </p>
          {trading.tension.sample_url && (
            <a
              href={trading.tension.sample_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[9px] text-white/30 hover:text-white/60 font-mono transition-colors"
            >
              SOURCE →
            </a>
          )}
        </div>
      )}
    </div>
  );
}
