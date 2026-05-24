#!/usr/bin/env python3
"""Minimal dependency-free Parsli shipment dashboard.

Run:
    python3 dashboard.py

Then open:
    http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import html
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_DB_PATH = Path(__file__).parent / ".parsli" / "parsli.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

def resolve_display_merchant(
    merchant: str | None,
    sender_display_name: str | None,
    sender_domain: str | None,
) -> str:
    """Fallback chain matching the projection layer: merchant → display name → domain → Unknown."""
    return merchant or sender_display_name or sender_domain or "Unknown"


def strip_domain_prefix(identifier: str | None) -> str | None:
    """Strip leading 'domain.tld:' prefix from order numbers for display."""
    if not identifier:
        return identifier
    if re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}:', identifier):
        return identifier.split(':', 1)[1]
    return identifier


STATUS_ORDER = [
    "action_required",
    "payment_required",
    "delayed_or_problem",
    "out_for_delivery",
    "ready_for_pickup",
    "handed_to_local_carrier",
    "customs_pending",
    "customs_released",
    "arrived_in_destination_country",
    "in_transit",
    "received_by_carrier",
    "shipped",
    "order_confirmed",
    "delivered",
    "unknown",
]

STATUS_LABELS = {
    "order_confirmed": "order confirmed",
    "shipped": "shipped",
    "received_by_carrier": "received by carrier",
    "in_transit": "in transit",
    "arrived_in_destination_country": "arrived in country",
    "customs_pending": "customs pending",
    "customs_released": "customs released",
    "handed_to_local_carrier": "with local carrier",
    "ready_for_pickup": "ready for pickup",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "payment_required": "payment required",
    "action_required": "action required",
    "delayed_or_problem": "delayed / problem",
    "unknown": "unknown",
}

STATUS_TONES = {
    "action_required": "urgent",
    "payment_required": "urgent",
    "delayed_or_problem": "danger",
    "out_for_delivery": "good",
    "ready_for_pickup": "good",
    "delivered": "done",
    "unknown": "muted",
}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "unknown", (status or "unknown").replace("_", " ").title())


def status_tone(status: str | None) -> str:
    return STATUS_TONES.get(status or "unknown", "normal")


def format_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%b %-d  %H:%M")
    except ValueError:
        return value


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def load_dashboard_data(db_path: Path, query: str = "", status: str = "", show_tickets: bool = False) -> dict:
    if not db_path.exists():
        return {"error": f"SQLite database not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        missing = [name for name in ("shipments", "shipment_events") if not table_exists(conn, name)]
        if missing:
            return {"error": f"Missing required table(s): {', '.join(missing)}"}

        where = []
        params: list[str] = []

        # Exclude tickets unless explicitly requested.
        # The column may not exist in older DBs (before the notebook adds it).
        has_category_col = any(
            row[1] == "shipment_category"
            for row in conn.execute("PRAGMA table_info(shipments)").fetchall()
        )
        if has_category_col and not show_tickets:
            where.append("COALESCE(s.shipment_category, 'parcel') = 'parcel'")

        if status:
            where.append("s.current_status = ?")
            params.append(status)
        if query:
            like = f"%{query.lower()}%"
            where.append(
                "("
                "lower(s.canonical_shipment_id) LIKE ? OR "
                "lower(COALESCE(s.primary_tracking_number, '')) LIKE ? OR "
                "lower(COALESCE(s.primary_order_number, '')) LIKE ? OR "
                "lower(COALESCE(s.merchant, '')) LIKE ? OR "
                "s.canonical_shipment_id IN ("
                "  SELECT canonical_shipment_id FROM shipment_aliases"
                "  WHERE lower(alias_value) LIKE ?"
                ")"
                ")"
            )
            params.extend([like, like, like, like, like])

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        shipments = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    s.canonical_shipment_id AS shipment_key,
                    s.primary_tracking_number AS tracking_number,
                    s.primary_order_number AS order_number,
                    s.merchant,
                    (SELECT se.sender_display_name FROM shipment_events se
                     WHERE se.canonical_shipment_id = s.canonical_shipment_id
                     ORDER BY se.event_date ASC LIMIT 1) AS sender_display_name,
                    (SELECT se.sender_domain FROM shipment_events se
                     WHERE se.canonical_shipment_id = s.canonical_shipment_id
                     ORDER BY se.event_date ASC LIMIT 1) AS sender_domain,
                    s.first_seen_at,
                    s.last_seen_at,
                    s.current_status,
                    s.current_status_date,
                    s.current_status_evidence,
                    s.event_count,
                    s.merge_confidence,
                    s.chronology_ok,
                    s.chronology_severity,
                    s.chronology_notes_json,
                    (
                        SELECT GROUP_CONCAT(
                            alias_type || ':' || alias_value, ' · '
                        )
                        FROM shipment_aliases a
                        WHERE a.canonical_shipment_id = s.canonical_shipment_id
                    ) AS aliases
                FROM shipments s
                {where_sql}
                ORDER BY s.last_seen_at DESC, s.canonical_shipment_id ASC
                """,
                params,
            ).fetchall()
        ]

        all_statuses = [row[0] for row in conn.execute("SELECT current_status FROM shipments").fetchall()]
        status_counts = Counter(all_statuses)
        total_shipments = len(all_statuses)
        total_events = conn.execute("SELECT COUNT(*) FROM shipment_events").fetchone()[0]
        needs_attention = sum(status_counts[s] for s in ("action_required", "payment_required", "delayed_or_problem"))
        active_shipments = total_shipments - status_counts.get("delivered", 0)

        event_rows = conn.execute(
            """
            SELECT
                canonical_shipment_id AS shipment_key,
                event_date,
                status,
                status_confidence,
                status_evidence,
                sender_domain,
                email_id
            FROM shipment_events
            ORDER BY event_date DESC, id DESC
            """
        ).fetchall()
        events_by_shipment: dict[str, list[dict]] = defaultdict(list)
        for row in event_rows:
            events_by_shipment[row["shipment_key"]].append(dict(row))

        return {
            "shipments": shipments,
            "events_by_shipment": events_by_shipment,
            "status_counts": status_counts,
            "total_shipments": total_shipments,
            "total_events": total_events,
            "needs_attention": needs_attention,
            "active_shipments": active_shipments,
            "query": query,
            "status": status,
            "show_tickets": show_tickets,
            "db_path": str(db_path),
        }
    finally:
        conn.close()


