import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { t } from "../../i18n";

// who is signed in and the way out; the bar shows only the initial
export default function AccountMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [location]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && setOpen(false);
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  if (!user) return null;
  const leave = () => signOut().then(() => navigate("/logowanie", { replace: true }));

  return (
    <div className="account" ref={box}>
      <button
        type="button"
        className="account__button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${t("nav.account")}: ${user.name}`}
        title={user.name}
        onClick={() => setOpen(!open)}
      >
        <span className="topbar__avatar" aria-hidden="true">
          {user.name.charAt(0).toUpperCase()}
        </span>
      </button>
      {open && (
        <div className="account__menu" role="menu" aria-label={t("nav.account")}>
          <div className="account__who">
            <b>{user.name}</b>
            <span>
              {t(`role.${user.role}`)} · {user.login}
            </span>
          </div>
          <Link role="menuitem" to="/konto">
            {t("nav.accountSettings")}
          </Link>
          <Link role="menuitem" to="/konto#skroty">
            {t("settings.shortcuts")}
          </Link>
          <button type="button" role="menuitem" className="account__out" onClick={leave}>
            {t("settings.logout")}
          </button>
        </div>
      )}
    </div>
  );
}
