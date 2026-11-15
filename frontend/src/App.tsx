import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "./auth/AuthProvider";
import AppShell from "./components/layout/AppShell";
import Page from "./components/layout/Page";
import { LoadingState } from "./components/State";
import { t } from "./i18n";
import AccountPage from "./pages/AccountPage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import ModelsPage from "./pages/ModelsPage";
import NotFoundPage from "./pages/NotFoundPage";
import SettingsPage from "./pages/SettingsPage";
import StudiesPage from "./pages/StudiesPage";

// the image viewer is the heavy part, so its pages load when opened
const LesionOverviewPage = lazy(() => import("./pages/LesionOverviewPage"));
const ReviewPage = lazy(() => import("./pages/ReviewPage"));

function Loading({ title, label }: { title: string; label: string }) {
  return (
    <Page title={title}>
      <LoadingState label={label} />
    </Page>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="logowanie" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/pulpit" replace />} />
          <Route path="pulpit" element={<DashboardPage />} />
          <Route path="badania" element={<StudiesPage />} />
          <Route
            path="badania/:studyId"
            element={
              <Suspense fallback={<Loading title={t("overview.title")} label={t("overview.loading")} />}>
                <LesionOverviewPage />
              </Suspense>
            }
          />
          <Route
            path="weryfikacja/:studyId?"
            element={
              <RequireRole permission="review" title={t("nav.review")}>
                <Suspense fallback={<Loading title={t("nav.review")} label={t("review.loading")} />}>
                  <ReviewPage />
                </Suspense>
              </RequireRole>
            }
          />
          <Route
            path="modele"
            element={
              <RequireRole permission="viewModels" title={t("nav.models")}>
                <ModelsPage module="segmentation" />
              </RequireRole>
            }
          />
          <Route
            path="modele/ekstrakcja"
            element={
              <RequireRole permission="viewModels" title={t("nav.models")}>
                <ModelsPage module="extraction" />
              </RequireRole>
            }
          />
          <Route path="konto" element={<AccountPage />} />
          <Route
            path="ustawienia"
            element={
              <RequireRole permission="administer" title={t("nav.settings")}>
                <SettingsPage />
              </RequireRole>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
