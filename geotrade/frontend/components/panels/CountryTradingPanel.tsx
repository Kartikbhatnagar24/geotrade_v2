// frontend/components/panels/CountryTradingPanel.tsx
// Full-featured trading analysis drawer that slides in when a country is selected.
// Shows: Tension summary | Recent News | Stock signals | Market prediction

import { useEffect, useState } from "react";
import type { GeoEvent, TradingData, StockSignal, NewsItem } from "@/types";
import { fetchTradingSignals } from "@/lib/api";

// ── Small helpers ─────────────────────────────────────────────

function TensionBar({ score }: { score: number }) {
  const pct   = Math.round(score * 100);
  const color  = score >= 0.65 ? "#ef4444" : score >= 0.35 ? "#f59e0b" : "#22c55e";
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

function RiskBadge({ level }: { level: "HIGH" | "MEDIUM" | "LOW" }) {
  const cfg = {
    HIGH:   "text-red-400 bg-red-500/15 border-red-500/30 animate-pulse",
    MEDIUM: "text-amber-400 bg-amber-500/15 border-amber-500/30",
    LOW:    "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
  }[level];
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded border text-[11px] font-mono font-bold ${cfg}`}>
      ⚠ RISK: {level}
    </span>
  );
}

function ConfidenceRing({ pct }: { pct: number }) {
  const r    = 28;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  const color = pct >= 70 ? "#ef4444" : pct >= 50 ? "#f59e0b" : "#22c55e";
  return (
    <svg width="72" height="72" className="transform -rotate-90">
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="5" />
      <circle
        cx="36" cy="36" r={r}
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeLinecap="round"
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text
        x="36" y="36"
        dominantBaseline="middle"
        textAnchor="middle"
        className="rotate-90"
        transform="rotate(90 36 36)"
        fill="white"
        fontSize="12"
        fontFamily="monospace"
        fontWeight="bold"
      >
        {pct}%
      </text>
    </svg>
  );
}

// ── Tab components ────────────────────────────────────────────

function NewsTab({ news }: { news: NewsItem[] }) {
  if (!news.length) return (
    <p className="text-xs text-white/40 text-center py-6">No recent news found for this country.</p>
  );
  return (
    <div className="flex flex-col gap-2.5">
      {news.map((item, i) => (
        <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <NewsTypePill type={item.news_type} />
            <span className="text-[9px] text-white/35 font-mono shrink-0">
              {item.date ? item.date.slice(0, 10) : "—"}
            </span>
          </div>
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
          {item.source && (
            <p className="text-[9px] text-white/30 mt-1 font-mono">
              {item.source.split(":").pop()}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function StocksTab({ signals }: { signals: StockSignal[] }) {
  if (!signals.length) return (
    <p className="text-xs text-white/40 text-center py-6">No stock data available.</p>
  );
  return (
    <div className="flex flex-col gap-2">
      {signals.map((s, i) => (
        <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-mono font-bold text-sm text-white">{s.ticker}</span>
            <DirectionBadge dir={s.direction} />
          </div>
          <p className="text-[10px] text-white/50 mb-2">{s.name}</p>
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-white/45 leading-relaxed flex-1 pr-2">{s.rationale}</p>
            <div className="text-right shrink-0">
              {s.price != null && (
                <p className="text-xs font-mono text-white/80">${s.price.toFixed(2)}</p>
              )}
              {s.change_5d != null && (
                <p className={`text-[10px] font-mono ${s.change_5d >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {s.change_5d >= 0 ? "+" : ""}{s.change_5d.toFixed(2)}%
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PredictionTab({ data }: { data: TradingData }) {
  const p     = data.prediction;
  const pct   = Math.round(p.confidence * 100);
  const vixUp = p.vix_direction === "increase";
  const vixUncertain = p.vix_direction === "uncertain";

  return (
    <div className="flex flex-col gap-4">
      {/* Confidence ring */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/5 flex items-center gap-4">
        <ConfidenceRing pct={pct} />
        <div className="flex-1">
          <p className="text-[10px] text-white/40 font-mono uppercase tracking-wider mb-1">
            Model Confidence
          </p>
          <p className="font-mono font-bold text-sm text-white mb-2">
            VIX will{" "}
            <span className={vixUp ? "text-red-400" : vixUncertain ? "text-amber-400" : "text-emerald-400"}>
              {vixUp ? "↑ INCREASE" : vixUncertain ? "≈ STAY FLAT" : "↓ DECREASE"}
            </span>
          </p>
          <RiskBadge level={p.risk_level} />
        </div>
      </div>

      {/* News type context */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
          Dominant News Category
        </p>
        <NewsTypePill type={data.dominant_news_type} />
      </div>

      {/* Trade idea */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider mb-2">
          💡 Trade Idea
        </p>
        <p className="text-xs text-white/80 leading-relaxed">{p.trade_idea}</p>
      </div>

      {/* Tension context */}
      <div className="bg-white/5 rounded-xl p-3 border border-white/5">
        <div className="flex justify-between items-center mb-1">
          <p className="text-[9px] text-white/40 font-mono uppercase tracking-wider">Tension Score</p>
          <span className="text-xs font-mono text-white/70">
            {Math.round(data.tension.tension_score * 100)}/100
          </span>
        </div>
        <TensionBar score={data.tension.tension_score} />
        <p className="text-[9px] text-white/30 mt-2">
          {data.tension.event_count} events tracked · {data.tension.date?.slice(0, 10)}
        </p>
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────

interface Props {
  event: GeoEvent;
  onClose: () => void;
}

export default function CountryTradingPanel({ event, onClose }: Props) {
  const [tab,     setTab]     = useState<"news" | "stocks" | "prediction">("news");
  const [data,    setData]    = useState<TradingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);

  useEffect(() => {
    setLoading(true);
    setData(null);
    setError(false);
    setTab("news");

    fetchTradingSignals(event.iso).then((res) => {
      if (res) setData(res);
      else     setError(true);
      setLoading(false);
    });
  }, [event.iso]);

  const tensionColor =
    event.tension_label === "high"   ? "#ef4444" :
    event.tension_label === "medium" ? "#f59e0b" : "#22c55e";

  return (
    <div
      className="fixed right-0 top-0 bottom-0 z-30 flex flex-col"
      style={{
        width: "340px",
        background: "rgba(5, 10, 20, 0.92)",
        backdropFilter: "blur(20px)",
        borderLeft: "1px solid rgba(255,255,255,0.07)",
        animation: "slideInRight 0.3s ease",
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

      {/* ── Tabs ── */}
      <div
        className="flex shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        {(["news", "stocks", "prediction"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2.5 text-[10px] font-mono uppercase tracking-wider transition-colors ${
              tab === t
                ? "text-white border-b-2 border-accent"
                : "text-white/35 hover:text-white/60"
            }`}
            style={tab === t ? { borderColor: tensionColor } : {}}
          >
            {t === "news" ? "📰 News" : t === "stocks" ? "💹 Stocks" : "🔮 Predict"}
          </button>
        ))}
      </div>

      {/* ── Body ── */}
      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-white/30">
            <div
              className="w-8 h-8 rounded-full border-2 border-white/10"
              style={{
                borderTopColor: tensionColor,
                animation: "spin 1s linear infinite",
              }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            <p className="text-[10px] font-mono">Loading {event.iso} data…</p>
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-white/30">
            <p className="text-2xl">⚠</p>
            <p className="text-xs font-mono text-center">
              No trading data for {event.country}.<br />
              Start the API to enable this panel.
            </p>
          </div>
        )}

        {!loading && data && (
          <>
            {tab === "news"       && <NewsTab       news={data.recent_news}    />}
            {tab === "stocks"     && <StocksTab     signals={data.stock_signals} />}
            {tab === "prediction" && <PredictionTab data={data}                />}
          </>
        )}
      </div>

      {/* ── Footer ── */}
      {data && (
        <div
          className="px-4 py-2 shrink-0 flex items-center justify-between"
          style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}
        >
          <p className="text-[9px] text-white/25 font-mono">
            Data: MongoDB · yfinance
          </p>
          {data.tension.sample_url && (
            <a
              href={data.tension.sample_url}
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
