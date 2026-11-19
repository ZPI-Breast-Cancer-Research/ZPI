import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

// an optional link next to the message, to what was just saved or to try again
type ToastLink = { label: string; to: string } | { label: string; onClick: () => void };

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

  const link = toast?.link;
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={toast ? "toast toast--on" : "toast"} role="status" aria-live="polite">
        {toast?.message}
        {link &&
          ("to" in link ? (
            <Link className="toast__link" to={link.to} onClick={() => setToast(null)}>
              {link.label}
            </Link>
          ) : (
            <button
              type="button"
              className="toast__link"
              onClick={() => {
                setToast(null);
                link.onClick();
              }}
            >
              {link.label}
            </button>
          ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
