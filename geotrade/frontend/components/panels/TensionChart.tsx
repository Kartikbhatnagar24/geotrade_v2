// frontend/components/panels/TensionChart.tsx
import type { DailySignal } from "@/types";

interface Props {
  signals: DailySignal[];
}

function barColor(tension: number): string {
  if (tension >= 0.65) return "#ef4444";
  if (tension >= 0.35) return "#f59e0b";
  return "#22c55e";
}

export default function TensionChart({ signals }: Props) {
  if (!signals.length) return null;

  const recent = signals.slice(-30);
  const maxVal = Math.max(...recent.map((s) => s.global_tension), 0.01);

  return (
    <div className="glass-panel p-4">
      <div className="text-[10px] font-mono text-geo-text tracking-widest mb-3">
        GLOBAL TENSION — 30d
      </div>

      {/* Bar chart */}
      <div className="flex items-end gap-[2px] h-12">
        {recent.map((sig, i) => {
          const heightPct = Math.max((sig.global_tension / maxVal) * 100, 4);
          return (
            <div
              key={i}
              className="flex-1 rounded-t transition-all"
              style={{
                height: `${heightPct}%`,
                backgroundColor: barColor(sig.global_tension),
                opacity: 0.85,
              }}
              title={`${sig.date}: ${(sig.global_tension * 100).toFixed(0)}`}
            />
          );
        })}
      </div>

      {/* Date labels */}
      <div className="flex justify-between mt-1">
        <span className="text-[9px] font-mono text-geo-text/50">
          {recent[0]?.date?.slice(5) ?? ""}
        </span>
        <span className="text-[9px] font-mono text-geo-text/50">
          {recent[recent.length - 1]?.date?.slice(5) ?? ""}
        </span>
      </div>

      {/* Current value */}
      {recent.length > 0 && (
        <div className="mt-2 pt-2 border-t border-geo-border flex justify-between">
          <span className="text-[10px] font-mono text-geo-text">Latest</span>
          <span
            className="text-[10px] font-mono font-bold"
            style={{ color: barColor(recent[recent.length - 1].global_tension) }}
          >
            {(recent[recent.length - 1].global_tension * 100).toFixed(0)} / 100
          </span>
        </div>
      )}
    </div>
  );
}
