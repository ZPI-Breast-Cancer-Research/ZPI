import { Link, NavLink } from "react-router-dom";

import logo from "../../assets/logo.png";
import { useAuth } from "../../auth/AuthProvider";
import { t, type MessageKey } from "../../i18n";

const MODULES: { to: string; label: MessageKey; adminOnly?: boolean }[] = [
  { to: "/pulpit", label: "nav.dashboard" },
  { to: "/badania", label: "nav.studies" },
  { to: "/weryfikacja", label: "nav.review" },
  { to: "/modele", label: "nav.models", adminOnly: true },
];

export default function TopBar() {
  const { user } = useAuth();
  const initial = user?.name.charAt(0).toUpperCase() ?? "";

  return (
    <header className="topbar">
      <NavLink to="/pulpit" className="topbar__brand">
        <img src={logo} alt="" />
        {t("app.name")}
      </NavLink>

      <nav className="topbar__nav" aria-label={t("nav.modules")}>
        {MODULES.filter((module) => !module.adminOnly || user?.role === "admin").map((module) => (
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
        <NavLink to="/ustawienia">{t("nav.settings")}</NavLink>
        <Link to="/ustawienia" aria-label={t("nav.account")}>
          <span className="topbar__avatar" aria-hidden="true">
            {initial}
          </span>
          {user?.name}
        </Link>
      </div>
    </header>
  );
}
