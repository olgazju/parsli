import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/api/client";
import type { ShipmentSummaryRow } from "@/api/types";
import { ErrorState, FullLoading } from "@/components/atoms";
import { ParcelCard } from "@/components/ParcelCard";
import { StatCard } from "@/components/StatCard";
import { IconEmptyBox, IconSearch } from "@/components/icons";
import { useToast } from "@/components/Toast";

type Filter = "all" | "active" | "action" | "delivered";

const FILTER_LABELS: Record<Filter, string> = {
  all: "All",
  active: "Active",
  action: "Needs action",
  delivered: "Delivered",
};

const RECEIVED_KEY = "parsli.receivedIds";

function readReceived(): Set<string> {
  try {
    const raw = localStorage.getItem(RECEIVED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function writeReceived(ids: Set<string>) {
  try {
    localStorage.setItem(RECEIVED_KEY, JSON.stringify([...ids]));
  } catch {
    /* ignore */
  }
}

export default function ParcelsScreen() {
  const qc = useQueryClient();
  const { show } = useToast();

  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.getDashboard,
  });

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [received, setReceived] = useState<Set<string>>(readReceived);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteShipment(id),
    onSuccess: () => {
      show("Parcel deleted.", "success");
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Couldn't delete parcel.";
      show(msg, "error");
    },
  });

  const shipments = dashboard.data?.shipments ?? [];
  const filtered = useMemo(
    () => applyFilters(shipments, search, filter, received),
    [shipments, search, filter, received],
  );

  const stats = useMemo(() => {
    if (!dashboard.data) {
      return { active: 0, delivered: 0, orderOnly: 0, review: 0 };
    }
    const d = dashboard.data;
    const localReceivedDelta = shipments.filter(
      (s) => s.current_status !== "delivered" && received.has(s.shipment_id),
    ).length;
    return {
      active: Math.max(0, d.active_count - localReceivedDelta),
      delivered: d.delivered_count + localReceivedDelta,
      orderOnly: d.order_only_count,
      review: d.needs_review_count,
    };
  }, [dashboard.data, shipments, received]);

  const onToggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const onReceive = (id: string) => {
    setReceived((prev) => {
      const next = new Set(prev);
      const was = next.has(id);
      was ? next.delete(id) : next.add(id);
      writeReceived(next);
      show(
        was ? "Removed from received." : "Marked as received.",
        "success",
      );
      return next;
    });
  };

  const onDelete = (s: ShipmentSummaryRow) => {
    const ok = window.confirm(
      `Delete "${s.display_title}"?\n\nThis removes the parcel and its events permanently.`,
    );
    if (!ok) return;
    deleteMutation.mutate(s.shipment_id);
  };

  if (dashboard.isLoading) {
    return (
      <>
        <ScreenHeader total={0} />
        <FullLoading />
      </>
    );
  }

  if (dashboard.isError) {
    const msg =
      dashboard.error instanceof ApiError
        ? dashboard.error.message
        : "Couldn't load parcels. Is the parsli server running?";
    return (
      <>
        <ScreenHeader total={0} />
        <ErrorState message={msg} onRetry={() => void dashboard.refetch()} />
      </>
    );
  }

  const total = shipments.length;
  const noResults = filtered.length === 0;
  const isFiltered = search.trim().length > 0 || filter !== "all";

  return (
    <>
      <ScreenHeader total={total} />

      <div className="stat-grid">
        <StatCard label="Active" value={stats.active} tone="blue" />
        <StatCard label="Delivered" value={stats.delivered} tone="green" />
        <StatCard label="Order only" value={stats.orderOnly} tone="gray" />
        <StatCard
          label="Needs review"
          value={stats.review}
          tone={stats.review > 0 ? "red" : "gray"}
        />
      </div>

      <div className="controls-bar">
        <div className="search-wrap">
          <IconSearch />
          <input
            className="search-input"
            type="text"
            placeholder="Search merchant, carrier, tracking…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="filter-pills">
          {(Object.keys(FILTER_LABELS) as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              className={`filter-pill${filter === f ? " active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </div>

      {noResults ? (
        isFiltered ? (
          <div className="no-results">
            No parcels match your search. Try broadening the filter.
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-glyph">
              <IconEmptyBox size={52} />
            </div>
            <div className="empty-title">No active parcels</div>
            <div className="empty-sub">
              Connect a source to start scanning for parcels, or sit back and
              enjoy the quiet.
            </div>
          </div>
        )
      ) : (
        <div className="parcel-list">
          {filtered.map((s) => (
            <ParcelCardWithDetail
              key={s.shipment_id}
              shipment={s}
              expanded={expanded.has(s.shipment_id)}
              received={received.has(s.shipment_id)}
              onToggle={() => onToggle(s.shipment_id)}
              onReceive={() => onReceive(s.shipment_id)}
              onDelete={() => onDelete(s)}
            />
          ))}
        </div>
      )}
    </>
  );
}

function ScreenHeader({ total }: { total: number }) {
  return (
    <div className="screen-header">
      <div className="screen-title">Parcels</div>
      <div className="screen-sub">All tracked shipments · {total} total</div>
    </div>
  );
}

function applyFilters(
  shipments: ShipmentSummaryRow[],
  query: string,
  filter: Filter,
  receivedIds: Set<string>,
): ShipmentSummaryRow[] {
  let list = shipments;
  const q = query.trim().toLowerCase();
  if (q) {
    list = list.filter((s) => {
      const haystack = [
        s.display_title,
        s.display_merchant,
        s.merchant ?? "",
        s.tracking_number ?? "",
        s.order_number ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }
  if (filter === "active") {
    list = list.filter(
      (s) =>
        s.current_status !== "delivered" && !receivedIds.has(s.shipment_id),
    );
  } else if (filter === "action") {
    list = list.filter(
      (s) =>
        s.current_status === "action_required" ||
        s.current_status === "payment_required" ||
        s.needs_review,
    );
  } else if (filter === "delivered") {
    list = list.filter(
      (s) =>
        s.current_status === "delivered" || receivedIds.has(s.shipment_id),
    );
  }
  return list;
}

interface ParcelCardWithDetailProps {
  shipment: ShipmentSummaryRow;
  expanded: boolean;
  received: boolean;
  onToggle: () => void;
  onReceive: () => void;
  onDelete: () => void;
}

function ParcelCardWithDetail({
  shipment,
  expanded,
  received,
  onToggle,
  onReceive,
  onDelete,
}: ParcelCardWithDetailProps) {
  const detail = useQuery({
    queryKey: ["shipment-detail", shipment.shipment_id],
    queryFn: () => api.getShipmentDetail(shipment.shipment_id),
    enabled: expanded,
  });

  return (
    <ParcelCard
      shipment={shipment}
      expanded={expanded}
      received={received}
      detail={detail.data}
      detailLoading={detail.isFetching}
      onToggle={onToggle}
      onReceive={onReceive}
      onDelete={onDelete}
    />
  );
}
