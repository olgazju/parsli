import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError, api } from "@/api/client";
import { Badge, ErrorState, FullLoading } from "@/components/atoms";
import type {
  ObservabilityData,
  QueryRunRow,
  RecentProcessingRow,
} from "@/api/types";

export default function DiagnosticsScreen() {
  const obs = useQuery({
    queryKey: ["observability"],
    queryFn: api.getObservability,
    refetchInterval: 5_000,
  });

  if (obs.isLoading) {
    return (
      <>
        <Header />
        <FullLoading />
      </>
    );
  }
  if (obs.isError) {
    const msg =
      obs.error instanceof ApiError
        ? obs.error.message
        : "Couldn't load diagnostics.";
    return (
      <>
        <Header />
        <ErrorState message={msg} onRetry={() => void obs.refetch()} />
      </>
    );
  }

  const data = obs.data!;
  return (
    <>
      <Header />
      <PipelineGrid data={data} />
      <MethodBreakdown rows={data.recent_processing} />
      <RecentProcessingTable rows={data.recent_processing} />
      <QueryBatches rows={data.recent_query_runs} />
    </>
  );
}

function Header() {
  return (
    <div className="screen-header">
      <div className="screen-title">Diagnostics</div>
      <div className="screen-sub">
        Pipeline observability — every stage, locally
      </div>
    </div>
  );
}

