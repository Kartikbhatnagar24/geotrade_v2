// frontend/components/panels/LegendPanel.tsx
// Compact globe encoding legend.

import { TENSION_COLOR } from "@/lib/constants";
import type { TensionLabel } from "@/types";

const TENSION_ROWS: { label: TensionLabel; range: string }[] = [
  { label: "high",   range: "65–100" },
  { label: "medium", range: "35–64"  },
  { label: "low",    range: "0–34"   },
];

export default function LegendPanel() {
  return (
    <div className="glass-panel p-3">
      <div className="text-[10px] font-mono text-geo-text tracking-widest mb-2.5">LEGEND</div>

      {/* Tension color rows */}
      <div className="flex flex-col gap-1.5 mb-3">
        {TENSION_ROWS.map(({ label, range }) => {
          const color = (TENSION_COLOR as Record<string, string>)[label];
          return (
            <div key={label} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: color, boxShadow: `0 0 5px ${color}60` }}
                />
                <span className="text-[11px] font-mono text-white/75 capitalize">
                  {label} Tension
                </span>
              </div>
              <span className="text-[9px] font-mono text-geo-text/60">{range}</span>
            </div>
          );
        })}
      </div>

      {/* Divider */}
      <div className="border-t border-geo-border/60 pt-2.5 flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full border border-red-500/60 animate-pulse shrink-0"
            style={{ boxShadow: "0 0 4px rgba(239,68,68,0.4)" }}
          />
          <span className="text-[10px] font-mono text-white/50">Ring = active conflict</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-white/40 leading-none">▲</span>
          <span className="text-[10px] font-mono text-white/50">Height = tension score</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-white/40">◎</span>
          <span className="text-[10px] font-mono text-white/50">Click country → analysis</span>
        </div>
      </div>
    </div>
  );
}
