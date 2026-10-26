import { Outlet } from "react-router-dom";

import TopBar from "./TopBar";
import "./layout.css";

export default function AppShell() {
  return (
    <div className="app">
      <TopBar />
      <Outlet />
    </div>
  );
}
