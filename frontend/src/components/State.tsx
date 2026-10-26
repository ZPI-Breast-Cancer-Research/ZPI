import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { t } from "../i18n";

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="state state--loading" aria-busy="true">
      <p>{label}</p>
      <div className="skeleton" aria-hidden="true">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} />
        ))}
      </div>
    </div>
  );
}

interface ErrorProps {
  title: string;
  body?: string;
  onRetry?: () => void;
  retrying?: boolean;
}

export function ErrorState({ title, body, onRetry, retrying = false }: ErrorProps) {
  return (
    <div className="state-alert" role="alert">
      <b>{title}</b>
      {body && <p>{body}</p>}
      {onRetry && (
        <div className="state-alert__actions">
          <button type="button" className="btn btn--primary" onClick={onRetry} disabled={retrying}>
            {retrying ? t("state.retrying") : t("state.retry")}
          </button>
        </div>
      )}
    </div>
  );
}

export function ForbiddenState({ role }: { role: string }) {
  return (
    <div className="state">
      <svg className="state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="5" y="11" width="14" height="9" rx="1.5" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
      <h3>{t("forbidden.title")}</h3>
      <p>{t("forbidden.body", { role })}</p>
      <Link className="btn" to="/pulpit">
        {t("forbidden.back")}
      </Link>
    </div>
  );
}
