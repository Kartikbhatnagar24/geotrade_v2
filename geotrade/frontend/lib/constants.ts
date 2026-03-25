// frontend/lib/constants.ts
import type { GeoEvent, TensionLabel } from "@/types";

export const TENSION_COLOR: Record<TensionLabel, string> = {
  high:   "#ef4444",
  medium: "#f59e0b",
  low:    "#22c55e",
};

export const TENSION_RING_COLOR: Record<TensionLabel, string> = {
  high:   "#ef444460",
  medium: "#f59e0b40",
  low:    "#22c55e30",
};

export function tensionColor(label: string): string {
  return TENSION_COLOR[label as TensionLabel] ?? "#94a3b8";
}

export function formatScore(score: number): string {
  return (score * 100).toFixed(0);
}

// ── Offline demo data (shown when API is unreachable) ─────────
export const DEMO_EVENTS: GeoEvent[] = [
  { country:"Ukraine",     iso:"UA", latitude:50.45, longitude:30.52,  tension_score:0.93, tension_label:"high",   event_label:"conflict",   event_count:18, date:"2024-01-15", sample_title:"Ukrainian forces repel attacks in Kharkiv region",          sample_url:"#" },
  { country:"Russia",      iso:"RU", latitude:55.75, longitude:37.62,  tension_score:0.91, tension_label:"high",   event_label:"conflict",   event_count:12, date:"2024-01-15", sample_title:"Russia-Ukraine conflict escalates on eastern front",         sample_url:"#" },
  { country:"Israel",      iso:"IL", latitude:31.77, longitude:35.22,  tension_score:0.88, tension_label:"high",   event_label:"conflict",   event_count:14, date:"2024-01-15", sample_title:"Gaza ceasefire talks collapse in Cairo",                    sample_url:"#" },
  { country:"North Korea", iso:"KP", latitude:39.02, longitude:125.75, tension_score:0.87, tension_label:"high",   event_label:"conflict",   event_count:5,  date:"2024-01-12", sample_title:"North Korea fires ballistic missiles into Sea of Japan",    sample_url:"#" },
  { country:"Iran",        iso:"IR", latitude:35.69, longitude:51.42,  tension_score:0.82, tension_label:"high",   event_label:"sanctions",  event_count:7,  date:"2024-01-13", sample_title:"Iran nuclear talks stall as sanctions loom",                sample_url:"#" },
  { country:"Sudan",       iso:"SD", latitude:15.55, longitude:32.53,  tension_score:0.79, tension_label:"high",   event_label:"conflict",   event_count:6,  date:"2024-01-10", sample_title:"Sudan civil war displaces millions amid humanitarian crisis",sample_url:"#" },
  { country:"China",       iso:"CN", latitude:39.91, longitude:116.39, tension_score:0.74, tension_label:"high",   event_label:"trade",      event_count:8,  date:"2024-01-14", sample_title:"US-China semiconductor tariffs spark trade war fears",       sample_url:"#" },
  { country:"Pakistan",    iso:"PK", latitude:33.72, longitude:73.06,  tension_score:0.71, tension_label:"high",   event_label:"elections",  event_count:6,  date:"2024-01-14", sample_title:"Pakistan political crisis deepens after Imran Khan verdict", sample_url:"#" },
  { country:"Nigeria",     iso:"NG", latitude:9.07,  longitude:7.40,   tension_score:0.68, tension_label:"medium", event_label:"conflict",   event_count:4,  date:"2024-01-07", sample_title:"Boko Haram attacks surge in northeast Nigeria",              sample_url:"#" },
  { country:"Venezuela",   iso:"VE", latitude:10.49, longitude:-66.88, tension_score:0.62, tension_label:"medium", event_label:"elections",  event_count:5,  date:"2024-01-09", sample_title:"Venezuela election results disputed, triggering turmoil",    sample_url:"#" },
  { country:"Turkey",      iso:"TR", latitude:39.93, longitude:32.86,  tension_score:0.41, tension_label:"medium", event_label:"diplomacy",  event_count:3,  date:"2024-01-08", sample_title:"Turkey-Greece Aegean drilling dispute escalates",            sample_url:"#" },
  { country:"India",       iso:"IN", latitude:28.61, longitude:77.21,  tension_score:0.48, tension_label:"medium", event_label:"diplomacy",  event_count:4,  date:"2024-01-11", sample_title:"India-Pakistan border tensions following Kashmir incident",   sample_url:"#" },
  { country:"Japan",       iso:"JP", latitude:35.68, longitude:139.69, tension_score:0.35, tension_label:"medium", event_label:"diplomacy",  event_count:3,  date:"2024-01-04", sample_title:"Japan condemns North Korean missile tests",                  sample_url:"#" },
  { country:"Germany",     iso:"DE", latitude:52.52, longitude:13.40,  tension_score:0.22, tension_label:"low",    event_label:"diplomacy",  event_count:2,  date:"2024-01-05", sample_title:"Germany mediates EU sanctions negotiations",                 sample_url:"#" },
  { country:"Brazil",      iso:"BR", latitude:-15.78,longitude:-47.93, tension_score:0.29, tension_label:"low",    event_label:"trade",      event_count:2,  date:"2024-01-06", sample_title:"Brazil pushes back on IMF adjustment terms",                sample_url:"#" },
];
