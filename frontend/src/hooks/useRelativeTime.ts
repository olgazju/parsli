/** Format an ISO date string into a short "2h" / "3d" / "12m" relative label,
 * suitable for the parcel-card age column and timeline rows. */
export function formatRelativeAge(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "";
  const diffMs = Date.now() - d.valueOf();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${Math.max(0, minutes)}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo`;
  return `${Math.round(months / 12)}y`;
}

/** Format an ISO date string as "Jun 14" for timeline rows. */
export function formatEventDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "";
  try {
    return new Intl.DateTimeFormat("en", {
      month: "short",
      day: "numeric",
    }).format(d);
  } catch {
    return d.toLocaleDateString();
  }
}
