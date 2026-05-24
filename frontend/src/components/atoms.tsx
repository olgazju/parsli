import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { ShipmentStatus } from "@/api/types";

/* ── Status → color mappings (port of UI kit constants) ───────── */

export const STATUS_BADGE: Record<ShipmentStatus, BadgeTone> = {
  delivered: "green",
  shipped: "blue",
  received_by_carrier: "blue",
  in_transit: "blue",
  arrived_in_destination_country: "blue",
  customs_pending: "yellow",
  customs_released: "yellow",
  handed_to_local_carrier: "blue",
  out_for_delivery: "yellow",
  ready_for_pickup: "yellow",
  action_required: "red",
  payment_required: "red",
  delayed_or_problem: "red",
  order_confirmed: "gray",
  unknown: "gray",
};

export const STATUS_BORDER: Record<ShipmentStatus, string> = {
  delivered: "var(--c-olive)",
  shipped: "var(--c-sky)",
  received_by_carrier: "var(--c-sky)",
  in_transit: "var(--c-sky)",
  arrived_in_destination_country: "var(--c-sky)",
  handed_to_local_carrier: "var(--c-sky)",
  customs_pending: "var(--c-yellow)",
  customs_released: "var(--c-yellow)",
  out_for_delivery: "var(--c-yellow)",
  ready_for_pickup: "var(--c-yellow)",
  action_required: "var(--c-jacket-red)",
  payment_required: "var(--c-jacket-red)",
  delayed_or_problem: "var(--c-jacket-red)",
  order_confirmed: "var(--c-beige)",
  unknown: "var(--c-beige)",
};

const MILESTONE: Partial<Record<ShipmentStatus, number>> = {
  order_confirmed: 0,
  shipped: 1,
  received_by_carrier: 1,
  in_transit: 1,
  arrived_in_destination_country: 1,
  customs_pending: 1,
  customs_released: 1,
  handed_to_local_carrier: 1,
  out_for_delivery: 2,
  ready_for_pickup: 2,
  delivered: 3,
};

const MILESTONE_LABELS = ["Ordered", "Shipped", "Arriving", "Delivered"] as const;

/* ── Badge ────────────────────────────────────────────────────── */

export type BadgeTone = "blue" | "green" | "yellow" | "red" | "gray";

export function Badge({
  status,
  label,
  tone,
}: {
  status?: ShipmentStatus;
  label: string;
  tone?: BadgeTone;
}) {
  const resolved = tone ?? (status ? STATUS_BADGE[status] : "gray");
  return <span className={`badge badge-${resolved}`}>{label}</span>;
}

/* ── Button ──────────────────────────────────────────────────── */

export type ButtonKind = "primary" | "secondary" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  kind?: ButtonKind;
  size?: "md" | "sm";
}

export function Button({
  kind = "primary",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonProps) {
  const cls = `btn btn-${kind}${size === "sm" ? " btn-sm" : ""}${className ? ` ${className}` : ""}`;
  return (
    <button className={cls} {...rest}>
      {children}
    </button>
  );
}

/* ── Spinner ─────────────────────────────────────────────────── */

export function Spinner({ lg }: { lg?: boolean }) {
  return <span className={`spinner${lg ? " lg" : ""}`} aria-hidden="true" />;
}

export function FullLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="full-loading">
      <Spinner lg />
      <span>{label}</span>
    </div>
  );
}

/* ── MiniTracker (Ordered → Shipped → Arriving → Delivered) ──── */

export function MiniTracker({ status }: { status: ShipmentStatus }) {
  const cur = MILESTONE[status];
  if (cur === undefined) return null;
  return (
    <>
      <div className="mini-tracker">
        {MILESTONE_LABELS.map((_, i) => {
          const dotClass = i < cur ? "past" : i === cur ? "current" : "future";
          const lineClass = i < cur ? "past" : "future";
          return (
            <span key={i} style={{ display: "contents" }}>
              <div className={`track-dot ${dotClass}`} />
              {i < MILESTONE_LABELS.length - 1 && (
                <div className={`track-line ${lineClass}`} />
              )}
            </span>
          );
        })}
      </div>
      <div className="track-labels">
        {MILESTONE_LABELS.map((l) => (
          <span key={l}>{l}</span>
        ))}
      </div>
    </>
  );
}

/* ── ActionBanner (red pulsing dot or yellow payment dot) ────── */

export function ActionBanner({
  kind,
}: {
  kind: "action_required" | "payment_required";
}) {
  if (kind === "action_required") {
    return (
      <div className="action-banner">
        <div className="action-banner-dot" />
        <div className="action-banner-text">
          Action required — expand to see details.
        </div>
      </div>
    );
  }
  return (
    <div className="action-banner payment">
      <div className="action-banner-dot" />
      <div className="action-banner-text">
        Payment required — expand to see details.
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Couldn't load",
  message,
  onRetry,
}: {
  title?: string;
  message?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="empty-state">
      <div className="empty-glyph" aria-hidden="true">
        ⚠
      </div>
      <div className="empty-title">{title}</div>
      <div className="empty-sub">{message ?? "Something went wrong."}</div>
      {onRetry && (
        <Button kind="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