def render_page(data: dict) -> str:
    if error := data.get("error"):
        body = f'<main class="shell"><p class="error">{html.escape(error)}</p></main>'
        return render_document(body)

    shipments = data["shipments"]
    status_counts: Counter[str] = data["status_counts"]
    events_by_shipment = data["events_by_shipment"]
    selected_status = data["status"]
    query = data["query"]
    show_tickets = data.get("show_tickets", False)

    status_options = ['<option value="">all statuses</option>']
    seen_statuses = [s for s in STATUS_ORDER if status_counts.get(s)]
    seen_statuses += sorted(s for s in status_counts if s not in seen_statuses)
    for current in seen_statuses:
        selected = " selected" if current == selected_status else ""
        status_options.append(
            f'<option value="{html.escape(current)}"{selected}>'
            f'{html.escape(status_label(current))} ({status_counts[current]})</option>'
        )

    cards = "".join(render_shipment_card(s, events_by_shipment.get(s["shipment_key"], [])) for s in shipments)
    if not cards:
        cards = '<p class="empty">No matching shipments.</p>'

    tickets_link = (
        '<a href="/">hide tickets</a>' if show_tickets
        else '<a href="/?tickets=1">show tickets</a>'
    )

    body = f"""
    <main class="shell">
      <div class="toolbar">
        <form method="get">
          <input name="q" value="{html.escape(query)}" placeholder="Search tracking, order, merchant…" />
          <select name="status">{''.join(status_options)}</select>
          <button type="submit">Search</button>
          <a href="/">Reset</a>
          {tickets_link}
        </form>
      </div>
      <div class="shipments">{cards}</div>
    </main>
    """
    return render_document(body)


def render_shipment_card(shipment: dict, events: list[dict]) -> str:
    name = resolve_display_merchant(
        shipment.get("merchant"),
        shipment.get("sender_display_name"),
        shipment.get("sender_domain"),
    )

    tracking = strip_domain_prefix(shipment["tracking_number"])
    order = strip_domain_prefix(shipment["order_number"])

    identifiers: list[str] = []
    if order:
        identifiers.append(f'<span class="id-label">order</span> <span class="id-val">{html.escape(order)}</span>')
    if tracking:
        identifiers.append(f'<span class="id-label">tracking</span> <span class="id-val">{html.escape(tracking)}</span>')
    ids_html = "  ·  ".join(identifiers) if identifiers else ""

    # Events sorted oldest → newest; most recent is current
    sorted_events = sorted(events, key=lambda e: e["event_date"])
    event_rows = "".join(render_event_row(e, is_last=(i == len(sorted_events) - 1))
                         for i, e in enumerate(sorted_events))

    severity = shipment.get("chronology_severity", "ok")
    warn_html = ""
    if severity == "conflict":
        warn_html = '<span class="warn danger">chronology conflict</span>'
    elif severity == "warning":
        warn_html = '<span class="warn warning">timeline warning</span>'

    return f"""
    <article class="card">
      <div class="card-head">
        <span class="who">{html.escape(name)}</span>
        <span class="badge {status_tone(shipment['current_status'])}">{html.escape(status_label(shipment['current_status']))}</span>
      </div>
      {f'<p class="ids">{ids_html}</p>' if ids_html else ''}
      {warn_html}
      <ol class="timeline">{event_rows}</ol>
    </article>
    """


