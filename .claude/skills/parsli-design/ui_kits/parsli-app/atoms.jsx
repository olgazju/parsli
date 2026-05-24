/* Small reusable atoms: Badge, Button, MiniTracker, Spinner, Toast, ActionBanner */

const STATUS_BADGE = {
  delivered:                        'green',
  shipped:                          'blue',
  received_by_carrier:              'blue',
  in_transit:                       'blue',
  arrived_in_destination_country:   'blue',
  customs_pending:                  'yellow',
  customs_released:                 'yellow',
  handed_to_local_carrier:          'blue',
  out_for_delivery:                 'yellow',
  ready_for_pickup:                 'yellow',
  action_required:                  'red',
  payment_required:                 'red',
  delayed_or_problem:               'red',
  order_confirmed:                  'gray',
  unknown:                          'gray',
};

const STATUS_BORDER = {
  delivered:                        'var(--c-olive)',
  shipped:                          'var(--c-sky)',
  in_transit:                       'var(--c-sky)',
  arrived_in_destination_country:   'var(--c-sky)',
  handed_to_local_carrier:          'var(--c-sky)',
  customs_pending:                  'var(--c-yellow)',
  customs_released:                 'var(--c-yellow)',
  out_for_delivery:                 'var(--c-yellow)',
  ready_for_pickup:                 'var(--c-yellow)',
  action_required:                  'var(--c-jacket-red)',
  payment_required:                 'var(--c-jacket-red)',
  delayed_or_problem:               'var(--c-jacket-red)',
  order_confirmed:                  'var(--c-beige)',
  unknown:                          'var(--c-beige)',
};

// Milestone: 0 Ordered, 1 Shipped, 2 Arriving, 3 Delivered
const MILESTONE = {
  order_confirmed: 0,
  shipped: 1, received_by_carrier: 1, in_transit: 1,
  arrived_in_destination_country: 1, customs_pending: 1,
  customs_released: 1, handed_to_local_carrier: 1,
  out_for_delivery: 2, ready_for_pickup: 2,
  delivered: 3,
};
const MILESTONE_LABELS = ['Ordered', 'Shipped', 'Arriving', 'Delivered'];

function Badge({ status, label }) {
  const tone = STATUS_BADGE[status] || 'gray';
  return <span className={`badge badge-${tone}`}>{label}</span>;
}

function Button({ kind = 'primary', size = 'md', children, ...rest }) {
  const cls = `btn btn-${kind}${size === 'sm' ? ' btn-sm' : ''}`;
  return <button className={cls} {...rest}>{children}</button>;
}

function Spinner({ lg }) {
  return <div className={`spinner${lg ? ' lg' : ''}`}></div>;
}

function MiniTracker({ status }) {
  const cur = MILESTONE[status] ?? -1;
  if (cur < 0) return null;
  return (
    <>
      <div className="mini-tracker">
        {MILESTONE_LABELS.map((_, i) => {
          const dotClass = i < cur ? 'past' : i === cur ? 'current' : 'future';
          const lineClass = i < cur ? 'past' : 'future';
          return (
            <React.Fragment key={i}>
              <div className={`track-dot ${dotClass}`}></div>
              {i < MILESTONE_LABELS.length - 1 && <div className={`track-line ${lineClass}`}></div>}
            </React.Fragment>
          );
        })}
      </div>
      <div className="track-labels">
        {MILESTONE_LABELS.map(l => <span key={l}>{l}</span>)}
      </div>
    </>
  );
}

function ActionBanner({ kind }) {
  if (kind === 'action_required') {
    return (
      <div className="action-banner">
        <div className="action-banner-dot"></div>
        <div className="action-banner-text">Action required — expand to see details.</div>
      </div>
    );
  }
  if (kind === 'payment_required') {
    return (
      <div className="action-banner payment">
        <div className="action-banner-dot"></div>
        <div className="action-banner-text">Payment required — expand to see details.</div>
      </div>
    );
  }
  return null;
}

function Toast({ message, tone }) {
  if (!message) return null;
  return <div className={`toast show${tone ? ' ' + tone : ''}`}>{message}</div>;
}

Object.assign(window, {
  Badge, Button, Spinner, MiniTracker, ActionBanner, Toast,
  STATUS_BADGE, STATUS_BORDER, MILESTONE, MILESTONE_LABELS,
});
