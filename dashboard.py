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

_SENDER_DISPLAY_RE = re.compile(r'^"?([^"<]+?)"?\s*<[^>]+>$')

# Curated names for merchant domains. Domains not listed here fall back to
# the sender display name, then to the raw domain.
_MERCHANT_NAMES: dict[str, str] = {
    "amazon.com": "Amazon",
    "asos.com": "ASOS",
    "nextdirect.com": "Next Direct",
    "hoodies.co.il": "Hoodies",
    "manovino.co.il": "Manovino",
    "caretobeauty.com": "Care to Beauty",
    "saasplaybook.com": "SaaS Playbook",
    "accessoticketing.com": "Accesso Ticketing",
}


def parse_sender_display_name(sender: str | None) -> str | None:
    """Extract display name from 'Name <email>' format, or None if not present."""
    if not sender:
        return None
    m = _SENDER_DISPLAY_RE.match(sender.strip())
    if not m:
        return None
    name = m.group(1).strip().strip('"')
    return name or None


def merchant_display_name(domain: str | None, sender_display: str | None) -> str:
    """Return the best human-readable merchant name."""
    if domain and domain in _MERCHANT_NAMES:
        return _MERCHANT_NAMES[domain]
    if sender_display:
        return sender_display
    return domain or "Unknown"


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
    "order_confirmed": "Order confirmed",
    "shipped": "Shipped",
    "received_by_carrier": "Received by carrier",
    "in_transit": "In transit",
    "arrived_in_destination_country": "Arrived in country",
    "customs_pending": "Customs pending",
    "customs_released": "Customs released",
    "handed_to_local_carrier": "With local carrier",
    "ready_for_pickup": "Ready for pickup",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "payment_required": "Payment required",
    "action_required": "Action required",
    "delayed_or_problem": "Delayed / problem",
    "unknown": "Unknown",
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
        return dt.strftime("%Y-%m-%d %H:%M")
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
                    COALESCE(s.merchant,
                        (SELECT se.sender_domain FROM shipment_events se
                         WHERE se.canonical_shipment_id = s.canonical_shipment_id
                         ORDER BY se.event_date ASC LIMIT 1)
                    ) AS sender_domain,
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
        body = f"""
        <main class="shell narrow">
          <section class="empty">
            <h1>Parsli dashboard</h1>
            <p>{html.escape(error)}</p>
          </section>
        </main>
        """
        return render_document(body)

    shipments = data["shipments"]
    status_counts: Counter[str] = data["status_counts"]
    events_by_shipment = data["events_by_shipment"]
    selected_status = data["status"]
    query = data["query"]
    show_tickets = data.get("show_tickets", False)

    status_options = ['<option value="">All statuses</option>']
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
        cards = """
        <section class="empty compact">
          <h2>No matching shipments</h2>
          <p>Try clearing the search or status filter.</p>
        </section>
        """

    status_chips = "".join(
        render_status_chip(status, count)
        for status, count in sorted(status_counts.items(), key=lambda item: (-item[1], status_label(item[0])))
    )

    body = f"""
    <main class="shell">
      <header class="hero">
        <div>
          <p class="eyebrow">Parsli / shipment timelines</p>
          <h1>Shipment dashboard</h1>
          <p class="subtle">Reading directly from <code>{html.escape(data['db_path'])}</code></p>
        </div>
      </header>

      <section class="stats">
        {render_stat('Shipments', data['total_shipments'])}
        {render_stat('Active', data['active_shipments'])}
        {render_stat('Need attention', data['needs_attention'])}
        {render_stat('Events', data['total_events'])}
      </section>

      <section class="toolbar">
        <form method="get">
          <input name="q" value="{html.escape(query)}" placeholder="Search tracking, order, domain…" />
          <select name="status">{''.join(status_options)}</select>
          <button type="submit">Filter</button>
          <a href="/">Reset</a>
          {'<a href="/?tickets=1" class="toggle-link">Show tickets</a>' if not show_tickets else '<a href="/" class="toggle-link active">Hide tickets</a>'}
        </form>
      </section>

      <section class="chips">{status_chips}</section>

      <section class="shipments">
        {cards}
      </section>
    </main>
    """
    return render_document(body)


def render_stat(label: str, value: int) -> str:
    return f"""
    <article class="stat">
      <span>{html.escape(label)}</span>
      <strong>{value}</strong>
    </article>
    """


