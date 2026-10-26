import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/layout/AppShell";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import NotFoundPage from "./pages/NotFoundPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import SettingsPage from "./pages/SettingsPage";
import StudiesPage from "./pages/StudiesPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/pulpit" replace />} />
        <Route path="pulpit" element={<DashboardPage />} />
        <Route path="badania" element={<StudiesPage />} />
        <Route path="badania/:studyId" element={<PlaceholderPage title="nav.studies" />} />
        <Route path="weryfikacja/:studyId?" element={<PlaceholderPage title="nav.review" />} />
        <Route path="modele" element={<ModelsPage module="segmentation" />} />
        <Route path="modele/ekstrakcja" element={<ModelsPage module="extraction" />} />
        <Route path="ustawienia" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
