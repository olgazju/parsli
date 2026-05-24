/* ParcelCard — title, badge, meta, mini-tracker, expandable event timeline. */

function ParcelCard({ shipment, expanded, received, onToggle, onReceive, onDelete }) {
  const s = shipment;
  const isActionReq = s.current_status === 'action_required';
  const isPaymentReq = s.current_status === 'payment_required';

  const metaParts = [];
  if (s.display_merchant && s.display_merchant !== 'Unknown') metaParts.push(s.display_merchant);
  if (s.tracking_number) metaParts.push(<span key="tn" className="mono">{s.tracking_number}</span>);
  else if (s.order_number) metaParts.push(<span key="on" className="mono">#{s.order_number}</span>);
  metaParts.push(`${s.events_count} event${s.events_count !== 1 ? 's' : ''}`);
  // join with " · "
  const meta = [];
  metaParts.forEach((p, i) => {
    if (i > 0) meta.push(<span key={`sep-${i}`}> · </span>);
    meta.push(<React.Fragment key={`p-${i}`}>{p}</React.Fragment>);
  });

  return (
    <div
      className={`parcel-card${expanded ? ' expanded' : ''}${received ? ' received-card' : ''}`}
      style={{ borderLeftColor: STATUS_BORDER[s.current_status] || 'var(--c-beige)' }}
    >
      <div className="card-main" onClick={onToggle}>
        <div className="card-row1">
          <span className="card-title">{s.display_title}</span>
          <div className="card-right">
            <Badge status={s.current_status} label={s.current_status_label} />
            <button className="expand-btn" aria-label="Toggle timeline">▼</button>
          </div>
        </div>

        <div className="card-row2">
          <span className="card-meta">{meta}</span>
          <span className="card-age">{s.last_status_date} ago</span>
        </div>

        {isActionReq && <ActionBanner kind="action_required" />}
        {isPaymentReq && <ActionBanner kind="payment_required" />}

        <MiniTracker status={s.current_status} />
      </div>

      <div className="card-footer">
        <span></span>
        <div className="card-links">
          <button
            className={`link-btn${received ? ' received-active' : ''}`}
            onClick={(e) => { e.stopPropagation(); onReceive(); }}
          >
            {received ? '✓ Received' : 'Mark received'}
          </button>
          <button
            className="link-btn delete-btn"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
          >
            Delete
          </button>
        </div>
      </div>

      <div className="card-timeline">
        {expanded && <Timeline events={s.events} />}
      </div>
    </div>
  );
}

function Timeline({ events }) {
  if (!events || events.length === 0) {
    return <div className="timeline-inner" style={{ padding: '16px', color: 'var(--fg-2)', fontSize: 12 }}>No events recorded.</div>;
  }
  const lastIdx = events.length - 1;
  return (
    <div className="timeline-inner">
      {events.map((ev, i) => {
        const isLast = i === lastIdx;
        const isCurrent = isLast;
        const isSide = ['action_required', 'payment_required', 'delayed_or_problem'].includes(ev.status);
        let dotClass = 'past';
        if (isCurrent) dotClass = 'current';
        if (isSide) dotClass = `side${ev.status === 'payment_required' ? ' payment' : ''}`;
        const lineClass = isCurrent ? '' : 'past';
        return (
          <div key={i} className={`tl-event${isCurrent ? ' current' : ''}`}>
            <div className="tl-spine">
              <div className={`tl-dot ${dotClass}`}></div>
              {!isLast && <div className={`tl-line ${lineClass}`}></div>}
            </div>
            <div className="tl-body">
              <div className="tl-header">
                <span className="tl-status">{ev.status_label}</span>
                <span className="tl-date">{ev.event_date}</span>
              </div>
              {ev.evidence && <div className="tl-evidence">{ev.evidence}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

Object.assign(window, { ParcelCard, Timeline });
