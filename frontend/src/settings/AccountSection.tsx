import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { t, type MessageKey } from "../i18n";
import { forgetViewerLayout } from "../viewer/layout";
import type { Plane, Series } from "../viewer/types";
import { changePassword, type Profile } from "./api";
import { usePreferences, type Preferences } from "./preferences";

export function ProfileSection({ profile }: { profile: Profile }) {
  const rows: [MessageKey, string][] = [
    ["settings.name", profile.name],
    ["settings.login", profile.login],
    ["settings.email", profile.email],
    ["settings.role", t(`role.${profile.role}`)],
    ["settings.pwz", profile.pwz ?? "—"],
  ];
  return (
    <Panel title={t("settings.profile")} className="settings__section">
      <div className="settings__body">
        <table className="kv settings__kv">
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label}>
                <th>{t(label)}</th>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="field__help">{t("settings.profileNote")}</p>
      </div>
    </Panel>
  );
}

export function PasswordSection() {
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

function Choice<T extends string | boolean>({ label, value, options, onChange }: { label: MessageKey; value: T; options: [T, MessageKey][]; onChange: (value: T) => void }) {
  return (
    <div className="settings__choice">
      <span className="settings__label">{t(label)}</span>
      <div className="segmented" role="group" aria-label={t(label)}>
        {options.map(([option, name]) => (
          <button key={String(option)} type="button" aria-pressed={value === option} onClick={() => onChange(option)}>
            {t(name)}
          </button>
        ))}
      </div>
    </div>
  );
}

// saved as soon as it changes; what the viewer opens with, not how it looks right now
export function WorkSection() {
  const toast = useToast();
  const [preferences, update] = usePreferences();
  const set = (change: Partial<Preferences>) => {
    update(change);
    if ("main" in change || "single" in change) forgetViewerLayout();
    toast(t("settings.saved"));
  };

  return (
    <Panel title={t("settings.work")} className="settings__section">
      <div className="settings__body settings__choices">
        <Choice<Series>
          label="settings.defaultSeries"
          value={preferences.series}
          options={[
            ["post", "viewer.series.post"],
            ["sub", "viewer.series.sub"],
            ["pre", "viewer.series.pre"],
          ]}
          onChange={(series) => set({ series })}
        />
        <Choice<Plane>
          label="settings.mainPlane"
          value={preferences.main}
          options={[
            ["axial", "viewer.plane.axial"],
            ["sagittal", "viewer.plane.sagittal"],
            ["coronal", "viewer.plane.coronal"],
          ]}
          onChange={(main) => set({ main })}
        />
        <Choice<boolean>
          label="settings.layout"
          value={preferences.single}
          options={[
            [false, "settings.layout.three"],
            [true, "settings.layout.one"],
          ]}
          onChange={(single) => set({ single })}
        />
        <Choice<boolean>
          label="settings.maskOnOpen"
          value={preferences.maskShown}
          options={[
            [true, "settings.mask.shown"],
            [false, "settings.mask.hidden"],
          ]}
          onChange={(maskShown) => set({ maskShown })}
        />
        <Choice<boolean>
          label="settings.hints"
          value={preferences.hints}
          options={[
            [true, "settings.on"],
            [false, "settings.off"],
          ]}
          onChange={(hints) => set({ hints })}
        />
      </div>
    </Panel>
  );
}

const KEYS: [MessageKey, [MessageKey, string[]][]][] = [
  [
    "settings.keys.tools",
    [
      ["viewer.pan", ["P"]],
      ["viewer.window", ["W"]],
      ["viewer.brush", ["B"]],
      ["viewer.threshold", ["T"]],
      ["viewer.eraser", ["E"]],
      ["settings.key.shape", ["S"]],
      ["settings.key.radius", ["[", "]"]],
      ["viewer.fill", ["I"]],
      ["viewer.restoreSlice", ["R"]],
      ["viewer.undo", ["Ctrl", "Z"]],
    ],
  ],
  [
    "settings.keys.image",
    [
      ["settings.key.slice", ["↑", "↓"]],
      ["settings.key.grab", ["Spacja"]],
      ["settings.key.zoom", ["+", "−"]],
      ["viewer.fit", ["0"]],
      ["settings.key.mask", ["M"]],
    ],
  ],
  [
    "settings.keys.views",
    [
      ["settings.key.main", ["1", "2", "3"]],
      ["settings.key.single", ["V"]],
      ["settings.key.full", ["F"]],
      ["settings.key.close", ["Esc"]],
    ],
  ],
  [
    "settings.keys.case",
    [
      ["review.pickNext", ["N"]],
      ["settings.key.next", ["Ctrl", "Enter"]],
    ],
  ],
];

// a reference card: the keys are fixed, so there is nothing to save here
export function ShortcutsSection() {
  return (
    <Panel title={t("settings.shortcuts")} className="settings__section">
      <div className="settings__body settings__keys">
        {KEYS.map(([group, rows]) => (
          <table key={group} className="kv">
            <thead>
              <tr>
                <th colSpan={2}>{t(group)}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, keys]) => (
                <tr key={label}>
                  <th>{t(label)}</th>
                  <td className="cell-right">
                    {keys.map((key) => (
                      <kbd key={key}>{key}</kbd>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
    </Panel>
  );
}
