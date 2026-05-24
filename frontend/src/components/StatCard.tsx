import type { BadgeTone } from "@/components/atoms";

export function StatCard({
  label,
  value,
  tone = "gray",
}: {
  label: string;
  value: number | string;
  tone?: BadgeTone;
}) {
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-num">{value}</div>
    </div>
  );
}
