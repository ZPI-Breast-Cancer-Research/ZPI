import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import Page from "../components/layout/Page";
import { ForbiddenState } from "../components/State";
import { t } from "../i18n";
import { PERMISSIONS, signOut as apiSignOut, type Permission, type Role, type User } from "./api";

interface AuthValue {
  user: User | null;
  signIn: (user: User) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

// TODO: kept in sessionStorage until there's a real session cookie from the backend
const STORAGE_KEY = "maria.user";

// dev only: VITE_SKIP_LOGIN=radiologist (or researcher, admin) signs in straight away with that role
const SKIP_LOGIN = import.meta.env.DEV ? (import.meta.env.VITE_SKIP_LOGIN as Role | undefined) : undefined;

function readUser(): User | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as User;
  } catch {
    // fall through to the dev user, if any
  }
  return SKIP_LOGIN ? { login: "dev", name: "Dev", role: SKIP_LOGIN } : null;
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

export function useCan() {
  const { user } = useAuth();
  return (permission: Permission) => !!user && (PERMISSIONS[permission] as Role[]).includes(user.role);
}

export function RequireRole({ permission, title, children }: { permission: Permission; title: string; children: ReactNode }) {
  const can = useCan();
  if (!can(permission)) {
    return (
      <Page title={title}>
        <ForbiddenState role={PERMISSIONS[permission].map((role) => t(`role.${role}`)).join(", ")} />
      </Page>
    );
  }
  return <>{children}</>;
}
