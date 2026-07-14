// frontend/components/panels/CountryTradingPanel.tsx

import { useEffect, useState } from "react";
import type {
  GeoEvent, TradingData, StockSignal, NewsItem,
  ForecastData, BriefingData, TradeIdea,
  TensionMomentum, MarketSignal, TradingPrediction,
} from "@/types";
import { fetchTradingSignals, fetchForecast, fetchBriefing } from "@/lib/api";

// ── Color helpers ───────────────────────────────────────────────────────────

const T_COLOR = (label: string) =>
  label === "high" ? "var(--signal-high)" :
  label === "medium" ? "var(--signal-mid)" : "var(--signal-low)";

const DIR_CFG = {
  increase: {
    color: "var(--signal-low)",
    bg: "rgba(0,200,74,0.07)",
    border: "rgba(0,200,74,0.2)",
    arrow: "↑",
    label: "PRICE UP",
    sublabel: "likely higher in 3 days",
  },
  decrease: {
    color: "var(--signal-high)",
    bg: "rgba(240,40,40,0.07)",
    border: "rgba(240,40,40,0.2)",
    arrow: "↓",
    label: "PRICE DOWN",
    sublabel: "likely lower in 3 days",
  },
  uncertain: {
    color: "var(--signal-mid)",
    bg: "rgba(232,144,32,0.07)",
    border: "rgba(232,144,32,0.2)",
    arrow: "→",
    label: "UNCLEAR",
    sublabel: "mixed directional signal",
  },
};

const VOL_CFG = {
  high: {
    color: "var(--signal-high)",
    bg: "rgba(240,40,40,0.07)",
    border: "rgba(240,40,40,0.2)",
    icon: "▲▲",
    label: "HIGH VOL",
    sublabel: "large swings expected 5d",
  },
  low: {
    color: "var(--signal-low)",
    bg: "rgba(0,200,74,0.07)",
    border: "rgba(0,200,74,0.2)",
    icon: "▼▼",
    label: "LOW VOL",
    sublabel: "calm market expected 5d",
  },
  neutral: {
    color: "var(--signal-mid)",
    bg: "rgba(232,144,32,0.07)",
    border: "rgba(232,144,32,0.2)",
    icon: "▬▬",
    label: "MIXED",
    sublabel: "vol regime unclear 5d",
  },
};

// ── Spinner ─────────────────────────────────────────────────────────────────

