import { useEffect } from "react";

import type { Theme } from "./preferences";

const SYSTEM_DARK = "(prefers-color-scheme: dark)";

export function applyTheme(theme: Theme) {
  const dark = theme === "system" ? (window.matchMedia?.(SYSTEM_DARK).matches ?? true) : theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

// "system" keeps following the operating system while the app is open
export function useTheme(theme: Theme) {
  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system" || !window.matchMedia) return;
    const query = window.matchMedia(SYSTEM_DARK);
    const change = () => applyTheme("system");
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, [theme]);
}
