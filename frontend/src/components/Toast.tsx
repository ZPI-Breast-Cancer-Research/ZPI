import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

// an optional link next to the message, e.g. to what was just saved
interface ToastLink {
  label: string;
  to: string;
}

type ShowToast = (message: string, link?: ToastLink) => void;

const ToastContext = createContext<ShowToast>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; link?: ToastLink } | null>(null);
  const timer = useRef<number>();

  const show = useCallback<ShowToast>((message, link) => {
    setToast({ message, link });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), link ? 5000 : 2800);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={toast ? "toast toast--on" : "toast"} role="status" aria-live="polite">
        {toast?.message}
        {toast?.link && (
          <Link className="toast__link" to={toast.link.to} onClick={() => setToast(null)}>
            {toast.link.label}
          </Link>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
