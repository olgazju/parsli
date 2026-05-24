/* AccountRow — connected Gmail account with sync state + actions. */

function AccountRow({ account, syncing, onSync, onRemove }) {
  const a = account;
  const initial = a.initial_sync_completed;
  const syncLabel = syncing ? 'Syncing…' : initial ? 'Initial sync done' : 'Needs initial sync';
  const syncClass = syncing ? 'syncing' : initial ? 'complete' : 'pending';
  const last = a.last_sync_at_minutes != null
    ? (a.last_sync_at_minutes < 60
        ? `${a.last_sync_at_minutes}m ago`
        : `${Math.round(a.last_sync_at_minutes / 60)}h ago`)
    : null;

  return (
    <div className="account-row">
      <div className="account-avatar">{a.account_id[0]}</div>
      <div className="account-info">
        <div className="account-email">{a.account_id}</div>
        <div className="account-meta">
          <span className={`sync-indicator ${syncClass}`}>{syncLabel}</span>
          {last && <span> · Last: {last}</span>}
        </div>
      </div>
      <div className="account-actions">
        <Button kind="secondary" size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? <><Spinner /> Syncing</> : '↻ Sync'}
        </Button>
        <Button kind="danger" size="sm" onClick={onRemove}>Remove</Button>
      </div>
    </div>
  );
}

Object.assign(window, { AccountRow });
