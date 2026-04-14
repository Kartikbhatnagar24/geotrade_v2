// frontend/components/panels/HoverTooltip.tsx
// Globe country hover tooltip — v2: adds tension regime + velocity badge.
import type { GeoEvent } from "@/types";
import { tensionColor, formatScore } from "@/lib/constants";

interface Props {
  event: GeoEvent;
  x: number;
  y: number;
}

function regimeDot(regime?: string) {
  const colors: Record<string, string> = {
    CALM:    "#22c55e",
    RISING:  "#f59e0b",
    PEAK:    "#ef4444",
    COOLING: "#38bdf8",
  };
  return colors[regime ?? ""] ?? null;
}

export default function HoverTooltip({ event, x, y }: Props) {
  const color = tensionColor(event.tension_label);
  const flipX = typeof window !== "undefined" && x > window.innerWidth - 240;
  const rColor = regimeDot(event.tension_regime);

  return (
    <div
      className="geo-tooltip fixed z-30 pointer-events-none"
      style={{
        left: flipX ? x - 220 : x + 14,
        top:  y - 10,
      }}
    >
      {/* Country name */}
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}` }}
        />
        <span className="font-semibold text-white text-sm">{event.country}</span>
      </div>

      {/* Core stats */}
      <div className="space-y-0.5 text-[11px] font-mono">
        <div>
          Tension:{" "}
          <span style={{ color }} className="font-bold">
            {formatScore(event.tension_score)}/100
          </span>
        </div>
        <div className="text-geo-text">
          Type: <span className="text-white/80 capitalize">{event.event_label}</span>
        </div>
        <div className="text-geo-text">
          Date: <span className="text-white/80">{event.date}</span>
        </div>

        {/* Regime badge — only shown when available */}
        {event.tension_regime && rColor && (
          <div className="flex items-center gap-1.5 pt-1 mt-1 border-t border-white/10">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: rColor, boxShadow: `0 0 3px ${rColor}` }}
            />
            <span className="text-white/60">{event.tension_regime}</span>
            {event.tension_velocity_7d != null && Math.abs(event.tension_velocity_7d) > 0.01 && (
              <span
                className="font-bold"
                style={{ color: event.tension_velocity_7d > 0 ? "#ef4444" : "#22c55e" }}
              >
                {event.tension_velocity_7d > 0 ? "↑" : "↓"}
                {Math.abs(event.tension_velocity_7d * 100).toFixed(1)}pt
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
