import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/api/client";
import { AccountRow } from "@/components/AccountRow";
import { Button, ErrorState, FullLoading } from "@/components/atoms";
import { PrivacyBanner } from "@/components/PrivacyBanner";
import { useToast } from "@/components/Toast";

export default function SourcesScreen() {
  const qc = useQueryClient();
  const { show } = useToast();

  const status = useQuery({
    queryKey: ["status"],
    queryFn: api.getStatus,
  });
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: api.listAccounts,
  });

  const [syncingIds, setSyncingIds] = useState<Set<string>>(() => new Set());
  const authWindowRef = useRef<Window | null>(null);

  const connectMutation = useMutation({
    mutationFn: () => api.connectAccount(),
    onSuccess: (resp) => {
      show("Waiting for Google sign-in — check the window that just opened.");
      authWindowRef.current = window.open(
        resp.auth_url,
        "parsli-auth",
        "width=520,height=640",
      );
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof ApiError && err.status === 503
          ? "credentials.json is not configured — place it in the app directory to connect a Gmail account."
          : err instanceof ApiError
            ? err.message
            : "Couldn't open the sign-in flow.";
      show(msg, "error");
    },
  });

  const syncMutation = useMutation({
    mutationFn: ({ id, initial }: { id: string; initial: boolean }) =>
      initial ? api.initialSync(id) : api.incrementalSync(id),
    onMutate: ({ id, initial }) => {
      setSyncingIds((prev) => new Set(prev).add(id));
      if (initial) {
        show("Initial sync started — this can take a few minutes.");
      }
    },
    onSuccess: (result, { initial }) => {
      const fetched = result.total_fetched ?? result.new_ingested;
      show(
        initial
          ? `Initial sync complete — ${fetched} fetched, ${result.new_ingested} new, ${result.processed} processed.`
          : `Sync complete — ${result.new_ingested} new, ${result.processed} processed.`,
        "success",
      );
      void qc.invalidateQueries({ queryKey: ["accounts"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Sync failed.";
      show(msg, "error");
    },
    onSettled: (_d, _e, { id }) => {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.removeAccount(id),
    onSuccess: () => {
      show("Account removed.", "success");
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : "Couldn't remove account.";
      show(msg, "error");
    },
  });

  // Listen for the OAuth callback popup talking back via postMessage.
  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      const data = ev.data as { type?: string; message?: string } | undefined;
      if (!data || typeof data.type !== "string") return;
      if (data.type === "parsli_auth_success") {
        show("Account connected. Starting initial sync…", "success");
        void qc.invalidateQueries({ queryKey: ["accounts"] });
        // Kick an initial sync on the freshly-added account; we don't know
        // its email here, so re-fetch and rely on the user to press sync.
      } else if (data.type === "parsli_auth_error") {
        show(data.message ?? "Sign-in failed.", "error");
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [qc, show]);

  const credsMissing = status.data?.credentials_configured === false;

  if (accounts.isLoading) {
    return (
      <>
        <Header />
        <FullLoading />
      </>
    );
  }

  if (accounts.isError) {
    const msg =
      accounts.error instanceof ApiError
        ? accounts.error.message
        : "Couldn't load connected accounts.";
    return (
      <>
        <Header />
        <ErrorState
          message={msg}
          onRetry={() => void accounts.refetch()}
        />
      </>
    );
  }

  const list = accounts.data ?? [];

  return (
    <>
      <Header />
      <PrivacyBanner />

      <div className="section-box">
        <div className="section-box-header">
          <div className="section-box-title">Connected accounts</div>
          <Button
            kind="primary"
            size="sm"
            onClick={() => connectMutation.mutate()}
            disabled={credsMissing || connectMutation.isPending}
          >
            + Add account
          </Button>
        </div>
        {credsMissing && (
          <div className="account-empty">
            credentials.json is not configured — place it in the app directory
            to connect a Gmail account.
          </div>
        )}
        {!credsMissing && list.length === 0 && (
          <div className="account-empty">No accounts connected yet.</div>
        )}
        {list.map((a) => (
          <AccountRow
            key={a.account_id}
            account={a}
            syncing={syncingIds.has(a.account_id)}
            onSync={() =>
              syncMutation.mutate({
                id: a.account_id,
                initial: !a.initial_sync_completed,
              })
            }
            onRemove={() => {
              const ok = window.confirm(
                `Remove ${a.account_id}?\n\nDisconnects the account and deletes the stored token. Parsed parcels are not affected.`,
              );
              if (!ok) return;
              removeMutation.mutate(a.account_id);
            }}
          />
        ))}
      </div>
    </>
  );
}

function Header() {
  return (
    <div className="screen-header">
      <div className="screen-title">Sources</div>
      <div className="screen-sub">
        Where parsli reads from — all runs locally on your device
      </div>
    </div>
  );
}
