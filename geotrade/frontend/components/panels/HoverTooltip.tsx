// frontend/components/panels/HoverTooltip.tsx
import type { GeoEvent } from "@/types";
import { tensionColor, formatScore } from "@/lib/constants";

interface Props {
  event: GeoEvent;
  x: number;
  y: number;
}

export default function HoverTooltip({ event, x, y }: Props) {
  const color = tensionColor(event.tension_label);

  // Flip left when near right edge
  const flipX = typeof window !== "undefined" && x > window.innerWidth - 240;

  return (
    <div
      className="geo-tooltip fixed z-30 pointer-events-none"
      style={{
        left:      flipX ? x - 220 : x + 14,
        top:       y - 10,
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}` }}
        />
        <span className="font-semibold text-white text-sm">{event.country}</span>
      </div>
      <div className="space-y-0.5 text-[11px] font-mono">
        <div>
          Tension:{" "}
          <span style={{ color }} className="font-bold">
            {formatScore(event.tension_score)}/100
          </span>
        </div>
        <div className="text-geo-text">Type: <span className="text-white/80 capitalize">{event.event_label}</span></div>
        <div className="text-geo-text">Date: <span className="text-white/80">{event.date}</span></div>
      </div>
    </div>
  );
}
