import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate } from "../format";
import { t } from "../i18n";
import { changePassword, fetchProfile, fetchUsers, saveProfile, type Profile, type Series } from "../settings/api";
import "../settings/settings.css";

const SERIES: Series[] = ["post", "sub", "pre"];
const SHORTCUTS = [
  ["settings.shortcut.tools", ["B", "E"]],
  ["settings.shortcut.mask", ["M"]],
  ["settings.shortcut.slice", ["↑", "↓"]],
  ["settings.shortcut.undo", ["Ctrl", "Z"]],
  ["settings.shortcut.approve", ["Ctrl", "Enter"]],
] as const;

const SECTIONS = [
  ["profil", "settings.profile"],
  ["haslo", "settings.password"],
  ["preferencje", "settings.preferences"],
] as const;

function ProfileSection({ profile }: { profile: Profile }) {
  const toast = useToast();
  const { user } = useAuth();
  const [form, setForm] = useState(profile);
  const save = useMutation({ mutationFn: saveProfile, onSuccess: () => toast(t("settings.profileSaved")) });

  return (
    <Panel title={t("settings.profile")} className="settings__section">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(form);
        }}
      >
        <div className="settings__cols">
          <div>
            <label className="field">
              <span>{t("settings.name")}</span>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" />
            </label>
            <label className="field">
              <span>{t("settings.email")}</span>
              <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" />
            </label>
          </div>
          <div>
            <label className="field">
              <span>{t("settings.role")}</span>
              <input className="input" value={user ? t(`role.${user.role}`) : ""} readOnly />
            </label>
            <label className="field">
              <span>{t("settings.pwz")}</span>
              <input className="input" value={form.pwz} onChange={(e) => setForm({ ...form, pwz: e.target.value })} inputMode="numeric" />
            </label>
          </div>
        </div>
        <div className="settings__actions">
          <button type="submit" className="btn btn--primary" disabled={save.isPending}>
            {t("settings.saveProfile")}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function PasswordSection() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [tried, setTried] = useState(false);
  const tooShort = next.length > 0 && next.length < 12;
  const mismatch = repeat.length > 0 && repeat !== next;

  const change = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      toast(t("settings.passwordChanged"));
      setCurrent("");
      setNext("");
      setRepeat("");
      setTried(false);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (current && next.length >= 12 && next === repeat) change.mutate();
  };

  return (
    <Panel title={t("settings.password")} className="settings__section">
      <form onSubmit={submit} noValidate>
        <div className="settings__cols">
          <div>
            <label className="field">
              <span>{t("settings.currentPassword")}</span>
              <input className="input" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
            </label>
          </div>
          <div>
            <label className={tooShort || (tried && next.length < 12) ? "field field--error" : "field"}>
              <span>{t("settings.newPassword")}</span>
              <input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
              <span className="field__help">{tooShort ? t("settings.passwordTooShort") : t("settings.passwordRule")}</span>
            </label>
            <label className={mismatch ? "field field--error" : "field"}>
              <span>{t("settings.repeatPassword")}</span>
              <input className="input" type="password" value={repeat} onChange={(e) => setRepeat(e.target.value)} autoComplete="new-password" />
              {mismatch && <span className="field__help">{t("settings.passwordMismatch")}</span>}
            </label>
          </div>
        </div>
        <div className="settings__actions">
          <button type="submit" className="btn" disabled={change.isPending}>
            {t("settings.changePassword")}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function PreferencesSection({ profile }: { profile: Profile }) {
  const toast = useToast();
  const [language, setLanguage] = useState(profile.language);
  const [series, setSeries] = useState(profile.defaultSeries);
  const save = useMutation({
    mutationFn: () => saveProfile({ ...profile, language, defaultSeries: series }),
    onSuccess: () => toast(t("settings.preferencesSaved")),
  });

  return (
    <Panel title={t("settings.preferences")} className="settings__section">
      <div className="settings__cols">
        <div>
          <span className="settings__label">{t("settings.language")}</span>
          <div className="segmented settings__control" role="group" aria-label={t("settings.language")}>
            <button type="button" aria-pressed={language === "pl"} onClick={() => setLanguage("pl")}>
              Polski
            </button>
            <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>
              English
            </button>
          </div>
          <span className="settings__label">{t("settings.defaultSeries")}</span>
          <div className="segmented settings__control" role="group" aria-label={t("settings.defaultSeries")}>
            {SERIES.map((s) => (
              <button key={s} type="button" aria-pressed={series === s} onClick={() => setSeries(s)}>
                {t(`settings.series.${s}`)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="settings__label">{t("settings.shortcuts")}</span>
          <table className="kv settings__keys">
            <tbody>
              {SHORTCUTS.map(([label, keys]) => (
                <tr key={label}>
                  <th>{t(label)}</th>
                  <td className="cell-right">
                    {keys.map((k) => (
                      <kbd key={k}>{k}</kbd>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="settings__actions">
        <button type="button" className="btn btn--primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {t("settings.savePreferences")}
        </button>
      </div>
    </Panel>
  );
}

function UsersSection() {
  const { data } = useQuery({ queryKey: ["users"], queryFn: fetchUsers });
  return (
    <Panel
      title={t("settings.users")}
      className="settings__section"
      aux={
        <button type="button" className="btn btn--primary btn--small">
          {t("settings.addUser")}
        </button>
      }
    >
      <table className="table">
        <thead>
          <tr>
            <th>{t("settings.col.name")}</th>
            <th>{t("settings.col.login")}</th>
            <th>{t("settings.col.role")}</th>
            <th>{t("settings.col.state")}</th>
            <th>{t("settings.col.lastLogin")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data?.map((user) => (
            <tr key={user.id}>
              <td className="cell-strong">{user.name}</td>
              <td>{user.login}</td>
              <td>{t(`role.${user.role}`)}</td>
              <td>
                <span className={user.state === "active" ? "status status--confirmed" : user.state === "invited" ? "status status--running" : "status"}>
                  {t(`userState.${user.state}`)}
                </span>
              </td>
              <td>{user.lastLogin ? formatDate(user.lastLogin) : "—"}</td>
              <td className="cell-right">
                <button type="button" className="link">
                  {t(user.state === "invited" ? "settings.resend" : "settings.edit")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

export default function SettingsPage() {
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });
  const [active, setActive] = useState("profil");
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const target = document.getElementById(active);
    target?.scrollIntoView({ block: "start" });
  }, [active]);

  const isAdmin = auth.user?.role === "admin";
  const signOut = () => auth.signOut().then(() => navigate("/logowanie", { replace: true }));

  return (
    <Page title={t("nav.settings")}>
      <div className="settings">
        <nav className="settings__nav" aria-label={t("nav.settings")}>
          <div className="settings__group">{t("settings.account")}</div>
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} aria-current={active === id ? "true" : undefined} onClick={(e) => (e.preventDefault(), setActive(id))}>
              {t(label)}
            </a>
          ))}
          {isAdmin && (
            <>
              <div className="settings__group">{t("settings.admin")}</div>
              <a href="#uzytkownicy" aria-current={active === "uzytkownicy" ? "true" : undefined} onClick={(e) => (e.preventDefault(), setActive("uzytkownicy"))}>
                {t("settings.users")}
              </a>
            </>
          )}
          <div className="settings__logout">
            <button type="button" className="btn" onClick={signOut}>
              {t("settings.logout")}
            </button>
          </div>
        </nav>
        <div className="settings__content">
          {profile && (
            <>
              <div id="profil">
                <ProfileSection profile={profile} />
              </div>
              <div id="haslo">
                <PasswordSection />
              </div>
              <div id="preferencje">
                <PreferencesSection profile={profile} />
              </div>
              {isAdmin && (
                <div id="uzytkownicy">
                  <UsersSection />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
