import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import Page from "../components/layout/Page";
import { ForbiddenState } from "../components/State";
import { t } from "../i18n";
import { signOut as apiSignOut, type Role, type User } from "./api";

interface AuthValue {
  user: User | null;
  signIn: (user: User) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

// TODO: kept in sessionStorage until there's a real session cookie from the backend
const STORAGE_KEY = "maria.user";

function readUser(): User | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(readUser);

  const signIn = useCallback((next: User) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setUser(next);
  }, []);

  const signOut = useCallback(async () => {
    await apiSignOut();
    sessionStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}

export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/logowanie" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}

export function RequireRole({ role, title, children }: { role: Role; title: string; children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== role) {
    return (
      <Page title={title}>
        <ForbiddenState role={t(`role.${role}`)} />
      </Page>
    );
  }
  return <>{children}</>;
}
