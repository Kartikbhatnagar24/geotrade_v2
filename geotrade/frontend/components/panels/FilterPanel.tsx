// frontend/components/panels/FilterPanel.tsx
// Tension filter with proportion bars + glowing active state.

import type { FilterType, GeoEvent } from "@/types";
import { TENSION_COLOR } from "@/lib/constants";

interface Props {
  filter:   FilterType;
  events:   GeoEvent[];
  onChange: (f: FilterType) => void;
}

const FILTERS: FilterType[] = ["all", "high", "medium", "low"];

const LABEL_MAP: Record<string, string> = {
  all:    "All Regions",
  high:   "High",
  medium: "Medium",
  low:    "Low",
};

export default function FilterPanel({ filter, events, onChange }: Props) {
  const total = events.length || 1;
  const counts: Record<string, number> = {
    all:    events.length,
    high:   events.filter((e) => e.tension_label === "high").length,
    medium: events.filter((e) => e.tension_label === "medium").length,
    low:    events.filter((e) => e.tension_label === "low").length,
  };

  return (
    <div className="glass-panel p-3">
      <div className="text-[10px] font-mono text-geo-text tracking-widest mb-2.5">
        FILTER BY TENSION
      </div>

      <div className="flex flex-col gap-1">
        {FILTERS.map((f) => {
          const active = filter === f;
          const count  = counts[f];
          const pct    = f === "all" ? 100 : Math.round((count / total) * 100);
          const color  = f === "all" ? "#64748b" : (TENSION_COLOR as Record<string, string>)[f];

          return (
            <button
              key={f}
              onClick={() => onChange(f)}
              className="relative flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-mono transition-all overflow-hidden text-left"
              style={{
                background: active
                  ? `rgba(${f === "high" ? "239,68,68" : f === "medium" ? "245,158,11" : f === "low" ? "34,197,94" : "100,116,139"},0.12)`
                  : "transparent",
                border: `1px solid ${active ? color + "40" : "transparent"}`,
                color: active ? "#fff" : "rgba(255,255,255,0.45)",
              }}
            >
              {/* Proportion fill background */}
              {f !== "all" && (
                <div
                  className="absolute left-0 top-0 bottom-0 rounded-lg transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: `${color}08`,
                  }}
                />
              )}

              {/* Dot */}
              {f !== "all" ? (
                <span
                  className="relative w-2 h-2 rounded-full shrink-0"
                  style={{
                    background: color,
                    boxShadow: active ? `0 0 6px ${color}` : "none",
                  }}
                />
              ) : (
                <span
                  className="relative w-2 h-2 rounded-full shrink-0 border"
                  style={{ borderColor: active ? "#94a3b8" : "#475569" }}
                />
              )}

              {/* Label */}
              <span className="relative flex-1">{LABEL_MAP[f]}</span>

              {/* Count */}
              <span
                className="relative text-[10px] tabular-nums"
                style={{ color: active ? color : "rgba(255,255,255,0.3)" }}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Mini proportion bar at bottom */}
      <div className="mt-3 flex rounded-full overflow-hidden h-1" style={{ gap: "1px" }}>
        {(["high", "medium", "low"] as const).map((lbl) => (
          <div
            key={lbl}
            className="transition-all duration-500"
            style={{
              flex: counts[lbl],
              background: (TENSION_COLOR as Record<string, string>)[lbl],
              opacity: filter === "all" || filter === lbl ? 0.75 : 0.2,
            }}
          />
        ))}
      </div>
    </div>
  );
}
