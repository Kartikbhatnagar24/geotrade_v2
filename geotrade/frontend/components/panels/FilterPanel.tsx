// frontend/components/panels/FilterPanel.tsx
import type { FilterType, GeoEvent } from "@/types";
import { TENSION_COLOR } from "@/lib/constants";

interface Props {
  filter: FilterType;
  events: GeoEvent[];
  onChange: (f: FilterType) => void;
}

const FILTERS: FilterType[] = ["all", "high", "medium", "low"];

export default function FilterPanel({ filter, events, onChange }: Props) {
  return (
    <div className="glass-panel p-4">
      <div className="text-[10px] font-mono text-geo-text tracking-widest mb-3">
        FILTER BY TENSION
      </div>
      <div className="flex flex-col gap-1">
        {FILTERS.map((f) => {
          const count =
            f === "all" ? events.length : events.filter((e) => e.tension_label === f).length;
          const active = filter === f;
          return (
            <button
              key={f}
              onClick={() => onChange(f)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono transition-all ${
                active
                  ? "bg-geo-border text-white"
                  : "text-geo-text hover:text-white hover:bg-geo-panel"
              }`}
            >
              {f !== "all" ? (
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: TENSION_COLOR[f],
                    boxShadow: active ? `0 0 5px ${TENSION_COLOR[f]}` : "none",
                  }}
                />
              ) : (
                <span className="w-2 h-2 flex-shrink-0 opacity-50">●</span>
              )}
              <span className="capitalize flex-1 text-left">{f === "all" ? "All" : f}</span>
              <span className="text-geo-text/60">{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
