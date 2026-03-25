// frontend/components/ui/LoadingScreen.tsx
export default function LoadingScreen() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-geo-bg">
      <div className="relative w-28 h-28 mb-8">
        <div className="absolute inset-0 rounded-full border border-accent/10 animate-ping" />
        <div className="absolute inset-2 rounded-full border border-accent/30 animate-pulse" />
        <div className="absolute inset-4 rounded-full border border-accent/60" />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-accent text-xs font-bold tracking-widest">GT</span>
        </div>
      </div>
      <p className="font-mono text-accent text-sm tracking-[0.35em] animate-pulse">
        GEOTRADE
      </p>
      <p className="font-mono text-geo-text text-[10px] mt-2 tracking-[0.25em]">
        LOADING TENSION SIGNALS
      </p>
    </div>
  );
}
