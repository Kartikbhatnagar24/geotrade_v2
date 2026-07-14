// frontend/components/globe/GlobeViewer.tsx
// Renders the globe.gl 3D globe. Loaded dynamically (no SSR).
//
// Interaction model:
//   PRIMARY — click a country polygon → opens CountryTradingPanel
//   HOVER   — polygon hover → HoverTooltip
//   MARKERS — cylindrical bars (height = tension) + pulse rings on high-tension

import { useEffect, useRef } from "react";
import type { GeoEvent, FilterType } from "@/types";

interface Props {
  events: GeoEvent[];
  filter: FilterType;
  onHover: (event: GeoEvent | null) => void;
  onClick: (event: GeoEvent) => void;
}

// ── Tension-based country colors ──────────────────────────────
const TENSION_CAP_COLOR: Record<string, string> = {
  high:   "#dc2626EE",
  medium: "#d97706EE",
  low:    "#22c55eEE",
};

// ── Star data ─────────────────────────────────────────────────
const NUM_STARS = 900;

function initStars(w: number, h: number) {
  return Array.from({ length: NUM_STARS }, () => ({
    x:       Math.random() * w,
    y:       Math.random() * h,
    r:       Math.random() * 1.4 + 0.2,
    alpha:   Math.random() * 0.7 + 0.3,
    speed:   Math.random() * 0.008 + 0.002,
    phase:   Math.random() * Math.PI * 2,
  }));
}

