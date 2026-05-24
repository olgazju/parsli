import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ToastTone = "default" | "success" | "error";

interface ToastMessage {
  id: number;
  text: string;
  tone: ToastTone;
}

interface ToastContextValue {
  show: (text: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const show = useCallback((text: string, tone: ToastTone = "default") => {
    setToast({ id: Date.now() + Math.random(), text, tone });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(id);
  }, [toast]);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className={`toast${toast ? " show" : ""}${toast?.tone && toast.tone !== "default" ? ` ${toast.tone}` : ""}`}
        role="status"
        aria-live="polite"
      >
        {toast?.text}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
