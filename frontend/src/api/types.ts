/* Shared API types — mirror the Pydantic models in backend/src/parsli/api/.
   Kept in one file so the client and screens import from a single place. */

export type ShipmentStatus =
  | "order_confirmed"
  | "shipped"
  | "received_by_carrier"
  | "in_transit"
  | "arrived_in_destination_country"
  | "customs_pending"
  | "customs_released"
  | "handed_to_local_carrier"
  | "ready_for_pickup"
  | "out_for_delivery"
  | "delivered"
  | "payment_required"
  | "action_required"
  | "delayed_or_problem"
  | "unknown";

export type ChronologyStatus = "ok" | "warning" | "conflict";

export interface ShipmentSummaryRow {
  shipment_id: string;
  display_title: string;
  merchant: string | null;
  display_merchant: string;
  tracking_number: string | null;
  order_number: string | null;
  current_status: ShipmentStatus;
  current_status_label: string;
  last_status_date: string;
  events_count: number;
  shipment_kind: "tracked" | "order_only" | string;
  chronology_status: ChronologyStatus;
  chronology_reason: string | null;
  needs_review: boolean;
}

export interface ShipmentEventProjection {
  event_date: string;
  status: ShipmentStatus;
  status_label: string;
  status_confidence: number;
  status_evidence: string;
  tracking_number: string | null;
  order_number: string | null;
  email_id: string;
  carrier: string | null;
  sender_display_name: string | null;
  sender_domain: string | null;
  source_label: string | null;
  decision_source: string | null;
  needs_review: boolean;
  model_mode: string | null;
  model_latency_ms: number | null;
}

export interface ShipmentDetailProjection {
  shipment_id: string;
  display_title: string;
  merchant: string | null;
  display_merchant: string;
  tracking_number: string | null;
  order_number: string | null;
  current_status: ShipmentStatus;
  current_status_label: string;
  last_status_date: string;
  first_seen_at: string;
  shipment_kind: string;
  chronology_status: ChronologyStatus;
  chronology_reason: string | null;
  chronology_notes: string[];
  needs_review: boolean;
  merge_confidence: number;
  events: ShipmentEventProjection[];
}

export interface DashboardProjection {
  shipments: ShipmentSummaryRow[];
  total_count: number;
  active_count: number;
  delivered_count: number;
  order_only_count: number;
  needs_review_count: number;
  generated_at: string;
}

export interface AccountInfo {
  account_id: string;
  initial_sync_completed: boolean;
  last_sync_at: string | null;
  lookback_days: number;
}

export interface SyncResult {
  account_id: string;
  total_fetched: number | null;
  new_ingested: number;
  processed: number;
}

export interface ConnectAccountResponse {
  auth_url: string;
  state: string;
}

export interface DomainPreferences {
  allowlist: string[];
  blocklist: string[];
  exclude_senders: string[];
}

export interface StatusResponse {
  credentials_configured: boolean;
  version: string;
}

export interface RecentProcessingRow {
  email_id: string;
  classification_method: string | null;
  is_relevant: boolean;
  ignore_reason: string | null;
  model_mode: string | null;
  status: string | null;
  decision_source: string | null;
  model_latency_ms: number | null;
  needs_review: boolean;
  processed_at: string | null;
}

export interface QueryRunRow {
  fetch_batch_id: string;
  query_name: string;
  result_count: number;
  duration_ms: number | null;
  started_at: string;
}

export interface ObservabilityData {
  total_ingested: number;
  total_processed: number;
  total_relevant: number;
  total_ignored: number;
  recent_processing: RecentProcessingRow[];
  recent_query_runs: QueryRunRow[];
}
