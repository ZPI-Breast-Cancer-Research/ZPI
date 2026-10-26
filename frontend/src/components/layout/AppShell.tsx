import { Outlet } from "react-router-dom";

import { ToastProvider } from "../Toast";
import TopBar from "./TopBar";
import "./layout.css";

export default function AppShell() {
  return (
    <ToastProvider>
      <div className="app">
        <TopBar />
        <Outlet />
      </div>
    </ToastProvider>
  );
}
