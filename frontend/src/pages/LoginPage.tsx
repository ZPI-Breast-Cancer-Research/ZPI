import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { fetchPacsStatus } from "../api";
import logo from "../assets/logo.png";
import { setFirstPassword, signIn, AuthError, type User } from "../auth/api";
import { useAuth } from "../auth/AuthProvider";
import "../auth/login.css";
import { t } from "../i18n";

const MIN_PASSWORD = 12;

function SignInForm({ onFirstLogin, onSignedIn }: { onFirstLogin: (login: string) => void; onSignedIn: (user: User) => void }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [missing, setMissing] = useState(false);
  const [forgot, setForgot] = useState(false);

  const submit = useMutation({
    mutationFn: () => signIn(login.trim(), password),
    onSuccess: (result) => (result.kind === "first-login" ? onFirstLogin(result.login) : onSignedIn(result.user)),
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setMissing(!login.trim() || !password);
    if (login.trim() && password) submit.mutate();
  };

  const failed = submit.error instanceof AuthError;

  return (
    <>
      <h1 className="login__heading">{t("login.title")}</h1>
      <form className="login__form" onSubmit={onSubmit} noValidate>
        {(failed || submit.error || missing) && (
          <p className="login__error" role="alert">
            {missing ? t("login.required") : failed ? t("login.failed") : t("login.unavailable")}
          </p>
        )}
        <label className="field">
          <span>{t("login.username")}</span>
          <input
            className="input"
            autoComplete="username"
            placeholder={t("login.usernamePlaceholder")}
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            autoFocus
          />
        </label>
        <label className="field">
          <span>{t("login.password")}</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            placeholder={t("login.passwordPlaceholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <div className="login__row">
          <button type="button" className="link" aria-expanded={forgot} onClick={() => setForgot((f) => !f)}>
            {t("login.forgot")}
          </button>
          <button type="submit" className="btn btn--primary" disabled={submit.isPending}>
            {submit.isPending ? t("login.submitting") : t("login.submit")}
          </button>
        </div>
        {forgot && <p className="login__hint">{t("login.forgotBody")}</p>}
      </form>
      <p className="login__note">{t("login.note")}</p>
    </>
  );
}

function FirstLoginForm({ login, onCancel, onSignedIn }: { login: string; onCancel: () => void; onSignedIn: (user: User) => void }) {
  const [temporary, setTemporary] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [tried, setTried] = useState(false);
  const tooShort = next.length > 0 && next.length < MIN_PASSWORD;
  const mismatch = repeat.length > 0 && repeat !== next;

  const submit = useMutation({ mutationFn: () => setFirstPassword(login, temporary, next), onSuccess: onSignedIn });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (temporary && next.length >= MIN_PASSWORD && next === repeat) submit.mutate();
  };

  return (
    <>
      <h1 className="login__heading">{t("login.firstTitle")}</h1>
      <form className="login__form" onSubmit={onSubmit} noValidate>
        {submit.error && (
          <p className="login__error" role="alert">
            {t("login.unavailable")}
          </p>
        )}
        <label className="field">
          <span>{t("login.username")}</span>
          <input className="input" autoComplete="username" value={login} readOnly />
        </label>
        <label className={tried && !temporary ? "field field--error" : "field"}>
          <span>{t("login.tempPassword")}</span>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            placeholder={t("login.tempPlaceholder")}
            value={temporary}
            onChange={(e) => setTemporary(e.target.value)}
            autoFocus
          />
        </label>
        <label className={tooShort || (tried && next.length < MIN_PASSWORD) ? "field field--error" : "field"}>
          <span>{t("settings.newPassword")}</span>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            placeholder={t("login.newPlaceholder")}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <span className="field__help">{tooShort ? t("settings.passwordTooShort") : t("settings.passwordRule")}</span>
        </label>
        <label className={mismatch ? "field field--error" : "field"}>
          <span>{t("settings.repeatPassword")}</span>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            placeholder={t("login.repeatPlaceholder")}
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
          />
          {mismatch && <span className="field__help">{t("settings.passwordMismatch")}</span>}
        </label>
        <div className="login__row">
          <button type="button" className="link" onClick={onCancel}>
            {t("login.cancel")}
          </button>
          <button type="submit" className="btn btn--primary" disabled={submit.isPending}>
            {t("login.setAndSignIn")}
          </button>
        </div>
      </form>
    </>
  );
}

export default function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [firstLogin, setFirstLogin] = useState<string | null>(null);
  const { data: pacs = "unknown" } = useQuery({ queryKey: ["pacs-status"], queryFn: fetchPacsStatus });

  const from = (location.state as { from?: string } | null)?.from ?? "/pulpit";
  if (auth.user) return <Navigate to={from} replace />;

  const signedIn = (user: User) => {
    auth.signIn(user);
    navigate(from, { replace: true });
  };

  return (
    <div className="login">
      <header className="topbar">
        <span className="topbar__brand">
          <img src={logo} alt="" />
          {t("app.name")}
        </span>
        <span className="login__env">{t("app.env")}</span>
      </header>

      <main className="login__center">
        <div className="login__box">
          <div className="login__id">
            <img src={logo} alt="" />
            <div>
              <b>{t("app.name")}</b>
              <span>{t("app.fullName")}</span>
            </div>
          </div>
          {firstLogin ? (
            <FirstLoginForm login={firstLogin} onCancel={() => setFirstLogin(null)} onSignedIn={signedIn} />
          ) : (
            <SignInForm onFirstLogin={setFirstLogin} onSignedIn={signedIn} />
          )}
        </div>
      </main>

      <footer className="statusbar">
        <span>
          {t("status.pacs")} <b>{t(`status.pacs.${pacs}`)}</b>
        </span>
        <span className="statusbar__end">{t("status.version", { v: __APP_VERSION__ })}</span>
      </footer>
    </div>
  );
}
