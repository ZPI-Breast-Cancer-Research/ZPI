import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "./auth/AuthProvider";
import AppShell from "./components/layout/AppShell";
import { t } from "./i18n";
import DashboardPage from "./pages/DashboardPage";
import LesionOverviewPage from "./pages/LesionOverviewPage";
import LoginPage from "./pages/LoginPage";
import ModelsPage from "./pages/ModelsPage";
import NotFoundPage from "./pages/NotFoundPage";
import ReviewPage from "./pages/ReviewPage";
import SettingsPage from "./pages/SettingsPage";
import StudiesPage from "./pages/StudiesPage";

export default function App() {
  return (
    <Routes>
      <Route path="logowanie" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/pulpit" replace />} />
          <Route path="pulpit" element={<DashboardPage />} />
          <Route path="badania" element={<StudiesPage />} />
          <Route path="badania/:studyId" element={<LesionOverviewPage />} />
          <Route path="weryfikacja/:studyId?" element={<ReviewPage />} />
          <Route
            path="modele"
            element={
              <RequireRole role="admin" title={t("nav.models")}>
                <ModelsPage module="segmentation" />
              </RequireRole>
            }
          />
          <Route
            path="modele/ekstrakcja"
            element={
              <RequireRole role="admin" title={t("nav.models")}>
                <ModelsPage module="extraction" />
              </RequireRole>
            }
          />
          <Route path="ustawienia" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
