// frontend/components/ui/StatBadge.tsx
interface Props {
  label: string;
  value: number;
}

export default function StatBadge({ label, value }: Props) {
  return (
    <div className="glass-panel px-4 py-2 text-center min-w-[80px]">
      <div className="text-white font-mono font-bold text-sm">{value.toLocaleString()}</div>
      <div className="text-geo-text font-mono text-[9px] tracking-widest">{label}</div>
    </div>
  );
}
