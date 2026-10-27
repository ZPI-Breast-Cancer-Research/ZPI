import type { ReactNode } from "react";

interface PanelProps {
  title: ReactNode;
  aux?: ReactNode;
  className?: string;
  children: ReactNode;
}

export default function Panel({ title, aux, className, children }: PanelProps) {
  return (
    <section className={className ? `panel ${className}` : "panel"}>
      <header className="panel__header">
        <h2>{title}</h2>
        {aux !== undefined && <span className="panel__aux">{aux}</span>}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
