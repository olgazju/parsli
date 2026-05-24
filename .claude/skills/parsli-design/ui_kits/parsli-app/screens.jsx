/* Screens — Parcels, Sources (was Comms Array), Preferences. */

/* ── ParcelsScreen ──────────────────────────────────────────────── */
function ParcelsScreen({ shipments, stats, expandedIds, receivedIds, onExpand, onReceive, onDelete, searchQuery, onSearch, filter, onFilter }) {
  const filtered = applyFilters(shipments, searchQuery, filter, receivedIds);

  return (
    <>
      <div className="screen-header">
        <div className="screen-title">Parcels</div>
        <div className="screen-sub">All tracked shipments · {shipments.length} total</div>
      </div>

      <div className="stat-grid">
        <StatCard label="Active"        value={stats.active_count}        tone="blue" />
        <StatCard label="Delivered"     value={stats.delivered_count}     tone="green" />
        <StatCard label="Order only"    value={stats.order_only_count}    tone="gray" />
        <StatCard label="Needs review"  value={stats.needs_review_count}  tone={stats.needs_review_count > 0 ? 'red' : 'gray'} />
      </div>

      <div className="controls-bar">
        <div className="search-wrap">
          <svg className="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="search-input"
            type="text"
            placeholder="Search merchant, carrier, tracking…"
            value={searchQuery}
            onChange={e => onSearch(e.target.value)}
          />
        </div>
        <div className="filter-pills">
          {['all','active','action','delivered'].map(f => (
            <button
              key={f}
              className={`filter-pill${filter === f ? ' active' : ''}`}
              onClick={() => onFilter(f)}
            >
              {filterLabel(f)}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0
        ? (
          searchQuery || filter !== 'all'
            ? <div className="no-results">No parcels match your search. Try broadening the filter.</div>
            : (
              <div className="empty-state">
                <div className="empty-glyph">📭</div>
                <div className="empty-title">No active parcels</div>
                <div className="empty-sub">Connect a source to start scanning for parcels, or sit back and enjoy the quiet.</div>
              </div>
            )
          )
        : (
          <div className="parcel-list">
            {filtered.map(s => (
              <ParcelCard
                key={s.shipment_id}
                shipment={s}
                expanded={expandedIds.has(s.shipment_id)}
                received={receivedIds.has(s.shipment_id)}
                onToggle={() => onExpand(s.shipment_id)}
                onReceive={() => onReceive(s.shipment_id)}
                onDelete={() => onDelete(s.shipment_id)}
              />
            ))}
          </div>
        )
      }
    </>
  );
}

function filterLabel(f) {
  return { all: 'All', active: 'Active', action: 'Needs action', delivered: 'Delivered' }[f] || f;
}

function applyFilters(shipments, q, filter, receivedIds) {
  let list = shipments;
  if (q) {
    const lc = q.toLowerCase();
    list = list.filter(s =>
      (s.display_title || '').toLowerCase().includes(lc) ||
      (s.display_merchant || '').toLowerCase().includes(lc) ||
      (s.tracking_number || '').toLowerCase().includes(lc) ||
      (s.order_number || '').toLowerCase().includes(lc)
    );
  }
  if (filter === 'active') {
    list = list.filter(s => s.current_status !== 'delivered');
  } else if (filter === 'action') {
    list = list.filter(s =>
      s.current_status === 'action_required' ||
      s.current_status === 'payment_required' ||
      s.needs_review
    );
  } else if (filter === 'delivered') {
    list = list.filter(s => s.current_status === 'delivered' || receivedIds.has(s.shipment_id));
  }
  return list;
}

/* ── SourcesScreen ──────────────────────────────────────────────── */
function SourcesScreen({ accounts, syncingIds, onConnect, onSync, onRemove }) {
  return (
    <>
      <div className="screen-header">
        <div className="screen-title">Sources</div>
        <div className="screen-sub">Where parsli reads from — all runs locally on your device</div>
      </div>

      <PrivacyBanner />

      <div className="section-box">
        <div className="section-box-header">
          <div className="section-box-title">Connected accounts</div>
          <Button kind="primary" size="sm" onClick={onConnect}>+ Add account</Button>
        </div>
        {accounts.length === 0
          ? <div className="account-row" style={{ color: 'var(--fg-2)', fontSize: 13 }}>No accounts connected yet.</div>
          : accounts.map(a => (
              <AccountRow
                key={a.account_id}
                account={a}
                syncing={syncingIds.has(a.account_id)}
                onSync={() => onSync(a.account_id)}
                onRemove={() => onRemove(a.account_id)}
              />
            ))
        }
      </div>
    </>
  );
}

/* ── PreferencesScreen ──────────────────────────────────────────── */
function PreferencesScreen({
  languages, onToggleLanguage,
  allowlist, blocklist,
  onAddAllow, onRemoveAllow,
  onAddBlock, onRemoveBlock,
}) {
  return (
    <>
      <div className="screen-header">
        <div className="screen-title">Preferences</div>
        <div className="screen-sub">App settings, languages, sender rules</div>
      </div>

      <div className="pref-section">
        <div className="section-box-header">
          <div className="section-box-title">Languages</div>
        </div>
        <div className="pref-row" style={{ display: 'block' }}>
          <div className="pref-label" style={{ marginBottom: 4 }}>Languages parsli reads</div>
          <div className="pref-meta" style={{ marginBottom: 12 }}>
            Email subjects and bodies in these languages will be parsed.
            English and Hebrew are supported today.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {languages.available.map(l => {
              const on = languages.enabled.includes(l.code);
              return (
                <button
                  key={l.code}
                  className={`lang-chip${on ? ' on' : ''}`}
                  onClick={() => onToggleLanguage(l.code)}
                >
                  <span className="lang-check">{on ? '✓' : ''}</span>
                  <span>{l.name}</span>
                  <span className="lang-native">{l.native}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <SenderList
        title="Sender allowlist"
        sub="Always treat email from these domains as parcel-relevant."
        kind="allow"
        list={allowlist}
        onAdd={onAddAllow}
        onRemove={onRemoveAllow}
      />

      <SenderList
        title="Sender blocklist"
        sub="Never process email from these domains. Marketing senders go here."
        kind="block"
        list={blocklist}
        onAdd={onAddBlock}
        onRemove={onRemoveBlock}
      />

      <div className="pref-section">
        <div className="section-box-header">
          <div className="section-box-title">Sync schedule</div>
        </div>
        <div className="pref-row">
          <div>
            <div className="pref-label">Auto-sync every 30 minutes</div>
            <div className="pref-meta">Parsli checks for new emails in the background.</div>
          </div>
        </div>
        <div className="pref-row">
          <div>
            <div className="pref-label">Look back 60 days on first sync</div>
            <div className="pref-meta">Controls how much email history parsli ingests for a new source.</div>
          </div>
        </div>
      </div>
    </>
  );
}

function SenderList({ title, sub, kind, list, onAdd, onRemove }) {
  const [val, setVal] = React.useState('');
  const submit = (e) => {
    e.preventDefault();
    const v = val.trim().toLowerCase();
    if (!v) return;
    if (!/^[a-z0-9.-]+\.[a-z]{2,}$/.test(v)) return;
    onAdd(v);
    setVal('');
  };
  return (
    <div className="pref-section">
      <div className="section-box-header">
        <div className="section-box-title">{title}</div>
      </div>
      <div className="pref-row" style={{ display: 'block' }}>
        <div className="pref-meta" style={{ marginBottom: 10 }}>{sub}</div>
        <form className="sender-add" onSubmit={submit}>
          <input
            className="sender-input"
            type="text"
            placeholder="domain.com"
            value={val}
            onChange={e => setVal(e.target.value)}
          />
          <Button kind={kind === 'allow' ? 'primary' : 'danger'} size="sm" onClick={submit}>
            Add
          </Button>
        </form>
        <div className="sender-tags">
          {list.length === 0
            ? <span className="sender-empty">None yet.</span>
            : list.map(d => (
                <div key={d} className={`sender-tag ${kind}`}>
                  <span>{d}</span>
                  <button className="sender-remove" onClick={() => onRemove(d)} aria-label={`Remove ${d}`}>×</button>
                </div>
              ))
          }
        </div>
      </div>
    </div>
  );
}

/* ── DiagnosticsScreen ──────────────────────────────────────────── */
function DiagnosticsScreen({ obs }) {
  const methodTotal = obs.method_breakdown.reduce((sum, m) => sum + m.count, 0) || 1;

  return (
    <>
      <div className="screen-header">
        <div className="screen-title">Diagnostics</div>
        <div className="screen-sub">Pipeline observability — every stage, locally</div>
      </div>

      <div className="diag-grid">
        {obs.pipeline.map(p => (
          <div key={p.stage} className="diag-card">
            <div className="diag-label">{p.stage}</div>
            <div className="diag-num">{p.value.toLocaleString()}</div>
            <div className="diag-sub">{p.sub}</div>
          </div>
        ))}
      </div>

      <div className="section-box">
        <div className="section-box-header">
          <div className="section-box-title">Classification method</div>
          <div style={{ fontSize: 11, color: 'var(--fg-2)' }}>where decisions come from</div>
        </div>
        <div style={{ padding: '14px 18px 18px' }}>
          {obs.method_breakdown.map(m => {
            const pct = (m.count / methodTotal) * 100;
            return (
              <div key={m.method} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-1)', fontWeight: 700 }}>{m.method}</span>
                  <span style={{ color: 'var(--fg-2)' }}>
                    {m.count.toLocaleString()} · {m.ms_avg > 0 ? `${m.ms_avg}ms avg` : '—'}
                  </span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${pct}%`, background: methodColor(m.method) }}></div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="section-box">
        <div className="section-box-header">
          <div className="section-box-title">Recent processing</div>
          <div style={{ fontSize: 11, color: 'var(--fg-2)' }}>last 30 emails</div>
        </div>
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
            {obs.recent_processing.map(r => (
              <tr key={r.id}>
                <td className="mono">{r.id.slice(0,12)}…</td>
                <td>
                  {r.relevant
                    ? <span className="dot-row"><span className="dot dot-green"></span>relevant</span>
                    : <span className="dot-row"><span className="dot dot-gray"></span>{r.reason || 'ignored'}</span>}
                </td>
                <td className="mono">{r.method}</td>
                <td className="mono">{r.ms ? `${r.ms}ms` : '—'}</td>
                <td>
                  {r.status
                    ? <Badge status={r.status} label={r.status.replace(/_/g,' ')} />
                    : <span style={{ color: 'var(--fg-3)' }}>—</span>}
                  {r.review && <span className="review-flag" title="Needs review">⚠</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-box">
        <div className="section-box-header">
          <div className="section-box-title">Recent query runs</div>
        </div>
        {obs.query_batches.map(b => (
          <div key={b.id} className="query-batch">
            <div className="batch-id">batch {b.id} · {b.started_at_minutes_ago}m ago</div>
            {b.runs.map(r => (
              <div key={r.name} className="query-row">
                <span className="query-name">{r.name}</span>
                <span className="query-count">{r.count} results</span>
                <span className="query-ms">{r.ms}ms</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function methodColor(m) {
  if (m === 'rule_match')       return 'var(--c-olive)';
  if (m === 'rule_relevant')    return 'var(--c-sage)';
  if (m === 'model_classified') return 'var(--c-sky)';
  if (m === 'model_skipped')    return 'var(--c-beige)';
  return 'var(--c-metal)';
}

Object.assign(window, { ParcelsScreen, SourcesScreen, PreferencesScreen, DiagnosticsScreen, SenderList });