def render_status_chip(status: str, count: int) -> str:
    return (
        f'<span class="chip {status_tone(status)}">'
        f'{html.escape(status_label(status))} <b>{count}</b>'
        '</span>'
    )


def render_shipment_card(shipment: dict, events: list[dict]) -> str:
    raw_identifier = shipment["tracking_number"] or shipment["order_number"] or shipment["shipment_key"]
    identifier = strip_domain_prefix(raw_identifier) or raw_identifier
    identifier_label = "Tracking" if shipment["tracking_number"] else "Order" if shipment["order_number"] else "Shipment"
    key = shipment["shipment_key"]

    domain = shipment["sender_domain"] or ""
    name = merchant_display_name(domain or None, None)
    # Show domain below the name only when it adds information
    domain_html = (
        f'<p class="domain">{html.escape(domain)}</p>'
        if domain and domain not in name
        else ""
    )

    event_items = "".join(render_event_item(event) for event in events)
    evidence = shipment["current_status_evidence"] or "—"
    aliases  = shipment.get("aliases") or ""
    alias_html = (
        f'<p class="aliases">{html.escape(aliases)}</p>' if aliases else ""
    )

    flag_chips: list[str] = []
    if shipment.get("merge_confidence") == "medium":
        flag_chips.append('<span class="flag medium">medium-confidence merge</span>')
    severity = shipment.get("chronology_severity")
    if severity == "conflict":
        flag_chips.append('<span class="flag danger">chronology conflict</span>')
    elif severity == "warning":
        flag_chips.append('<span class="flag warning">timeline warning</span>')
    flags_html = (
        f'<div class="flags">{"".join(flag_chips)}</div>' if flag_chips else ""
    )

    return f"""
    <article class="shipment-card">
      <div class="shipment-main">
        <div>
          <h2>{html.escape(name)}</h2>
          <p class="identifier"><span class="meta">{html.escape(identifier_label)}</span> {html.escape(identifier)}</p>
          {domain_html}
        </div>
        <span class="badge {status_tone(shipment['current_status'])}">
          {html.escape(status_label(shipment['current_status']))}
        </span>
      </div>

      {alias_html}
      {flags_html}

      <div class="facts">
        <div><span>Last update</span><strong>{html.escape(format_dt(shipment['last_seen_at']))}</strong></div>
        <div><span>First seen</span><strong>{html.escape(format_dt(shipment['first_seen_at']))}</strong></div>
        <div><span>Events</span><strong>{shipment['event_count']}</strong></div>
      </div>

      <p class="evidence">{html.escape(evidence)}</p>

      <details>
        <summary>Timeline ({len(events)} event{'s' if len(events) != 1 else ''})</summary>
        <ol>{event_items}</ol>
      </details>
      <p class="key">{html.escape(key)}</p>
    </article>
    """


def render_event_item(event: dict) -> str:
    evidence = event["status_evidence"] or "—"
    conf_raw = event["status_confidence"]
    confidence = f"{conf_raw:.0%}" if isinstance(conf_raw, float) else (str(conf_raw) if conf_raw else "—")
    return f"""
    <li>
      <div>
        <strong>{html.escape(status_label(event['status']))}</strong>
        <span>{html.escape(format_dt(event['event_date']))}</span>
      </div>
      <p>{html.escape(evidence)}</p>
      <small>{html.escape(event['sender_domain'] or 'unknown sender')} · confidence {html.escape(confidence)}</small>
    </li>
    """


