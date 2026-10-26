import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/layout/AppShell";
import NotFoundPage from "./pages/NotFoundPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import StudiesPage from "./pages/StudiesPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/pulpit" replace />} />
        <Route path="pulpit" element={<PlaceholderPage title="nav.dashboard" />} />
        <Route path="badania" element={<StudiesPage />} />
        <Route path="weryfikacja" element={<PlaceholderPage title="nav.review" />} />
        <Route path="modele" element={<PlaceholderPage title="nav.models" />} />
        <Route path="ustawienia" element={<PlaceholderPage title="nav.settings" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