function PipelineGrid({ data }: { data: ObservabilityData }) {
  const coverage = data.total_ingested
    ? Math.round((data.total_processed / data.total_ingested) * 100)
    : 0;
  const relevantPct = data.total_processed
    ? Math.round((data.total_relevant / data.total_processed) * 1000) / 10
    : 0;

  const cards = [
    {
      label: "Ingested",
      value: data.total_ingested,
      sub: "all-time",
    },
    {
      label: "Processed",
      value: data.total_processed,
      sub: `${coverage}% coverage`,
    },
    {
      label: "Relevant",
      value: data.total_relevant,
      sub: `${relevantPct}% of processed`,
    },
    {
      label: "Ignored",
      value: data.total_ignored,
      sub: "rule-filtered",
    },
  ];

  return (
    <div className="diag-grid">
      {cards.map((c) => (
        <div key={c.label} className="diag-card">
          <div className="diag-label">{c.label}</div>
          <div className="diag-num">{c.value.toLocaleString()}</div>
          <div className="diag-sub">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

interface MethodSummary {
  method: string;
  count: number;
  ms_avg: number;
}

function MethodBreakdown({ rows }: { rows: RecentProcessingRow[] }) {
  const summary = useMemo(() => summarizeMethods(rows), [rows]);
  const total = summary.reduce((s, r) => s + r.count, 0) || 1;

  return (
    <div className="section-box">
      <div className="section-box-header">
        <div className="section-box-title">Classification method</div>
        <div className="section-box-sub">where decisions come from</div>
      </div>
      <div className="pref-body">
        {summary.length === 0 && (
          <div className="pref-meta">No recent processing yet.</div>
        )}
        {summary.map((m) => {
          const pct = (m.count / total) * 100;
          return (
            <div key={m.method} className="bar-row">
              <div className="bar-row-head">
                <span className="bar-method">{m.method}</span>
                <span className="bar-meta">
                  {m.count.toLocaleString()} ·{" "}
                  {m.ms_avg > 0 ? `${Math.round(m.ms_avg)}ms avg` : "—"}
                </span>
              </div>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${pct}%`,
                    background: methodColor(m.method),
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function summarizeMethods(rows: RecentProcessingRow[]): MethodSummary[] {
  const acc = new Map<string, { count: number; ms_sum: number; ms_n: number }>();
  for (const r of rows) {
    const method = r.classification_method ?? "unknown";
    const entry = acc.get(method) ?? { count: 0, ms_sum: 0, ms_n: 0 };
    entry.count += 1;
    if (typeof r.model_latency_ms === "number") {
      entry.ms_sum += r.model_latency_ms;
      entry.ms_n += 1;
    }
    acc.set(method, entry);
  }
  return [...acc.entries()]
    .map(([method, v]) => ({
      method,
      count: v.count,
      ms_avg: v.ms_n > 0 ? v.ms_sum / v.ms_n : 0,
    }))
    .sort((a, b) => b.count - a.count);
}

function methodColor(method: string): string {
  switch (method) {
    case "rule_match":
      return "var(--c-olive)";
    case "rule_relevant":
      return "var(--c-sage)";
    case "model_classified":
      return "var(--c-sky)";
    case "model_skipped":
      return "var(--c-beige)";
    case "rule_ignore":
      return "var(--c-metal)";
    default:
      return "var(--c-tan)";
  }
}

function RecentProcessingTable({ rows }: { rows: RecentProcessingRow[] }) {
  return (
    <div className="section-box">
      <div className="section-box-header">
        <div className="section-box-title">Recent processing</div>
        <div className="section-box-sub">last 30 emails</div>
      </div>
      {rows.length === 0 ? (
        <div className="pref-body pref-meta">
          No processed emails yet. Connect a source and run a sync.
        </div>
      ) : (
        <table className="diag-table">
          <thead>
            <tr>
              <th>Email ID</th>
              <th>Result</th>
              <th>Method</th>
              <th>AI latency</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.email_id}>
                <td className="mono">{r.email_id.slice(0, 12)}…</td>
                <td>
                  {r.is_relevant ? (
                    <span className="dot-row">
                      <span className="dot dot-green" />
                      relevant
                    </span>
                  ) : (
                    <span className="dot-row">
                      <span className="dot dot-gray" />
                      {r.ignore_reason ?? "ignored"}
                    </span>
                  )}
                </td>
                <td className="mono">{r.classification_method ?? "—"}</td>
                <td className="mono">
                  {r.model_latency_ms != null
                    ? `${Math.round(r.model_latency_ms)}ms`
                    : "—"}
                </td>
                <td>
                  {r.status ? (
                    <Badge
                      label={r.status.replace(/_/g, " ")}
                      tone="gray"
                    />
                  ) : (
                    <span style={{ color: "var(--fg-3)" }}>—</span>
                  )}
                  {r.needs_review && (
                    <span className="review-flag" title="Needs review">
                      ⚠
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function QueryBatches({ rows }: { rows: QueryRunRow[] }) {
  const grouped = useMemo(() => {
    const m = new Map<string, QueryRunRow[]>();
    for (const r of rows) {
      const list = m.get(r.fetch_batch_id) ?? [];
      list.push(r);
      m.set(r.fetch_batch_id, list);
    }
    return [...m.entries()].map(([id, runs]) => {
      const earliest = runs.reduce(
        (acc, r) => Math.min(acc, new Date(r.started_at).valueOf()),
        Number.POSITIVE_INFINITY,
      );
      const ago = Math.max(0, Math.round((Date.now() - earliest) / 60_000));
      return { id, runs, ago };
    });
  }, [rows]);

  return (
    <div className="section-box">
      <div className="section-box-header">
        <div className="section-box-title">Recent query runs</div>
      </div>
      {grouped.length === 0 ? (
        <div className="pref-body pref-meta">
          No query runs recorded yet.
        </div>
      ) : (
        grouped.map((b) => (
          <div key={b.id} className="query-batch">
            <div className="batch-id">
              batch {b.id.slice(0, 8)} · {b.ago}m ago
            </div>
            {b.runs.map((r) => (
              <div key={`${b.id}-${r.query_name}`} className="query-row">
                <span className="query-name">{r.query_name}</span>
                <span className="query-count">{r.result_count} results</span>
                <span className="query-ms">
                  {r.duration_ms != null
                    ? `${Math.round(r.duration_ms)}ms`
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );
}
