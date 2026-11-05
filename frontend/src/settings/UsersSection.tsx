import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import type { Role } from "../auth/api";
import { useAuth } from "../auth/AuthProvider";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate } from "../format";
import { t } from "../i18n";
import { createUser, fetchUsers, resetPassword, setBlocked, updateUser, type UserDraft, type UserRow, type UserState } from "./api";

const ROLES: Role[] = ["radiologist", "researcher", "admin"];
const STATE_CLASS: Record<UserState, string> = {
  active: "status status--confirmed",
  temporary: "status status--running",
  blocked: "status",
};
const EMPTY: UserDraft = { name: "", login: "", email: "", role: "radiologist", pwz: null };

function problems(draft: UserDraft) {
  return {
    name: !draft.name.trim(),
    login: !/^[a-z0-9._-]{3,32}$/.test(draft.login),
    email: !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(draft.email),
    pwz: draft.role === "radiologist" && !/^\d{7}$/.test(draft.pwz ?? ""),
  };
}

// shown once: the admin hands it over in person, the person replaces it at first login
function Issued({ login, password, onDone }: { login: string; password: string; onDone: () => void }) {
  const toast = useToast();
  return (
    <div className="users__band" role="status">
      <div className="users__issued">
        <span>{t("users.issued", { login })}</span>
        <code>{password}</code>
        <button type="button" className="btn btn--small" onClick={() => navigator.clipboard.writeText(password).then(() => toast(t("users.copied")))}>
          {t("users.copy")}
        </button>
      </div>
      <p className="field__help">{t("users.issuedNote")}</p>
      <div className="users__row">
        <button type="button" className="btn" onClick={onDone}>
          {t("users.done")}
        </button>
      </div>
    </div>
  );
}

interface FormProps {
  user: UserRow | null;
  self: boolean;
  lastAdmin: boolean;
  onClose: () => void;
  onIssued: (login: string, password: string) => void;
}

