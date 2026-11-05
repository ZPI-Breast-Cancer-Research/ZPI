import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface PageProps {
  // on case screens this is the patient, not the page name; the review banner shows it among its values
  title?: ReactNode;
  // a quiet way back to the list the case was opened from
  back?: { to: string; label: string };
  context?: ReactNode;
  actions?: ReactNode;
  // a row of tabs under the banner, for screens with more than one part
  tabs?: ReactNode;
  children: ReactNode;
}

export default function Page({ title, back, context, actions, tabs, children }: PageProps) {
  return (
    <div className={tabs ? "page page--tabs" : "page"}>
      <section className="banner">
        {back && (
          <>
            <Link className="banner__back" to={back.to}>
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M13 8H3 M7 4L3 8l4 4" />
              </svg>
              {back.label}
            </Link>
            <span className="banner__rule" aria-hidden="true" />
          </>
        )}
        {title && <h1>{title}</h1>}
        {context}
        {actions && <div className="banner__actions">{actions}</div>}
      </section>
      {tabs}
      <main className="page__body">{children}</main>
    </div>
  );
}
