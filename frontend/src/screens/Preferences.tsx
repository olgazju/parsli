import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/api/client";
import { ErrorState, FullLoading } from "@/components/atoms";
import { SenderList } from "@/components/SenderList";
import { useToast } from "@/components/Toast";
import { useReaderLanguages } from "@/hooks/useReaderLanguages";

export default function PreferencesScreen() {
  const qc = useQueryClient();
  const { show } = useToast();
  const readerLangs = useReaderLanguages();

  const prefs = useQuery({
    queryKey: ["domain-prefs"],
    queryFn: api.getDomainPrefs,
  });

  const handleApiError = (err: unknown, fallback: string) => {
    const msg = err instanceof ApiError ? err.message : fallback;
    show(msg, "error");
  };

  const addAllow = useMutation({
    mutationFn: (d: string) => api.addAllowlist(d),
    onSuccess: (next, d) => {
      qc.setQueryData(["domain-prefs"], next);
      show(`${d} added to allowlist.`, "success");
    },
    onError: (err) => handleApiError(err, "Couldn't add domain."),
  });
  const removeAllow = useMutation({
    mutationFn: (d: string) => api.removeAllowlist(d),
    onSuccess: (next) => qc.setQueryData(["domain-prefs"], next),
    onError: (err) => handleApiError(err, "Couldn't remove domain."),
  });
  const addBlock = useMutation({
    mutationFn: (d: string) => api.addBlocklist(d),
    onSuccess: (next, d) => {
      qc.setQueryData(["domain-prefs"], next);
      show(`${d} added to blocklist.`, "success");
    },
    onError: (err) => handleApiError(err, "Couldn't add domain."),
  });
  const removeBlock = useMutation({
    mutationFn: (d: string) => api.removeBlocklist(d),
    onSuccess: (next) => qc.setQueryData(["domain-prefs"], next),
    onError: (err) => handleApiError(err, "Couldn't remove domain."),
  });

  if (prefs.isLoading) {
    return (
      <>
        <Header />
        <FullLoading />
      </>
    );
  }
  if (prefs.isError) {
    const msg =
      prefs.error instanceof ApiError
        ? prefs.error.message
        : "Couldn't load preferences.";
    return (
      <>
        <Header />
        <ErrorState message={msg} onRetry={() => void prefs.refetch()} />
      </>
    );
  }

  const data = prefs.data!;

  return (
    <>
      <Header />

      <div className="pref-section">
        <div className="section-box-header">
          <div className="section-box-title">Languages</div>
        </div>
        <div className="pref-body">
          <div className="pref-label" style={{ marginBottom: 4 }}>
            Languages parsli reads
          </div>
          <div className="pref-meta" style={{ marginBottom: 12 }}>
            Email subjects and bodies in these languages will be parsed.
            English and Hebrew are supported today.
          </div>
          <div className="chip-group">
            {readerLangs.available.map((lang) => {
              const on = readerLangs.enabledSet.has(lang.code);
              return (
                <button
                  key={lang.code}
                  type="button"
                  className={`lang-chip${on ? " on" : ""}`}
                  onClick={() => {
                    const ok = readerLangs.toggle(lang.code);
                    if (!ok) {
                      show("At least one language must stay enabled.", "error");
                    }
                  }}
                >
                  <span className="lang-check">{on ? "✓" : ""}</span>
                  <span>{lang.name}</span>
                  <span className="lang-native">{lang.native}</span>
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
        list={data.allowlist}
        onAdd={(d) => {
          if (data.allowlist.includes(d) || data.blocklist.includes(d)) {
            show("Domain is already in a list.", "error");
            return;
          }
          addAllow.mutate(d);
        }}
        onRemove={(d) => removeAllow.mutate(d)}
        busy={addAllow.isPending || removeAllow.isPending}
      />

      <SenderList
        title="Sender blocklist"
        sub="Never process email from these domains. Marketing senders go here."
        kind="block"
        list={data.blocklist}
        onAdd={(d) => {
          if (data.allowlist.includes(d) || data.blocklist.includes(d)) {
            show("Domain is already in a list.", "error");
            return;
          }
          addBlock.mutate(d);
        }}
        onRemove={(d) => removeBlock.mutate(d)}
        busy={addBlock.isPending || removeBlock.isPending}
      />

      <div className="pref-section">
        <div className="section-box-header">
          <div className="section-box-title">Sync schedule</div>
        </div>
        <div className="pref-row">
          <div>
            <div className="pref-label">Look back 60 days on first sync</div>
            <div className="pref-meta">
              Controls how much email history parsli ingests for a new source.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Header() {
  return (
    <div className="screen-header">
      <div className="screen-title">Preferences</div>
      <div className="screen-sub">App settings, languages, sender rules</div>
    </div>
  );
}