export default function GlobeViewer({ events, filter, onHover, onClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const starsRef     = useRef<HTMLCanvasElement>(null);
  const globeRef     = useRef<any>(null);
  const cleanupRef   = useRef<() => void>(() => {});
  const rafRef       = useRef<number>(0);

  // ── Starfield animation ────────────────────────────────────
  useEffect(() => {
    const canvas = starsRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    let stars = initStars(canvas.width, canvas.height);
    let t = 0;

    function draw() {
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);
      t += 0.016;
      for (const s of stars) {
        const a = s.alpha * (0.6 + 0.4 * Math.sin(t * s.speed * 60 + s.phase));
        ctx!.beginPath();
        ctx!.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        ctx!.fill();
      }
      rafRef.current = requestAnimationFrame(draw);
    }

    draw();

    const handleResize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
      stars = initStars(canvas.width, canvas.height);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  // ── Globe init ─────────────────────────────────────────────
  useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;

    let cancelled = false;

    async function init() {
      const GlobeGL = (await import("globe.gl")).default;
      if (cancelled || !containerRef.current) return;

      cleanupRef.current();
      containerRef.current.innerHTML = "";

      const filtered =
        filter === "all" ? events : events.filter((e) => e.tension_label === filter);

      // Build fast ISO → event lookup
      const byIso = new Map(events.map((e) => [e.iso.toUpperCase(), e]));
      const activeIsos = new Set(filtered.map((e) => e.iso.toUpperCase()));

      // Fetch world GeoJSON
      const geoJson = await fetch(
        "https://raw.githubusercontent.com/vasturiano/globe.gl/master/example/datasets/ne_110m_admin_0_countries.geojson"
      ).then((r) => r.json());

      function featToEvent(feat: any): GeoEvent | null {
        const iso2 = (feat.properties.ISO_A2 || "").toUpperCase();
        const iso3 = (feat.properties.ISO_A3 || "").toUpperCase();
        return byIso.get(iso2) || byIso.get(iso3) || null;
      }

      const globe = new (GlobeGL as any)()(containerRef.current)
        .width(window.innerWidth)
        .height(window.innerHeight)
        .backgroundColor("rgba(0,0,0,0)")

        // ── Globe textures — nighttime earth from space ────────
        .globeImageUrl("https://unpkg.com/three-globe/example/img/earth-night.jpg")
        .bumpImageUrl("https://unpkg.com/three-globe/example/img/earth-topology.png")

        // ── Country Polygons ────────────────────────────────────
        .polygonsData(geoJson.features)
        .polygonAltitude((feat: any) => {
          const ev = featToEvent(feat);
          if (!ev) return 0.003;
          return ev.tension_label === "high" ? 0.012 : ev.tension_label === "medium" ? 0.007 : 0.004;
        })
        .polygonCapColor((feat: any) => {
          const ev = featToEvent(feat);
          const iso2 = (feat.properties.ISO_A2 || "").toUpperCase();
          const isActive = activeIsos.has(iso2) || activeIsos.has((feat.properties.ISO_A3 || "").toUpperCase());
          if (!isActive) return "rgba(18, 32, 56, 0.75)"; // dark navy for non-active
          return TENSION_CAP_COLOR[ev!.tension_label] ?? "#22c55eEE";
        })
        .polygonSideColor((feat: any) => {
          const iso2 = (feat.properties.ISO_A2 || "").toUpperCase();
          return activeIsos.has(iso2) ? "rgba(0,0,0,0.4)" : "rgba(0,0,0,0.2)";
        })
        .polygonStrokeColor((feat: any) => {
          const iso2 = (feat.properties.ISO_A2 || "").toUpperCase();
          return activeIsos.has(iso2) ? "rgba(255,255,255,0.4)" : "rgba(80,110,160,0.18)";
        })
        // Polygon is the PRIMARY interaction
        .onPolygonHover((feat: any) => {
          if (!feat) { onHover(null); return; }
          const ev = featToEvent(feat);
          onHover(ev ?? null);
          if (containerRef.current) {
            (containerRef.current as HTMLElement).style.cursor = ev ? "pointer" : "default";
          }
        })
        .onPolygonClick((feat: any) => {
          const ev = featToEvent(feat);
          if (ev) onClick(ev);
        })

        // ── Pulse rings for high-tension countries ──────────────
        .ringsData(filtered.filter((e) => e.tension_label === "high"))
        .ringLat("latitude")
        .ringLng("longitude")
        .ringMaxRadius(4.5)
        .ringPropagationSpeed(2)
        .ringRepeatPeriod(1000)
        .ringColor(() => "#ef444499")

        // ── Atmosphere glow ─────────────────────────────────────
        .showAtmosphere(true)
        .atmosphereColor("#3b82f6")
        .atmosphereAltitude(0.18);

      // Camera & controls
      const controls = globe.controls();
      controls.autoRotate      = true;
      controls.autoRotateSpeed = 0.35;
      controls.enableDamping   = true;
      controls.dampingFactor   = 0.08;
      controls.minDistance     = 200;

      // Resize
      const onResize = () => {
        if (containerRef.current)
          globe.width(window.innerWidth).height(window.innerHeight);
      };
      window.addEventListener("resize", onResize);

      globeRef.current = globe;
      cleanupRef.current = () => {
        window.removeEventListener("resize", onResize);
        if (containerRef.current) containerRef.current.innerHTML = "";
      };
    }

    init();
    return () => { cancelled = true; };
  }, [events, filter]);

  return (
    <div
      className="fixed inset-0 z-0"
      style={{ background: "#000005" }}
    >
      {/* Starfield layer */}
      <canvas
        ref={starsRef}
        className="absolute inset-0 w-full h-full"
        style={{ zIndex: 0 }}
      />
      {/* Space nebula gradient overlay */}
      <div
        className="absolute inset-0"
        style={{
          zIndex: 1,
          background:
            "radial-gradient(ellipse at 20% 50%, rgba(15,10,40,0.6) 0%, transparent 60%), " +
            "radial-gradient(ellipse at 80% 20%, rgba(5,15,35,0.5) 0%, transparent 50%), " +
            "radial-gradient(ellipse at 50% 50%, rgba(5,15,30,0.3) 0%, transparent 70%)",
        }}
      />
      {/* Globe canvas */}
      <div
        ref={containerRef}
        id="globe-canvas"
        className="absolute inset-0"
        style={{ zIndex: 2 }}
      />
    </div>
  );
}