function Spinner({ color }: { color: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3" style={{ color: "rgba(255,255,255,0.2)" }}>
      <div
        className="w-7 h-7 rounded-full border-2"
        style={{
          borderColor: "rgba(255,255,255,0.08)",
          borderTopColor: color,
          animation: "spin 0.9s linear infinite",
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <p className="font-mono text-[10px] tracking-widest">LOADING</p>
    </div>
  );
}

// ── Dual ML Prediction card ─────────────────────────────────────────────────

function DualMLCard({ prediction }: { prediction: TradingPrediction }) {
  const isRuleBased = prediction.model_source === "rule-based";

  const dir   = prediction.direction ?? prediction.vix_direction ?? "uncertain";
  const dirP  = prediction.direction_prob ?? prediction.confidence ?? 0;
  const dirPct= prediction.direction_pct ?? prediction.confidence_pct ?? `${Math.round(dirP * 100)}%`;
  const dirAuc= prediction.direction_auc;

  const vol   = prediction.vol_level;
  const volP  = prediction.vol_prob ?? 0;
  const volPct= prediction.vol_pct ?? `${Math.round(volP * 100)}%`;
  const volAuc= prediction.vol_auc;

  const dCfg  = DIR_CFG[dir as keyof typeof DIR_CFG] ?? DIR_CFG.uncertain;
  const vCfg  = vol ? (VOL_CFG[vol as keyof typeof VOL_CFG] ?? VOL_CFG.neutral) : null;

  return (
    <div className="flex flex-col gap-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] tracking-[0.2em]" style={{ color: "var(--geo-text-2)" }}>
          MODEL PREDICTIONS
        </span>
        <span
          className="font-mono text-[8px] px-1.5 py-0.5 rounded tracking-wider"
          style={{
            color: isRuleBased ? "var(--signal-mid)" : "var(--accent)",
            background: isRuleBased ? "rgba(232,144,32,0.1)" : "var(--accent-dim)",
            border: `1px solid ${isRuleBased ? "rgba(232,144,32,0.25)" : "var(--accent-glow)"}`,
          }}
        >
          {isRuleBased ? "RULE-BASED" : "ML ENSEMBLE"}
        </span>
      </div>

      {/* Cards row */}
      <div className="grid grid-cols-2 gap-2">
        {/* Direction card */}
        <div
          className="rounded-xl p-3 relative scanline-overlay"
          style={{ background: dCfg.bg, border: `1px solid ${dCfg.border}` }}
        >
          <p className="font-mono text-[8px] tracking-[0.18em] mb-2" style={{ color: `${dCfg.color}99` }}>
            3D DIRECTION
          </p>
          <div className="flex items-baseline gap-1.5 mb-1">
            <span
              className="font-mono text-2xl font-bold leading-none"
              style={{ color: dCfg.color }}
            >
              {dCfg.arrow}
            </span>
            <span
              className="font-mono text-[11px] font-bold leading-none"
              style={{ color: dCfg.color }}
            >
              {dCfg.label}
            </span>
          </div>
          <p className="font-mono text-[9px] mb-2.5" style={{ color: "rgba(255,255,255,0.35)" }}>
            {dCfg.sublabel}
          </p>
          {/* Confidence bar */}
          <div>
            <div className="flex justify-between mb-1">
              <span className="font-mono text-[8px]" style={{ color: "rgba(255,255,255,0.3)" }}>CONF</span>
              <span className="font-mono text-[8px] font-bold" style={{ color: dCfg.color }}>{dirPct}</span>
            </div>
            <div className="h-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div
                className="h-full rounded-full"
                style={{
                  width: dirPct,
                  background: dCfg.color,
                  opacity: 0.8,
                  transition: "width 0.7s ease",
                }}
              />
            </div>
            {dirAuc && (
              <p className="font-mono text-[7px] mt-1" style={{ color: "rgba(255,255,255,0.2)" }}>
                AUC {dirAuc.toFixed(3)}
              </p>
            )}
          </div>
        </div>

        {/* Volatility card */}
        {vCfg ? (
          <div
            className="rounded-xl p-3 relative scanline-overlay"
            style={{ background: vCfg.bg, border: `1px solid ${vCfg.border}` }}
          >
            <p className="font-mono text-[8px] tracking-[0.18em] mb-2" style={{ color: `${vCfg.color}99` }}>
              5D VOLATILITY
            </p>
            <div className="flex items-baseline gap-1.5 mb-1">
              <span
                className="font-mono text-[18px] font-bold leading-none"
                style={{ color: vCfg.color }}
              >
                {vCfg.icon}
              </span>
            </div>
            <p
              className="font-mono text-[11px] font-bold mb-1"
              style={{ color: vCfg.color }}
            >
              {vCfg.label}
            </p>
            <p className="font-mono text-[9px] mb-2.5" style={{ color: "rgba(255,255,255,0.35)" }}>
              {vCfg.sublabel}
            </p>
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-mono text-[8px]" style={{ color: "rgba(255,255,255,0.3)" }}>CONF</span>
                <span className="font-mono text-[8px] font-bold" style={{ color: vCfg.color }}>{volPct}</span>
              </div>
              <div className="h-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
                <div
                  className="h-full rounded-full"
                  style={{
                    width: volPct,
                    background: vCfg.color,
                    opacity: 0.8,
                    transition: "width 0.7s ease",
                  }}
                />
              </div>
              {volAuc && (
                <p className="font-mono text-[7px] mt-1" style={{ color: "rgba(255,255,255,0.2)" }}>
                  AUC {volAuc.toFixed(3)}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div
            className="rounded-xl p-3 flex flex-col items-center justify-center"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <p className="font-mono text-[8px] tracking-[0.18em] mb-2" style={{ color: "var(--geo-text)" }}>
              5D VOLATILITY
            </p>
            <p className="font-mono text-[9px] text-center leading-relaxed" style={{ color: "rgba(255,255,255,0.2)" }}>
              Train volatility model to unlock
            </p>
          </div>
        )}
      </div>

      {/* Rule-based note */}
      {isRuleBased && prediction.no_data_reason && (
        <p className="font-mono text-[9px] leading-relaxed" style={{ color: "rgba(255,255,255,0.3)" }}>
          {prediction.no_data_reason}
        </p>
      )}
    </div>
  );
}

// ── Stance card ─────────────────────────────────────────────────────────────

function StanceCard({ summary }: { summary: string }) {
  const u = summary.toUpperCase();
  const [color, bg] =
    u.startsWith("DEFENSIVE")    ? ["var(--signal-high)", "rgba(240,40,40,0.06)"] :
    u.startsWith("CAUTIOUS")     ? ["var(--signal-mid)",  "rgba(232,144,32,0.06)"] :
    u.startsWith("CONSTRUCTIVE") ? ["var(--signal-low)",  "rgba(0,200,74,0.06)"] :
                                   ["var(--geo-text-2)",  "rgba(255,255,255,0.03)"];
  const [stance, ...rest] = summary.split(" — ");
  return (
    <div
      className="rounded-xl px-3.5 py-3"
      style={{ background: bg, border: `1px solid ${color}18` }}
    >
      <p className="font-mono text-[8px] tracking-[0.2em] mb-1.5" style={{ color: "var(--geo-text)" }}>
        STANCE
      </p>
      <p className="font-mono text-xs leading-snug" style={{ color }}>
        <span className="font-bold">{stance}</span>
        {rest.length > 0 && (
          <span style={{ color: "rgba(255,255,255,0.5)" }}> — {rest.join(" — ")}</span>
        )}
      </p>
    </div>
  );
}

// ── Market signal card ───────────────────────────────────────────────────────

function MarketSignalCard({ signal }: { signal: MarketSignal }) {
  const [color, bg, border] =
    signal.direction === "LONG"  ? ["var(--signal-low)",  "rgba(0,200,74,0.06)",   "rgba(0,200,74,0.18)"] :
    signal.direction === "SHORT" ? ["var(--signal-high)", "rgba(240,40,40,0.06)",  "rgba(240,40,40,0.18)"] :
                                   ["var(--signal-mid)",  "rgba(232,144,32,0.06)", "rgba(232,144,32,0.18)"];

  const ICONS: Record<string, string> = {
    "Safe Havens":          "◈",
    "Energy / Oil":         "⬡",
    "Defense & Aerospace":  "◉",
    "Semiconductors / Tech":"⬡",
    "Agriculture":          "◈",
    "Local Equity":         "◎",
    "FX / Currencies":      "◈",
  };

  const arrow = signal.direction === "LONG" ? "↑ BUY" : signal.direction === "SHORT" ? "↓ SELL" : "◎ WATCH";

  return (
    <div
      className="rounded-xl px-3.5 py-3"
      style={{ background: bg, border: `1px solid ${border}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm" style={{ color: `${color}99` }}>
            {ICONS[signal.asset_class] ?? "◈"}
          </span>
          <span className="font-mono text-[11px] font-semibold" style={{ color: "rgba(255,255,255,0.80)" }}>
            {signal.asset_class}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Conviction dots */}
          <span className="flex gap-0.5">
            {Array.from({ length: 5 }, (_, i) => (
              <span
                key={i}
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: i < signal.conviction ? color : "rgba(255,255,255,0.1)" }}
              />
            ))}
          </span>
          <span
            className="font-mono text-[9px] font-bold px-1.5 py-0.5 rounded"
            style={{ color, background: `${color}15`, border: `1px solid ${color}30` }}
          >
            {arrow}
          </span>
        </div>
      </div>
      {/* Tickers */}
      <div className="flex flex-wrap gap-1 mb-2">
        {signal.tickers.map((t) => (
          <span
            key={t}
            className="font-mono text-[9px] px-1.5 py-0.5 rounded"
            style={{ color, background: `${color}10`, border: `1px solid ${color}25` }}
          >
            {t}
          </span>
        ))}
      </div>
      <p className="font-mono text-[9px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
        {signal.rationale}
      </p>
    </div>
  );
}

// ── Key risks ────────────────────────────────────────────────────────────────

function KeyRisks({ risks }: { risks: string[] }) {
  if (!risks.length) return null;
  return (
    <div
      className="rounded-xl px-3.5 py-3"
      style={{ background: "rgba(240,40,40,0.04)", border: "1px solid rgba(240,40,40,0.14)" }}
    >
      <p className="font-mono text-[8px] tracking-[0.2em] mb-2.5" style={{ color: "rgba(240,40,40,0.6)" }}>
        KEY RISKS
      </p>
      <div className="flex flex-col gap-1.5">
        {risks.map((r, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="font-mono text-[9px] mt-0.5 shrink-0" style={{ color: "rgba(240,40,40,0.45)" }}>
              ▸
            </span>
            <p className="font-mono text-[9px] leading-relaxed" style={{ color: "rgba(255,255,255,0.5)" }}>
              {r}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── News tab ─────────────────────────────────────────────────────────────────

const NEWS_TYPE_COLOR: Record<string, string> = {
  conflict:     "rgba(240,40,40,0.7)",
  military:     "rgba(220,100,30,0.7)",
  sanctions:    "rgba(160,80,220,0.7)",
  economic:     "rgba(40,140,240,0.7)",
  diplomatic:   "rgba(0,180,200,0.7)",
  humanitarian: "rgba(220,80,140,0.7)",
  elections:    "rgba(80,200,120,0.7)",
  other:        "rgba(100,120,150,0.7)",
};

function NewsTab({ news }: { news: NewsItem[] }) {
  if (!news.length)
    return (
      <div className="flex items-center justify-center h-full">
        <p className="font-mono text-[10px]" style={{ color: "var(--geo-text)" }}>
          No recent articles found.
        </p>
      </div>
    );

  return (
    <div className="flex flex-col gap-2">
      {news.map((item, i) => {
        const typeColor = NEWS_TYPE_COLOR[item.news_type] ?? NEWS_TYPE_COLOR.other;
        const sentIcon =
          item.sentiment_label?.toLowerCase() === "negative" ? "▼" :
          item.sentiment_label?.toLowerCase() === "positive" ? "▲" : null;

        return (
          <div
            key={i}
            className="rounded-xl px-3.5 py-3"
            style={{
              background: "rgba(255,255,255,0.025)",
              border: "1px solid rgba(255,255,255,0.05)",
            }}
          >
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span
                className="font-mono text-[8px] px-1.5 py-0.5 rounded uppercase tracking-wider"
                style={{ color: typeColor, background: `${typeColor}15`, border: `1px solid ${typeColor}30` }}
              >
                {item.news_type}
              </span>
              <div className="flex items-center gap-1.5">
                {sentIcon && (
                  <span
                    className="font-mono text-[8px]"
                    style={{ color: sentIcon === "▼" ? "var(--signal-high)" : "var(--signal-low)" }}
                  >
                    {sentIcon}
                  </span>
                )}
                <span className="font-mono text-[9px]" style={{ color: "var(--geo-text)" }}>
                  {item.date ? item.date.slice(5) : "—"}
                </span>
              </div>
            </div>

            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block font-mono text-[10px] leading-relaxed line-clamp-2 transition-colors"
                style={{ color: "rgba(255,255,255,0.72)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.95)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.72)")}
              >
                {item.title}
              </a>
            ) : (
              <p
                className="font-mono text-[10px] leading-relaxed line-clamp-2"
                style={{ color: "rgba(255,255,255,0.72)" }}
              >
                {item.title}
              </p>
            )}

            {item.source && (
              <p className="font-mono text-[8px] mt-1.5" style={{ color: "var(--geo-text)" }}>
                {item.source.split(":").pop()?.trim()}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Market / Signals tab ─────────────────────────────────────────────────────

function MarketTab({
  prediction,
}: {
  prediction: TradingPrediction | null;
}) {
  if (!prediction) return null;
  const marketSignals = prediction.market_signals ?? [];
  const keyRisks      = prediction.key_risks ?? [];
  const positioning   = prediction.positioning_summary ?? "";

  return (
    <div className="flex flex-col gap-3">
      <DualMLCard prediction={prediction} />
      {positioning && <StanceCard summary={positioning} />}

      {marketSignals.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="font-mono text-[8px] tracking-[0.2em] px-0.5" style={{ color: "var(--geo-text)" }}>
            ASSET CLASS SIGNALS — {marketSignals.length} CATEGORIES
          </p>
          {marketSignals.map((sig, i) => (
            <MarketSignalCard key={i} signal={sig} />
          ))}
        </div>
      )}

      <KeyRisks risks={keyRisks} />

      {marketSignals.length === 0 && (
        <p className="font-mono text-[10px] text-center py-6" style={{ color: "var(--geo-text)" }}>
          No market signals available.
        </p>
      )}
    </div>
  );
}

// ── Forecast tab ─────────────────────────────────────────────────────────────

function MomentumStrip({ momentum }: { momentum: TensionMomentum }) {
  const accelColor =
    momentum.acceleration === "rising"  ? "var(--signal-high)" :
    momentum.acceleration === "falling" ? "var(--signal-low)" : "var(--signal-mid)";
  const accelArrow =
    momentum.acceleration === "rising"  ? "↑" :
    momentum.acceleration === "falling" ? "↓" : "→";

  const fmt = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}`;
  const c3 = momentum.change_3d > 0 ? "var(--signal-high)" : momentum.change_3d < 0 ? "var(--signal-low)" : "var(--geo-text-2)";
  const c7 = momentum.change_7d > 0 ? "var(--signal-high)" : momentum.change_7d < 0 ? "var(--signal-low)" : "var(--geo-text-2)";

  return (
    <div
      className="rounded-xl px-3.5 py-3"
      style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <p className="font-mono text-[8px] tracking-[0.2em] mb-3" style={{ color: "var(--geo-text)" }}>
        TENSION MOMENTUM
      </p>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="font-mono text-[8px] mb-1" style={{ color: "var(--geo-text)" }}>3D Δ</p>
          <p className="font-mono text-sm font-bold" style={{ color: c3 }}>{fmt(momentum.change_3d)}</p>
        </div>
        <div>
          <p className="font-mono text-[8px] mb-1" style={{ color: "var(--geo-text)" }}>7D Δ</p>
          <p className="font-mono text-sm font-bold" style={{ color: c7 }}>{fmt(momentum.change_7d)}</p>
        </div>
        <div>
          <p className="font-mono text-[8px] mb-1" style={{ color: "var(--geo-text)" }}>TREND</p>
          <p className="font-mono text-sm font-bold" style={{ color: accelColor }}>
            {accelArrow} {momentum.acceleration.toUpperCase()}
          </p>
        </div>
      </div>
    </div>
  );
}

function ForecastSparkline({ forecast, momentum }: { forecast: ForecastData; momentum?: TensionMomentum }) {
  const W = 310, H = 76, PAD = 10;

  const allScores = [...forecast.history_scores, ...forecast.predictions];
  const allDates  = [...forecast.history_dates,  ...forecast.forecast_dates];
  const splitIdx  = forecast.history_scores.length;
  const total     = allScores.length;

  const minV = Math.min(...allScores, 0);
  const maxV = Math.max(...allScores, 1);
  const rng  = maxV - minV || 1;

  const toX = (i: number) => PAD + (i / (total - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minV) / rng) * (H - PAD * 2);

  const histPts  = forecast.history_scores.map((s, i) => `${toX(i)},${toY(s)}`);
  const fcastPts = forecast.predictions.map((s, i) => `${toX(splitIdx + i)},${toY(s)}`);

  const histPath  = `M ${histPts.join(" L ")}`;
  const lastHX    = toX(splitIdx - 1);
  const lastHY    = toY(forecast.history_scores[forecast.history_scores.length - 1]);
  const fcastPath = `M ${lastHX},${lastHY} L ${fcastPts.join(" L ")}`;

  const dirColor =
    forecast.direction === "escalating"    ? "var(--signal-high)" :
    forecast.direction === "de-escalating" ? "var(--signal-low)"  : "var(--signal-mid)";
  const dirArrow =
    forecast.direction === "escalating"    ? "↑" :
    forecast.direction === "de-escalating" ? "↓" : "→";
  const confColor =
    forecast.confidence_level === "high"   ? "var(--signal-low)" :
    forecast.confidence_level === "medium" ? "var(--signal-mid)" : "var(--signal-high)";

  return (
    <div className="flex flex-col gap-3">
      {momentum && <MomentumStrip momentum={momentum} />}

      {/* Direction header */}
      <div
        className="rounded-xl px-3.5 py-3 flex items-center justify-between"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div>
          <p className="font-mono text-[8px] tracking-[0.2em] mb-1" style={{ color: "var(--geo-text)" }}>
            7-DAY TENSION FORECAST
          </p>
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold" style={{ color: dirColor }}>{dirArrow}</span>
            <span className="font-mono text-sm font-bold capitalize" style={{ color: dirColor }}>
              {forecast.direction}
            </span>
            <span className="font-mono text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
              {forecast.pct_change > 0 ? "+" : ""}{forecast.pct_change.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-[8px] tracking-[0.2em] mb-1" style={{ color: "var(--geo-text)" }}>
            CONFIDENCE
          </p>
          <span className="font-mono text-xs font-bold uppercase" style={{ color: confColor }}>
            {forecast.confidence_level}
          </span>
        </div>
      </div>

      {/* Sparkline */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <svg width={W} height={H} style={{ display: "block" }}>
          {[0.25, 0.5, 0.75].map((v) => (
            <line
              key={v}
              x1={PAD} y1={toY(v)} x2={W - PAD} y2={toY(v)}
              stroke="rgba(255,255,255,0.035)" strokeWidth="1"
            />
          ))}
          {/* Today divider */}
          <line
            x1={lastHX} y1={PAD} x2={lastHX} y2={H - PAD}
            stroke="rgba(255,255,255,0.12)" strokeWidth="1" strokeDasharray="3,3"
          />
          <text x={lastHX + 4} y={PAD + 7} fill="rgba(255,255,255,0.25)" fontSize="7" fontFamily="Share Tech Mono, monospace">
            NOW
          </text>
          {/* History line */}
          <path d={histPath} fill="none" stroke="rgba(255,255,255,0.38)" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" />
          {/* Forecast area fill */}
          {forecast.predictions.length > 0 && (() => {
            const areaPath = `M ${lastHX},${H - PAD} L ${lastHX},${lastHY} L ${fcastPts.join(" L ")} L ${toX(total - 1)},${H - PAD} Z`;
            return <path d={areaPath} fill={dirColor} opacity="0.07" />;
          })()}
          {/* Forecast dashed line */}
          <path d={fcastPath} fill="none" stroke={dirColor} strokeWidth="1.5"
            strokeDasharray="4,3" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
          {/* End dot */}
          {forecast.predictions.length > 0 && (
            <circle
              cx={toX(total - 1)}
              cy={toY(forecast.predictions[forecast.predictions.length - 1])}
              r="3" fill={dirColor} opacity="0.9"
            />
          )}
        </svg>
        <div className="flex justify-between px-3 pb-2 -mt-1">
          <span className="font-mono text-[8px]" style={{ color: "var(--geo-text)" }}>
            {forecast.history_dates[0]?.slice(5) ?? ""}
          </span>
          <span className="font-mono text-[8px]" style={{ color: dirColor, opacity: 0.7 }}>
            +7d: {forecast.predictions[6]?.toFixed(2) ?? ""}
          </span>
        </div>
      </div>

      {/* Score trajectory */}
      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <p className="font-mono text-[8px] tracking-[0.2em] mb-2.5" style={{ color: "var(--geo-text)" }}>
          SCORE TRAJECTORY
        </p>
        <div className="flex items-center justify-between">
          <div className="text-center">
            <p className="font-mono text-[8px] mb-1" style={{ color: "var(--geo-text)" }}>NOW</p>
            <p className="font-mono text-base font-bold" style={{ color: "rgba(255,255,255,0.75)" }}>
              {Math.round(forecast.current_score * 100)}
            </p>
          </div>
          <div className="flex-1 mx-4">
            <div className="h-px relative" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div
                className="absolute inset-0"
                style={{ background: `linear-gradient(to right, rgba(255,255,255,0.2), ${dirColor})` }}
              />
            </div>
          </div>
          <div className="text-center">
            <p className="font-mono text-[8px] mb-1" style={{ color: "var(--geo-text)" }}>DAY 7</p>
            <p className="font-mono text-base font-bold" style={{ color: dirColor }}>
              {Math.round((forecast.predictions[6] ?? forecast.current_score) * 100)}
            </p>
          </div>
        </div>
      </div>

      {/* Confidence note */}
      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <p className="font-mono text-[8px] tracking-[0.2em] mb-1.5" style={{ color: "var(--geo-text)" }}>
          HOW RELIABLE IS THIS?
        </p>
        <p className="font-mono text-[10px] leading-relaxed" style={{ color: "rgba(255,255,255,0.58)" }}>
          {forecast.confidence_note}
        </p>
      </div>
    </div>
  );
}

// ── AI Brief tab ─────────────────────────────────────────────────────────────

function BriefingTab({ briefing }: { briefing: BriefingData }) {
  const a = briefing.analysis;
  const riskColor =
    a.risk_level === "high"   ? "var(--signal-high)" :
    a.risk_level === "medium" ? "var(--signal-mid)"  : "var(--signal-low)";

  return (
    <div className="flex flex-col gap-3">
      {/* Risk + freshness row */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px]" style={{ color: "var(--geo-text)" }}>
          {briefing.from_cache ? "cached" : "fresh"} · {briefing.created_at?.slice(0, 10)}
        </span>
        <span
          className="font-mono text-[10px] font-bold px-2.5 py-1 rounded"
          style={{
            color: riskColor,
            background: `${riskColor}12`,
            border: `1px solid ${riskColor}30`,
          }}
        >
          {a.risk_level.toUpperCase()} RISK
        </span>
      </div>

      {/* Geopolitical summary */}
      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <p className="font-mono text-[8px] tracking-[0.2em] mb-2" style={{ color: "var(--geo-text)" }}>
          GEOPOLITICAL SITUATION
        </p>
        <p className="font-mono text-[10px] leading-relaxed" style={{ color: "rgba(255,255,255,0.75)" }}>
          {a.geopolitical_summary}
        </p>
      </div>

      {/* Market impact */}
      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
      >
        <p className="font-mono text-[8px] tracking-[0.2em] mb-2" style={{ color: "var(--geo-text)" }}>
          MARKET IMPACT
        </p>
        <p className="font-mono text-[10px] leading-relaxed" style={{ color: "rgba(255,255,255,0.65)" }}>
          {a.market_impact}
        </p>
      </div>

      {/* Affected assets */}
      {a.affected_assets.length > 0 && (
        <div
          className="rounded-xl px-3.5 py-3"
          style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          <p className="font-mono text-[8px] tracking-[0.2em] mb-2" style={{ color: "var(--geo-text)" }}>
            AFFECTED ASSETS
          </p>
          <div className="flex flex-wrap gap-1.5">
            {a.affected_assets.map((asset, i) => (
              <span
                key={i}
                className="font-mono text-[9px] px-2 py-0.5 rounded"
                style={{
                  color: "rgba(255,255,255,0.65)",
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.1)",
                }}
              >
                {asset}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Trade ideas */}
      {a.trade_ideas.length > 0 && (
        <div
          className="rounded-xl px-3.5 py-3"
          style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          <p className="font-mono text-[8px] tracking-[0.2em] mb-2.5" style={{ color: "var(--geo-text)" }}>
            TRADE IDEAS
          </p>
          <div className="flex flex-col gap-2.5">
            {a.trade_ideas.map((idea: TradeIdea, i: number) => {
              const c = idea.direction === "LONG" ? "var(--signal-low)" : "var(--signal-high)";
              return (
                <div key={i} className="flex items-start gap-2.5">
                  <span
                    className="font-mono text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5"
                    style={{
                      color: c,
                      background: `${c}12`,
                      border: `1px solid ${c}28`,
                    }}
                  >
                    {idea.direction === "LONG" ? "↑" : "↓"} {idea.asset}
                  </span>
                  <p className="font-mono text-[9px] leading-relaxed" style={{ color: "rgba(255,255,255,0.5)" }}>
                    {idea.reasoning}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Analyst note */}
      <div
        className="rounded-xl px-3.5 py-3"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        <p className="font-mono text-[8px] tracking-[0.2em] mb-1" style={{ color: "var(--geo-text)" }}>
          ANALYST NOTE
        </p>
        <p className="font-mono text-[9px] italic leading-relaxed" style={{ color: "rgba(255,255,255,0.4)" }}>
          {a.confidence_note}
        </p>
      </div>
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

interface Props {
  event:   GeoEvent;
  onClose: () => void;
}

type TabId = "news" | "market" | "forecast" | "brief";

const TABS: { id: TabId; label: string }[] = [
  { id: "news",     label: "NEWS"    },
  { id: "market",   label: "MARKET"  },
  { id: "forecast", label: "OUTLOOK" },
  { id: "brief",    label: "BRIEF"   },
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

  const tensionColor = T_COLOR(event.tension_label);
  const tensionPct   = Math.round(event.tension_score * 100);

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

  useEffect(() => {
    if (tab !== "brief" || briefing || loadingBriefing) return;
    setLoadingBriefing(true);
    setErrorBriefing(false);
    fetchBriefing(event.iso).then((res) => {
      if (res) setBriefing(res);
      else     setErrorBriefing(true);
      setLoadingBriefing(false);
    });
  }, [tab, event.iso]);

  const isLoading =
    tab === "news" || tab === "market" ? loadingTrading  :
    tab === "forecast"                 ? loadingForecast :
    loadingBriefing;

  const hasError =
    tab === "news" || tab === "market" ? errorTrading  :
    tab === "forecast"                 ? errorForecast :
    errorBriefing;

  const momentum = trading?.prediction?.tension_momentum;

  const eventDesc: Record<string, string> = {
    conflict:     "armed conflict",
    military:     "military activity",
    sanctions:    "economic sanctions",
    diplomatic:   "diplomatic activity",
    elections:    "political elections",
    humanitarian: "humanitarian crisis",
    trade:        "trade disputes",
  };

  return (
    <div
      className="fixed right-0 top-0 bottom-0 z-30 flex flex-col panel-slide-in"
      style={{
        width:          "360px",
        background:     "rgba(4, 9, 20, 0.95)",
        backdropFilter: "blur(24px)",
        borderLeft:     "1px solid rgba(15, 32, 64, 0.9)",
      }}
    >
      {/* ── Header ───────────────────────────────────────────── */}
      <div
        className="px-5 pt-4 pb-3 shrink-0"
        style={{ borderBottom: "1px solid rgba(15, 32, 64, 0.8)" }}
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3 min-w-0">
            {/* Tension indicator dot */}
            <div className="shrink-0 relative">
              <div
                className="w-3 h-3 rounded-full"
                style={{
                  background: tensionColor,
                  boxShadow: `0 0 0 3px ${tensionColor}20, 0 0 10px ${tensionColor}40`,
                }}
              />
            </div>
            <div className="min-w-0">
              <h2
                className="font-bold text-base leading-none truncate"
                style={{ color: "rgba(255,255,255,0.95)", letterSpacing: "0.04em" }}
              >
                {event.country.toUpperCase()}
              </h2>
              <p className="font-mono text-[9px] mt-1 tracking-[0.2em]" style={{ color: "var(--geo-text-2)" }}>
                {event.iso} · {event.tension_label.toUpperCase()} TENSION
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2 shrink-0">
            {/* Tension score badge */}
            <div
              className="font-mono text-[11px] font-bold px-2 py-1 rounded"
              style={{
                color: tensionColor,
                background: `${tensionColor}12`,
                border: `1px solid ${tensionColor}28`,
              }}
            >
              {tensionPct}
            </div>
            <button
              onClick={onClose}
              className="font-mono text-[16px] leading-none p-1 rounded transition-colors"
              style={{ color: "var(--geo-text)", lineHeight: "1" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.8)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--geo-text)")}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tension fill bar */}
        <div className="h-px w-full rounded-full mb-3" style={{ background: "rgba(255,255,255,0.05)" }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${tensionPct}%`, background: tensionColor, opacity: 0.7 }}
          />
        </div>

        {/* Situation context sentence */}
        <p className="font-mono text-[10px] leading-relaxed" style={{ color: "rgba(255,255,255,0.5)" }}>
          {event.country} is a{" "}
          <span style={{ color: tensionColor, fontWeight: 600 }}>
            {event.tension_label}-risk
          </span>{" "}
          situation, mainly driven by{" "}
          <span style={{ color: "rgba(255,255,255,0.75)" }}>
            {eventDesc[event.event_label ?? ""] ?? "geopolitical events"}
          </span>.
          {trading?.prediction?.direction && trading.prediction.model_source !== "rule-based" && (
            <>
              {" "}ML signals{" "}
              <span style={{ color: trading.prediction.direction === "increase" ? "var(--signal-low)" : trading.prediction.direction === "decrease" ? "var(--signal-high)" : "var(--signal-mid)" }}>
                {trading.prediction.direction === "increase" ? "price up" : trading.prediction.direction === "decrease" ? "price down" : "uncertain direction"}
              </span>{" "}
              over 3 days.
            </>
          )}
        </p>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────── */}
      <div
        className="flex shrink-0"
        style={{ borderBottom: "1px solid rgba(15, 32, 64, 0.8)" }}
      >
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex-1 py-3 font-mono text-[9px] tracking-[0.22em] transition-all"
            style={{
              color: tab === id ? "rgba(255,255,255,0.9)" : "var(--geo-text)",
              borderBottom: tab === id ? `2px solid ${tensionColor}` : "2px solid transparent",
              background: tab === id ? `${tensionColor}06` : "transparent",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Body ─────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-3.5 scrollbar-thin">
        {isLoading && <Spinner color={tensionColor} />}

        {!isLoading && hasError && (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <p className="font-mono text-2xl" style={{ color: "var(--geo-text)" }}>⚠</p>
            <p className="font-mono text-[10px] text-center leading-relaxed" style={{ color: "var(--geo-text)" }}>
              {tab === "brief"
                ? "No AI briefing available.\nCheck GEMINI_API_KEY in .env"
                : tab === "forecast"
                ? `No forecast data for ${event.country}.\nNeed ≥ 3 days of signals.`
                : `No data for ${event.country}.\nStart the API to enable this panel.`}
            </p>
          </div>
        )}

        {!isLoading && !hasError && (
          <>
            {tab === "news"     && trading  && <NewsTab news={trading.recent_news} />}
            {tab === "market"   && trading  && <MarketTab prediction={trading.prediction} />}
            {tab === "forecast" && forecast && (
              <ForecastSparkline forecast={forecast} momentum={momentum} />
            )}
            {tab === "brief"    && briefing && <BriefingTab briefing={briefing} />}
          </>
        )}
      </div>

      {/* ── Footer (source only, no dev info) ────────────────── */}
      {trading?.tension?.sample_url && (
        <div
          className="px-5 py-2 shrink-0 flex justify-end"
          style={{ borderTop: "1px solid rgba(15, 32, 64, 0.6)" }}
        >
          <a
            href={trading.tension.sample_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[8px] tracking-[0.15em] transition-colors"
            style={{ color: "var(--geo-text)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--geo-text)")}
          >
            SOURCE →
          </a>
        </div>
      )}
    </div>
  );
}
