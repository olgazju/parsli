import { useState, type FormEvent } from "react";

import { Button } from "@/components/atoms";

const DOMAIN_RE = /^[a-z0-9.-]+\.[a-z]{2,}$/i;

interface SenderListProps {
  title: string;
  sub: string;
  kind: "allow" | "block";
  list: string[];
  onAdd: (domain: string) => void;
  onRemove: (domain: string) => void;
  busy?: boolean;
}

export function SenderList({
  title,
  sub,
  kind,
  list,
  onAdd,
  onRemove,
  busy,
}: SenderListProps) {
  const [value, setValue] = useState("");

  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const v = value.trim().toLowerCase();
    if (!v || !DOMAIN_RE.test(v)) return;
    onAdd(v);
    setValue("");
  };

  return (
    <div className="pref-section">
      <div className="section-box-header">
        <div className="section-box-title">{title}</div>
      </div>
      <div className="pref-body">
        <div className="pref-meta" style={{ marginBottom: 10 }}>
          {sub}
        </div>
        <form className="sender-add" onSubmit={submit}>
          <input
            className="sender-input"
            type="text"
            placeholder="domain.com"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={busy}
          />
          <Button
            type="submit"
            kind={kind === "allow" ? "primary" : "danger"}
            size="sm"
            disabled={busy || !value.trim()}
          >
            Add
          </Button>
        </form>
        <div className="sender-tags">
          {list.length === 0 ? (
            <span className="sender-empty">None yet.</span>
          ) : (
            list.map((d) => (
              <div key={d} className={`sender-tag ${kind}`}>
                <span>{d}</span>
                <button
                  type="button"
                  className="sender-remove"
                  onClick={() => onRemove(d)}
                  aria-label={`Remove ${d}`}
                  disabled={busy}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
