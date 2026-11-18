import { Outlet } from "react-router-dom";

import { usePreferences } from "../../settings/preferences";
import { useTheme } from "../../settings/theme";
import { ToastProvider } from "../Toast";
import TopBar from "./TopBar";
import "./layout.css";

export default function AppShell() {
  const [preferences] = usePreferences();
  useTheme(preferences.theme);

  return (
    <ToastProvider>
      <div className="app">
        <TopBar />
        <Outlet />
      </div>
    </ToastProvider>
  );
}
