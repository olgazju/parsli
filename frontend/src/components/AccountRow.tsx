import type { AccountInfo } from "@/api/types";
import { Button, Spinner } from "@/components/atoms";
import { formatRelativeAge } from "@/hooks/useRelativeTime";

interface AccountRowProps {
  account: AccountInfo;
  syncing: boolean;
  onSync: () => void;
  onRemove: () => void;
}

export function AccountRow({
  account,
  syncing,
  onSync,
  onRemove,
}: AccountRowProps) {
  const a = account;
  const initial = a.initial_sync_completed;
  const isInitial = !initial;

  let syncLabel: string;
  if (syncing) {
    syncLabel = isInitial ? "Initial sync in progress…" : "Syncing…";
  } else if (initial) {
    syncLabel = "Initial sync done";
  } else {
    syncLabel = "Needs initial sync";
  }
  const syncClass = syncing ? "syncing" : initial ? "complete" : "pending";
  const last = a.last_sync_at ? `${formatRelativeAge(a.last_sync_at)} ago` : null;

  const buttonLabel = isInitial ? "Run initial sync" : "↻ Sync";

  return (
    <div className="account-row">
      <div className="account-avatar">{a.account_id.slice(0, 1)}</div>
      <div className="account-info">
        <div className="account-email">{a.account_id}</div>
        <div className="account-meta">
          <span className={`sync-indicator ${syncClass}`}>{syncLabel}</span>
          {last && <span> · Last: {last}</span>}
        </div>
        {syncing && isInitial && (
          <div className="account-progress">
            Fetching {a.lookback_days} days of email — this can take a few
            minutes.
          </div>
        )}
      </div>
      <div className="account-actions">
        <Button kind="secondary" size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? (
            <>
              <Spinner /> {isInitial ? "Initial sync…" : "Syncing"}
            </>
          ) : (
            buttonLabel
          )}
        </Button>
        <Button kind="danger" size="sm" onClick={onRemove} disabled={syncing}>
          Remove
        </Button>
      </div>
    </div>
  );
}
