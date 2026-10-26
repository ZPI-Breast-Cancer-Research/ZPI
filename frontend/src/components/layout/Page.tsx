import type { ReactNode } from "react";

interface PageProps {
  // on case screens this is the patient, not the page name
  title: ReactNode;
  context?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

export default function Page({ title, context, actions, children }: PageProps) {
  return (
    <div className="page">
      <section className="banner">
        <h1>{title}</h1>
        {context}
        {actions && <div className="banner__actions">{actions}</div>}
      </section>
      <main className="page__body">{children}</main>
    </div>
  );
}
