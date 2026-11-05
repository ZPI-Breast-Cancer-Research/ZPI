import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { t, type MessageKey } from "../i18n";

export type Section = [id: string, label: MessageKey, content: ReactNode];

// one long page with a side list; the hash picks the section, so menus can link straight to it
export default function Sections({ label, sections }: { label: string; sections: Section[] }) {
  const { hash } = useLocation();
  const active = hash.slice(1) || sections[0][0];

  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start", inline: "nearest" });
  }, [hash]);

  return (
    <div className="settings">
      <nav className="settings__nav" aria-label={label}>
        {sections.map(([id, name]) => (
          <Link key={id} to={`#${id}`} aria-current={active === id ? "true" : undefined}>
            {t(name)}
          </Link>
        ))}
      </nav>
      <div className="settings__content">
        {sections.map(([id, , content]) => (
          <div key={id} id={id}>
            {content}
          </div>
        ))}
      </div>
    </div>
  );
}
