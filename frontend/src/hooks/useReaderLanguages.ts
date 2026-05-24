import { useCallback, useEffect, useMemo, useState } from "react";

const KEY = "parsli.readerLangs";

export interface ReaderLanguage {
  code: string;
  name: string;
  native: string;
}

export const AVAILABLE_READER_LANGUAGES: ReaderLanguage[] = [
  { code: "en", name: "English", native: "English" },
  { code: "he", name: "Hebrew", native: "עברית" },
];

const DEFAULT_ENABLED: string[] = ["en", "he"];

function read(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_ENABLED;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((c) => typeof c === "string")) {
      return parsed.length === 0 ? DEFAULT_ENABLED : parsed;
    }
    return DEFAULT_ENABLED;
  } catch {
    return DEFAULT_ENABLED;
  }
}

/** Languages the parser/backend reads (separate from the UI language).
   Persisted via localStorage until a backend endpoint exists. */
export function useReaderLanguages() {
  const [enabled, setEnabled] = useState<string[]>(read);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(enabled));
    } catch {
      /* ignore */
    }
  }, [enabled]);

  const enabledSet = useMemo(() => new Set(enabled), [enabled]);

  /** Returns true on success, false if the toggle would empty the list. */
  const toggle = useCallback(
    (code: string): boolean => {
      let ok = true;
      setEnabled((prev) => {
        const has = prev.includes(code);
        const next = has ? prev.filter((c) => c !== code) : [...prev, code];
        if (next.length === 0) {
          ok = false;
          return prev;
        }
        return next;
      });
      return ok;
    },
    [],
  );

  return {
    available: AVAILABLE_READER_LANGUAGES,
    enabled,
    enabledSet,
    toggle,
  };
}
