// frontend/components/panels/EventCard.tsx
import type { GeoEvent } from "@/types";
import { tensionColor, formatScore } from "@/lib/constants";

interface Props {
  event: GeoEvent;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-[11px] font-mono text-geo-text">{label}</span>
      <span className="text-[11px] font-mono text-white/80 capitalize">{value}</span>
    </div>
  );
}

export default function EventCard({ event, onClose }: Props) {
  const color = tensionColor(event.tension_label);

  return (
    <div className="glass-panel p-4 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-[10px] font-mono text-geo-text tracking-widest mb-1">
            SELECTED EVENT
          </div>
          <h3 className="text-white font-semibold text-sm leading-tight">{event.country}</h3>
          <span className="text-[10px] font-mono text-geo-text">{event.iso}</span>
        </div>
        <button
          onClick={onClose}
          className="text-geo-text hover:text-white transition-colors text-xl leading-none mt-0.5"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* Tension badge */}
      <div className="flex items-center gap-2 mb-3 py-2 px-3 rounded-lg bg-geo-bg/60">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
        />
        <span className="text-xs font-mono flex-1" style={{ color }}>
          {event.tension_label.toUpperCase()} TENSION
        </span>
        <span className="text-white font-mono font-bold text-sm">
          {formatScore(event.tension_score)}
          <span className="text-geo-text text-xs font-normal">/100</span>
        </span>
      </div>

      {/* Score bar */}
      <div className="w-full h-1 bg-geo-border rounded-full mb-4">
        <div
          className="h-1 rounded-full transition-all duration-500"
          style={{ width: `${event.tension_score * 100}%`, backgroundColor: color }}
        />
      </div>

      {/* Details */}
      <div className="space-y-1.5 mb-4">
        <Row label="Event Type"  value={event.event_label} />
        <Row label="Articles"    value={String(event.event_count)} />
        <Row label="Date"        value={event.date} />
        <Row label="Coordinates" value={`${event.latitude.toFixed(2)}, ${event.longitude.toFixed(2)}`} />
      </div>

      {/* Sample article */}
      {event.sample_title && (
        <div className="border-t border-geo-border pt-3">
          <div className="text-[10px] font-mono text-geo-text tracking-widest mb-1.5">
            SAMPLE ARTICLE
          </div>
          <p className="text-xs text-white/70 leading-relaxed line-clamp-3">
            {event.sample_title}
          </p>
          {event.sample_url && event.sample_url !== "#" && (
            <a
              href={event.sample_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent text-xs mt-1.5 block hover:underline"
            >
              Read source →
            </a>
          )}
        </div>
      )}
    </div>
  );
}