def render_event_row(event: dict, *, is_last: bool) -> str:
    ts = format_dt(event["event_date"])
    label = status_label(event["status"])
    cls = " current" if is_last else ""
    return f'<li class="ev{cls}"><span class="ts">{html.escape(ts)}</span><span class="st">{html.escape(label)}</span></li>'


def render_document(body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Parsli</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --surface: #fffaf4;
      --ink: #241b16;
      --muted: #78685d;
      --line: rgba(36,27,22,.12);
      --good: #2f7d57;
      --urgent: #a26200;
      --danger: #a33a33;
      --done: #68736d;
      --normal: #66584f;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: 14px;
      color: var(--ink);
      background: var(--bg);
      min-height: 100vh;
    }}
    .shell {{ max-width: 860px; margin: 0 auto; padding: 32px 20px 64px; }}

    /* toolbar */
    .toolbar {{ margin-bottom: 24px; }}
    form {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--surface);
      color: var(--ink);
      height: 38px;
      padding: 0 12px;
      font: inherit;
    }}
    input {{ flex: 1 1 220px; }}
    select {{ min-width: 170px; }}
    button {{
      height: 38px; border-radius: 10px; padding: 0 14px;
      background: var(--ink); color: #fff; border: 0;
      font: inherit; cursor: pointer;
    }}
    form a {{ color: var(--muted); font-size: 13px; text-decoration: none; padding: 0 4px; }}
    form a:hover {{ color: var(--ink); }}

    /* cards */
    .shipments {{ display: grid; gap: 12px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px 18px;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 6px;
    }}
    .who {{ font-size: 16px; font-weight: 600; letter-spacing: -.02em; }}
    .ids {{ color: var(--muted); font-size: 12px; font-family: ui-monospace, Menlo, monospace; margin-bottom: 10px; word-break: break-all; }}
    .id-label {{ text-transform: uppercase; font-size: 10px; letter-spacing: .06em; margin-right: 2px; }}
    .id-val {{ color: var(--ink); }}

    /* badge */
    .badge {{
      border-radius: 999px; padding: 5px 11px;
      font-size: 12px; font-weight: 700; white-space: nowrap;
      background: rgba(102,88,79,.10); color: var(--normal);
    }}
    .good  {{ background: rgba(47,125,87,.12);  color: var(--good); }}
    .urgent {{ background: rgba(162,98,0,.12);  color: var(--urgent); }}
    .danger {{ background: rgba(163,58,51,.12); color: var(--danger); }}
    .done  {{ background: rgba(104,115,109,.12); color: var(--done); }}

    /* timeline */
    .timeline {{ list-style: none; border-top: 1px solid var(--line); padding-top: 10px; margin-top: 4px; display: grid; gap: 4px; }}
    .ev {{ display: flex; gap: 16px; font-size: 13px; color: var(--muted); }}
    .ev.current {{ color: var(--ink); font-weight: 600; }}
    .ts {{ font-family: ui-monospace, Menlo, monospace; flex-shrink: 0; min-width: 100px; }}
    .st {{ }}

    /* warnings */
    .warn {{
      display: inline-block; margin-bottom: 8px;
      font-size: 11px; font-weight: 700; border-radius: 999px; padding: 3px 8px;
    }}
    .warn.warning {{ background: rgba(120,104,93,.14); color: var(--normal); }}
    .warn.danger  {{ background: rgba(163,58,51,.12);  color: var(--danger); }}

    .empty {{ color: var(--muted); padding: 24px 0; }}
    .error {{ color: var(--danger); padding: 24px 0; }}

    @media (max-width: 600px) {{
      .card-head {{ flex-direction: column; align-items: start; }}
      input, select, button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
<div class="shell">
{body}
</div>
</body>
</html>
"""


def make_handler(db_path: Path):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            parsed = urlparse(self.path)
            if parsed.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            status = params.get("status", [""])[0].strip()
            show_tickets = params.get("tickets", [""])[0] == "1"
            page = render_page(load_dashboard_data(db_path, query=query, status=status, show_tickets=show_tickets)).encode("utf-8")

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args) -> None:
            # Keep the terminal quiet; the dashboard is intentionally tiny.
            return

    return DashboardHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the minimal Parsli shipment dashboard.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to parsli SQLite database")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.db_path))
    print(f"Parsli dashboard: http://{args.host}:{args.port}")
    print(f"Reading SQLite DB: {args.db_path.resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