def render_document(body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Parsli shipment dashboard</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --surface: #fffaf4;
      --surface-2: #f7efe5;
      --ink: #241b16;
      --muted: #78685d;
      --line: rgba(36, 27, 22, .12);
      --accent: #8a5a44;
      --normal: #66584f;
      --good: #2f7d57;
      --urgent: #a26200;
      --danger: #a33a33;
      --done: #68736d;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(138, 90, 68, .14), transparent 28rem),
        linear-gradient(180deg, #fbf7f1 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    .shell {{ max-width: 1100px; margin: 0 auto; padding: 42px 24px 64px; }}
    .shell.narrow {{ max-width: 720px; }}
    .hero {{ display: flex; justify-content: space-between; align-items: end; gap: 20px; margin-bottom: 24px; }}
    .eyebrow {{ margin: 0 0 8px; color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(28px, 4vw, 40px); letter-spacing: -.04em; }}
    .subtle {{ margin: 10px 0 0; color: var(--muted); font-size: 14px; }}
    code {{ background: rgba(36,27,22,.06); border-radius: 8px; padding: 3px 7px; }}

    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }}
    .stat {{ background: rgba(255, 250, 244, .8); border: 1px solid var(--line); border-radius: 20px; padding: 18px; box-shadow: 0 10px 28px rgba(64, 43, 30, .06); }}
    .stat span {{ display: block; color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
    .stat strong {{ font-size: 28px; letter-spacing: -.03em; }}

    .toolbar {{ margin: 18px 0 14px; }}
    form {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 250, 244, .95);
      color: var(--ink);
      min-height: 44px;
      padding: 0 14px;
      font: inherit;
    }}
    input {{ flex: 1 1 280px; }}
    select {{ min-width: 190px; }}
    button, form a {{
      min-height: 44px;
      border-radius: 14px;
      padding: 0 16px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 0;
      text-decoration: none;
      font: inherit;
      cursor: pointer;
    }}
    button {{ background: var(--ink); color: white; }}
    form a {{ color: var(--ink); background: rgba(36,27,22,.07); }}

    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }}
    .chip, .badge {{
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: rgba(102, 88, 79, .10);
      color: var(--normal);
    }}
    .chip {{ padding: 7px 11px; font-size: 13px; }}
    .badge {{ padding: 8px 12px; font-size: 13px; font-weight: 700; white-space: nowrap; }}
    .good {{ background: rgba(47,125,87,.12); color: var(--good); }}
    .urgent {{ background: rgba(162,98,0,.12); color: var(--urgent); }}
    .danger {{ background: rgba(163,58,51,.12); color: var(--danger); }}
    .done {{ background: rgba(104,115,109,.12); color: var(--done); }}
    .muted {{ background: rgba(120,104,93,.10); color: var(--muted); }}

    .shipments {{ display: grid; gap: 16px; }}
    .shipment-card {{
      background: rgba(255, 250, 244, .92);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      box-shadow: 0 14px 34px rgba(64, 43, 30, .07);
    }}
    .shipment-main {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; }}
    h2 {{ margin: 0 0 6px; font-size: 22px; letter-spacing: -.03em; word-break: break-word; }}
    .identifier {{ margin: 0; font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; color: var(--text); }}
    .identifier .meta {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; margin-right: 4px; font-family: inherit; }}
    .meta {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .domain {{ color: var(--muted); font-size: 12px; margin: 3px 0 0; }}
    .toggle-link {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    .toggle-link:hover, .toggle-link.active {{ color: var(--accent); }}
    .facts {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0 14px; }}
    .facts div {{ background: var(--surface-2); border-radius: 16px; padding: 12px; }}
    .facts span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }}
    .facts strong {{ font-size: 14px; }}
    .evidence {{ margin: 0 0 14px; line-height: 1.5; }}
    .aliases {{ margin: 10px 0 0; color: var(--muted); font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }}
    .flags {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0; }}
    .flag {{ font-size: 11px; padding: 4px 9px; border-radius: 999px; font-weight: 700; letter-spacing: .02em; }}
    .flag.medium {{ background: rgba(162,98,0,.12); color: var(--urgent); }}
    .flag.warning {{ background: rgba(120,104,93,.14); color: var(--normal); }}
    .flag.danger {{ background: rgba(163,58,51,.12); color: var(--danger); }}
    details {{ border-top: 1px solid var(--line); padding-top: 14px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; }}
    ol {{ margin: 14px 0 0; padding-left: 20px; display: grid; gap: 12px; }}
    li div {{ display: flex; justify-content: space-between; gap: 12px; }}
    li span, li small {{ color: var(--muted); }}
    li p {{ margin: 4px 0; }}
    .key {{ margin: 14px 0 0; color: var(--muted); font-size: 12px; word-break: break-all; }}
    .empty {{ background: rgba(255,250,244,.9); border: 1px solid var(--line); border-radius: 24px; padding: 28px; }}
    .empty.compact h2, .empty h1 {{ margin-top: 0; }}

    @media (max-width: 760px) {{
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .facts {{ grid-template-columns: 1fr; }}
      .shipment-main {{ flex-direction: column; }}
      input, select, button, form a {{ width: 100%; }}
    }}
  </style>
</head>
<body>
{body}
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
