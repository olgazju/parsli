import type {
  ShipmentDetailProjection,
  ShipmentEventProjection,
  ShipmentStatus,
  ShipmentSummaryRow,
} from "@/api/types";
import {
  ActionBanner,
  Badge,
  MiniTracker,
  STATUS_BORDER,
  Spinner,
} from "@/components/atoms";
import { formatEventDate, formatRelativeAge } from "@/hooks/useRelativeTime";

const SIDE_STATUSES = new Set<ShipmentStatus>([
  "action_required",
  "payment_required",
  "delayed_or_problem",
]);

// Statuses that warrant showing the freetext evidence to the user. Routine
// transit events are too noisy and often contain raw foreign-language
// boilerplate — keep them collapsed.
const SHOW_EVIDENCE_STATUSES = new Set<ShipmentStatus>([
  "action_required",
  "payment_required",
  "delayed_or_problem",
]);

const AUDIT_PREFIX_RE = /^\s*\[(audit|note)\b[^\]]*\]\s*/i;

function cleanEvidence(text: string | null | undefined): string {
  if (!text) return "";
  const stripped = text.replace(AUDIT_PREFIX_RE, "").trim();
  return stripped;
}

interface ParcelCardProps {
  shipment: ShipmentSummaryRow;
  expanded: boolean;
  received: boolean;
  detail: ShipmentDetailProjection | undefined;
  detailLoading: boolean;
  onToggle: () => void;
  onReceive: () => void;
  onDelete: () => void;
}

export function ParcelCard({
  shipment,
  expanded,
  received,
  detail,
  detailLoading,
  onToggle,
  onReceive,
  onDelete,
}: ParcelCardProps) {
  const s = shipment;
  const isAction = s.current_status === "action_required";
  const isPayment = s.current_status === "payment_required";
  const merchantKnown =
    s.display_merchant && s.display_merchant !== "Unknown";
  const refLabel = s.tracking_number
    ? s.tracking_number
    : s.order_number
      ? `#${s.order_number}`
      : null;

  return (
    <div
      className={`parcel-card${expanded ? " expanded" : ""}${received ? " received-card" : ""}`}
      style={{
        borderLeftColor: STATUS_BORDER[s.current_status] ?? "var(--c-beige)",
      }}
    >
      <div className="card-main" onClick={onToggle}>
        <div className="card-row1">
          <span className="card-title">
            {merchantKnown ? s.display_merchant : s.display_title}
          </span>
          <div className="card-right">
            <Badge status={s.current_status} label={s.current_status_label} />
            <button
              className="expand-btn"
              type="button"
              aria-label="Toggle timeline"
              aria-expanded={expanded}
              onClick={(e) => {
                e.stopPropagation();
                onToggle();
              }}
            >
              ▼
            </button>
          </div>
        </div>

        {refLabel && (
          <div className="card-subtitle">
            <span className="mono">{refLabel}</span>
          </div>
        )}

        <div className="card-row2">
          <span className="card-meta">
            {s.events_count} event{s.events_count === 1 ? "" : "s"}
          </span>
          <span className="card-age">
            {formatRelativeAge(s.last_status_date)} ago
          </span>
        </div>

        {isAction && <ActionBanner kind="action_required" />}
        {isPayment && <ActionBanner kind="payment_required" />}

        <MiniTracker status={s.current_status} />
      </div>

      <div className="card-footer">
        <span />
        <div className="card-links">
          <button
            type="button"
            className={`link-btn${received ? " received-active" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              onReceive();
            }}
          >
            {received ? "✓ Received" : "Mark received"}
          </button>
          <button
            type="button"
            className="link-btn delete-btn"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            Delete
          </button>
        </div>
      </div>

      <div className="card-timeline">
        {expanded && (
          detailLoading && !detail ? (
            <div className="tl-loading">
              <Spinner /> Loading timeline…
            </div>
          ) : (
            <Timeline events={detail?.events ?? []} />
          )
        )}
      </div>
    </div>
  );
}

function Timeline({ events }: { events: ShipmentEventProjection[] }) {
  if (events.length === 0) {
    return (
      <div className="timeline-inner" style={{ padding: 16 }}>
        <span style={{ color: "var(--fg-2)", fontSize: 12 }}>
          No events recorded.
        </span>
      </div>
    );
  }
  const lastIdx = events.length - 1;
  return (
    <div className="timeline-inner">
      {events.map((ev, i) => {
        const isCurrent = i === lastIdx;
        const isSide = SIDE_STATUSES.has(ev.status);
        let dotClass = "past";
        if (isCurrent) dotClass = "current";
        if (isSide) {
          dotClass = `side${ev.status === "payment_required" ? " payment" : ""}`;
        }
        const lineClass = isCurrent ? "" : "past";
        const evidence = SHOW_EVIDENCE_STATUSES.has(ev.status)
          ? cleanEvidence(ev.status_evidence)
          : "";
        return (
          <div key={i} className={`tl-event${isCurrent ? " current" : ""}`}>
            <div className="tl-spine">
              <div className={`tl-dot ${dotClass}`} />
              {i !== lastIdx && <div className={`tl-line ${lineClass}`} />}
            </div>
            <div className="tl-body">
              <div className="tl-header">
                <span className="tl-status">{ev.status_label}</span>
                <span className="tl-date">{formatEventDate(ev.event_date)}</span>
              </div>
              {ev.source_label && (
                <div className="tl-source">
                  via <span className="tl-source-name">{ev.source_label}</span>
                </div>
              )}
              {evidence && <div className="tl-evidence">{evidence}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
