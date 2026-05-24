import { useCallback, useEffect, useState } from "react";

const KEY = "parsli.devMode";

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Dev-mode toggle, persisted across reloads via localStorage. */
export function useDevMode(): [boolean, (next: boolean) => void] {
  const [on, setOn] = useState<boolean>(read);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, on ? "1" : "0");
    } catch {
      /* ignore — quota or privacy mode */
    }
  }, [on]);

  const set = useCallback((next: boolean) => setOn(next), []);
  return [on, set];
}
