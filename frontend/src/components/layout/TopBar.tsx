import { NavLink } from "react-router-dom";

import logo from "../../assets/logo.png";
import { useCan } from "../../auth/AuthProvider";
import type { Permission } from "../../auth/api";
import { t, type MessageKey } from "../../i18n";
import AccountMenu from "./AccountMenu";

const MODULES: { to: string; label: MessageKey; permission?: Permission }[] = [
  { to: "/pulpit", label: "nav.dashboard" },
  { to: "/badania", label: "nav.studies" },
  { to: "/weryfikacja", label: "nav.review", permission: "review" },
  { to: "/modele", label: "nav.models", permission: "viewModels" },
];

export default function TopBar() {
  const can = useCan();

  return (
    <header className="topbar">
      <NavLink to="/pulpit" className="topbar__brand">
        <img src={logo} alt="" />
        {t("app.name")}
      </NavLink>

      <nav className="topbar__nav" aria-label={t("nav.modules")}>
        {MODULES.filter((module) => !module.permission || can(module.permission)).map((module) => (
          <NavLink key={module.to} to={module.to}>
            {t(module.label)}
          </NavLink>
        ))}
      </nav>

      <label className="topbar__search">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
          <circle cx="7" cy="7" r="4.5" />
          <path d="M10.5 10.5l4 4" />
        </svg>
        <input type="search" placeholder={t("search.placeholder")} aria-label={t("search.label")} />
      </label>

      <div className="topbar__util">
        {can("administer") && (
          <NavLink to="/ustawienia" className="topbar__icon" aria-label={t("nav.settings")} title={t("nav.settings")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </NavLink>
        )}
        <AccountMenu />
      </div>
    </header>
  );
}
