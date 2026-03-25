/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts}",
  ],
  theme: {
    extend: {
      colors: {
        "geo-bg":       "#050b14",
        "geo-panel":    "#0d1627",
        "geo-border":   "#1a2744",
        "geo-text":     "#64748b",
        "accent":       "#38bdf8",
        "tension-high": "#ef4444",
        "tension-med":  "#f59e0b",
        "tension-low":  "#22c55e",
      },
      fontFamily: {
        sans: ["'DM Sans'", "sans-serif"],
        mono: ["'Space Mono'", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":    "fadeIn 0.25s ease-out both",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
