/* Typed API client — one function per backend endpoint.
   Talks to the FastAPI server at /api (proxied to :8000 in dev). */

import type {
  AccountInfo,
  ConnectAccountResponse,
  DashboardProjection,
  DomainPreferences,
  ObservabilityData,
  ShipmentDetailProjection,
  StatusResponse,
  SyncResult,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? (parsed as { detail: unknown }).detail
        : null;
    const message =
      typeof detail === "string"
        ? detail
        : `Request failed with ${res.status}`;
    throw new ApiError(res.status, parsed, message);
  }
  return parsed as T;
}

export const api = {
  // ── Status ─────────────────────────────────────────────────────
  getStatus(): Promise<StatusResponse> {
    return request("/status");
  },

  // ── Dashboard / shipments ──────────────────────────────────────
  getDashboard(): Promise<DashboardProjection> {
    return request("/dashboard/projection");
  },
  getShipmentDetail(id: string): Promise<ShipmentDetailProjection> {
    return request(`/shipments/${encodeURIComponent(id)}/detail`);
  },
  deleteShipment(id: string): Promise<{ deleted: string }> {
    return request(`/shipments/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  },

  // ── Accounts / sync ────────────────────────────────────────────
  listAccounts(): Promise<AccountInfo[]> {
    return request("/accounts");
  },
  connectAccount(): Promise<ConnectAccountResponse> {
    return request("/accounts/connect", { method: "POST" });
  },
  removeAccount(id: string): Promise<{ removed: string }> {
    return request(`/accounts/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  },
  initialSync(id: string): Promise<SyncResult> {
    return request(`/sync/initial/${encodeURIComponent(id)}`, {
      method: "POST",
    });
  },
  incrementalSync(id: string): Promise<SyncResult> {
    return request(`/sync/incremental/${encodeURIComponent(id)}`, {
      method: "POST",
    });
  },

  // ── Settings: domain allow/block lists ─────────────────────────
  getDomainPrefs(): Promise<DomainPreferences> {
    return request("/settings/domains");
  },
  addAllowlist(domain: string): Promise<DomainPreferences> {
    return request("/settings/domains/allowlist", {
      method: "POST",
      body: JSON.stringify({ domain }),
    });
  },
  removeAllowlist(domain: string): Promise<DomainPreferences> {
    return request(`/settings/domains/allowlist/${encodeURIComponent(domain)}`, {
      method: "DELETE",
    });
  },
  addBlocklist(domain: string): Promise<DomainPreferences> {
    return request("/settings/domains/blocklist", {
      method: "POST",
      body: JSON.stringify({ domain }),
    });
  },
  removeBlocklist(domain: string): Promise<DomainPreferences> {
    return request(`/settings/domains/blocklist/${encodeURIComponent(domain)}`, {
      method: "DELETE",
    });
  },

  // ── Dev observability ──────────────────────────────────────────
  getObservability(): Promise<ObservabilityData> {
    return request("/dev/observability");
  },
};

export type ApiClient = typeof api;
