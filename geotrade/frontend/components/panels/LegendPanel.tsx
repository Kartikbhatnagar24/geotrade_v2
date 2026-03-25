// frontend/components/panels/LegendPanel.tsx
import { TENSION_COLOR } from "@/lib/constants";
import type { TensionLabel } from "@/types";

const LABELS: TensionLabel[] = ["high", "medium", "low"];

export default function LegendPanel() {
  return (
    <div className="glass-panel p-4">
      <div className="text-[10px] font-mono text-geo-text tracking-widest mb-3">LEGEND</div>
      <div className="space-y-2">
        {LABELS.map((label) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{
                backgroundColor: TENSION_COLOR[label],
                boxShadow: `0 0 5px ${TENSION_COLOR[label]}`,
              }}
            />
            <span className="text-xs font-mono text-white/80 capitalize">{label} Tension</span>
          </div>
        ))}
        <div className="flex items-center gap-2 pt-2 mt-1 border-t border-geo-border">
          <span className="w-2.5 h-2.5 rounded-full border border-tension-high/60 animate-pulse flex-shrink-0" />
          <span className="text-xs font-mono text-white/60">Pulse ring = conflict</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-tension-high text-xs">↑</span>
          <span className="text-xs font-mono text-white/60">Height = tension score</span>
        </div>
      </div>
    </div>
  );
}