function UserForm({ user, self, lastAdmin, onClose, onIssued }: FormProps) {
  const toast = useToast();
  const client = useQueryClient();
  const [draft, setDraft] = useState<UserDraft>(user ?? EMPTY);
  const [tried, setTried] = useState(false);
  const [taken, setTaken] = useState(false);
  const wrong = problems(draft);
  const set = (change: Partial<UserDraft>) => setDraft({ ...draft, ...change });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["users"] });
    client.invalidateQueries({ queryKey: ["audit"] });
  };
  // the only admin keeps the role, or nobody could manage accounts
  const roleLocked = self && lastAdmin;

  const save = useMutation({
    mutationFn: () => {
      const clean = { ...draft, name: draft.name.trim(), pwz: draft.role === "radiologist" ? draft.pwz : null };
      return user ? updateUser(user.id, clean).then(() => null) : createUser(clean);
    },
    onSuccess: (issued) => {
      refresh();
      if (issued) onIssued(draft.login, issued.password);
      else toast(t("settings.saved"));
      onClose();
    },
    onError: () => setTaken(true),
  });

  const block = useMutation({
    mutationFn: () => setBlocked(user!.id, user!.state !== "blocked"),
    onSuccess: () => {
      refresh();
      toast(t(user!.state === "blocked" ? "users.unblocked" : "users.blocked"));
      onClose();
    },
  });

  const reset = useMutation({
    mutationFn: () => resetPassword(user!.id),
    onSuccess: ({ password }) => {
      refresh();
      onIssued(user!.login, password);
      onClose();
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!Object.values(wrong).some(Boolean)) save.mutate();
  };

  const field = (bad: boolean) => (tried && bad ? "field field--error" : "field");

  return (
    <form className="users__band" onSubmit={submit} noValidate>
      <b>{user ? t("users.editing", { name: user.name }) : t("users.new")}</b>
      <div className="users__fields">
        <label className={field(wrong.name)}>
          <span>{t("settings.name")}</span>
          <input className="input" value={draft.name} onChange={(e) => set({ name: e.target.value })} autoFocus />
        </label>
        <label className={field(wrong.login || taken)}>
          <span>{t("settings.login")}</span>
          <input
            className="input"
            value={draft.login}
            readOnly={!!user}
            onChange={(e) => {
              setTaken(false);
              set({ login: e.target.value.toLowerCase() });
            }}
          />
          {!user && <span className="field__help">{taken ? t("users.loginTaken") : t("users.loginRule")}</span>}
        </label>
        <label className={field(wrong.email)}>
          <span>{t("settings.email")}</span>
          <input className="input" type="email" value={draft.email} onChange={(e) => set({ email: e.target.value })} />
        </label>
        <label className="field">
          <span>{t("settings.role")}</span>
          <select className="select" value={draft.role} disabled={roleLocked} onChange={(e) => set({ role: e.target.value as Role })}>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {t(`role.${role}`)}
              </option>
            ))}
          </select>
          {roleLocked && <span className="field__help">{t("users.lastAdmin")}</span>}
        </label>
        {draft.role === "radiologist" && (
          <label className={field(wrong.pwz)}>
            <span>{t("settings.pwz")}</span>
            <input className="input" inputMode="numeric" value={draft.pwz ?? ""} onChange={(e) => set({ pwz: e.target.value.replace(/\D/g, "").slice(0, 7) })} />
            <span className="field__help">{t("users.pwzRule")}</span>
          </label>
        )}
      </div>
      <div className="users__row">
        {user && (
          <span className="users__danger">
            {user.state !== "blocked" && (
              <button type="button" className="btn" disabled={reset.isPending} onClick={() => window.confirm(t("users.resetConfirm", { name: user.name })) && reset.mutate()}>
                {t("users.reset")}
              </button>
            )}
            {self ? (
              <span className="field__help">{t("users.notSelf")}</span>
            ) : (
              <button
                type="button"
                className="btn"
                disabled={block.isPending}
                onClick={() => (user.state === "blocked" || window.confirm(t("users.blockConfirm", { name: user.name }))) && block.mutate()}
              >
                {t(user.state === "blocked" ? "users.unblock" : "users.block")}
              </button>
            )}
          </span>
        )}
        <button type="button" className="btn" onClick={onClose}>
          {t("users.cancel")}
        </button>
        <button type="submit" className="btn btn--primary" disabled={save.isPending}>
          {t(user ? "users.save" : "users.create")}
        </button>
      </div>
    </form>
  );
}

// accounts are blocked, never deleted: their history stays in the audit log
export default function UsersSection() {
  const me = useAuth().user?.login;
  const { data } = useQuery({ queryKey: ["users"], queryFn: fetchUsers });
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [issued, setIssued] = useState<{ login: string; password: string } | null>(null);
  const admins = data?.filter((user) => user.role === "admin" && user.state !== "blocked").length ?? 0;

  const open = (target: UserRow | "new") => {
    setIssued(null);
    setEditing(target);
  };

  return (
    <Panel
      title={t("settings.users")}
      className="settings__section"
      aux={
        <button type="button" className="btn btn--primary btn--small" onClick={() => open("new")}>
          {t("users.add")}
        </button>
      }
    >
      {issued && <Issued {...issued} onDone={() => setIssued(null)} />}
      {editing && (
        <UserForm
          key={editing === "new" ? "new" : editing.id}
          user={editing === "new" ? null : editing}
          self={editing !== "new" && editing.login === me}
          lastAdmin={admins <= 1}
          onClose={() => setEditing(null)}
          onIssued={(login, password) => setIssued({ login, password })}
        />
      )}
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
            <tr key={user.id} className={user.state === "blocked" ? "users__blocked" : undefined}>
              <td className="cell-strong">
                {user.name}
                {user.login === me && <span className="users__me"> · {t("users.you")}</span>}
              </td>
              <td>{user.login}</td>
              <td>{t(`role.${user.role}`)}</td>
              <td>
                <span className={STATE_CLASS[user.state]}>{t(`userState.${user.state}`)}</span>
              </td>
              <td>{user.lastLogin ? formatDate(user.lastLogin) : "—"}</td>
              <td className="cell-right">
                <button type="button" className="link" onClick={() => open(user)}>
                  {t("users.edit")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
