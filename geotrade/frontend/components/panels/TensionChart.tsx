// frontend/components/panels/TensionChart.tsx
// 30-day global tension — SVG area/line chart with gradient fill.

import type { DailySignal } from "@/types";

interface Props {
  signals: DailySignal[];
}

function tensionColor(v: number) {
  if (v >= 0.65) return "#ef4444";
  if (v >= 0.35) return "#f59e0b";
  return "#22c55e";
}

export default function TensionChart({ signals }: Props) {
  if (!signals.length) return null;

  const recent  = signals.slice(-30);
  const W = 188, H = 52, PAD = { t: 4, r: 2, b: 4, l: 2 };
  const vals    = recent.map((s) => s.global_tension);
  const minV    = Math.min(...vals) * 0.85;
  const maxV    = Math.max(...vals, 0.01);
  const range   = maxV - minV || 0.01;
  const latest  = vals[vals.length - 1];
  const prev    = vals[vals.length - 2] ?? latest;
  const trend   = latest - prev;
  const color   = tensionColor(latest);

  const n   = recent.length;
  const toX = (i: number) => PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r);
  const toY = (v: number) => PAD.t + (1 - (v - minV) / range) * (H - PAD.t - PAD.b);

  const pts    = recent.map((s, i) => `${toX(i).toFixed(1)},${toY(s.global_tension).toFixed(1)}`);
  const linePath  = `M ${pts.join(" L ")}`;
  const areaPath  = `M ${toX(0)},${H - PAD.b} L ${pts.join(" L ")} L ${toX(n - 1)},${H - PAD.b} Z`;

  // 7-day simple moving average overlay
  const smaPoints = recent.map((_, i) => {
    if (i < 3) return null;
    const slice = vals.slice(Math.max(0, i - 3), i + 1);
    const avg   = slice.reduce((a, b) => a + b, 0) / slice.length;
    return `${toX(i).toFixed(1)},${toY(avg).toFixed(1)}`;
  }).filter(Boolean);
  const smaPath = smaPoints.length > 1 ? `M ${smaPoints.join(" L ")}` : "";

  const gradId = "tensionGrad";

  return (
    <div className="glass-panel p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono text-geo-text tracking-widest">
          GLOBAL TENSION — 30d
        </span>
        <div className="flex items-center gap-1.5">
          <span
            className="text-[10px] font-mono font-bold"
            style={{ color }}
          >
            {Math.round(latest * 100)}
          </span>
          <span
            className="text-[9px] font-mono"
            style={{ color: trend > 0 ? "#ef4444" : "#22c55e" }}
          >
            {trend > 0 ? "↑" : "↓"}
          </span>
        </div>
      </div>

      {/* SVG area chart */}
      <svg
        width={W} height={H}
        viewBox={`0 0 ${W} ${H}`}
        style={{ display: "block", overflow: "visible" }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Horizontal grid lines */}
        {[0.25, 0.5, 0.75].map((v) => {
          const y = toY(minV + v * range);
          if (y < PAD.t || y > H - PAD.b) return null;
          return (
            <line
              key={v}
              x1={PAD.l} y1={y} x2={W - PAD.r} y2={y}
              stroke="rgba(255,255,255,0.04)" strokeWidth="1"
            />
          );
        })}

        {/* Area fill */}
        <path d={areaPath} fill={`url(#${gradId})`} />

        {/* SMA line — subtle */}
        {smaPath && (
          <path
            d={smaPath}
            fill="none"
            stroke="rgba(255,255,255,0.15)"
            strokeWidth="1"
            strokeDasharray="2,2"
          />
        )}

        {/* Main line */}
        <path
          d={linePath}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.9"
        />

        {/* Latest value dot */}
        <circle
          cx={toX(n - 1)} cy={toY(latest)}
          r="2.5" fill={color} opacity="0.95"
        />
        <circle
          cx={toX(n - 1)} cy={toY(latest)}
          r="5" fill={color} opacity="0.12"
        />
      </svg>

      {/* Date range + mini trend bar */}
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-[8px] font-mono text-geo-text/50">
          {recent[0]?.date?.slice(5) ?? ""}
        </span>
        {/* 7-day mini sparkline pill */}
        <div className="flex items-center gap-0.5 h-2">
          {vals.slice(-7).map((v, i) => (
            <div
              key={i}
              className="w-1 rounded-sm"
              style={{
                height: `${Math.max(20, (v / maxV) * 100)}%`,
                background: tensionColor(v),
                opacity: 0.7,
              }}
            />
          ))}
        </div>
        <span className="text-[8px] font-mono text-geo-text/50">
          {recent[recent.length - 1]?.date?.slice(5) ?? ""}
        </span>
      </div>
    </div>
  );
}
