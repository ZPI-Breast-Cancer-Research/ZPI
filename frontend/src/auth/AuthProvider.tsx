import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { hasSession, onSessionEnd } from "../api";
import Page from "../components/layout/Page";
import { ForbiddenState } from "../components/State";
import { t } from "../i18n";
import { MOCK_API } from "../mock";
import { PERMISSIONS, signOut as apiSignOut, type Permission, type Role, type User } from "./api";

interface AuthValue {
  user: User | null;
  // signed out by the server, not by the user
  expired: boolean;
  signIn: (user: User) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

// who is signed in, for this tab; the session itself is the backend's cookie
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
  const [expired, setExpired] = useState(false);
  const queryClient = useQueryClient();

  const signIn = useCallback((next: User) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setUser(next);
    setExpired(false);
  }, []);

  useEffect(() => {
    const end = () => {
      sessionStorage.removeItem(STORAGE_KEY);
      setUser(null);
      setExpired(true);
      queryClient.clear();
    };
    const stop = onSessionEnd(end);
    // a tab kept open overnight still remembers the user, the server may not
    if (!MOCK_API && readUser()) hasSession().then((alive) => !alive && end());
    return stop;
  }, [queryClient]);

  // leave locally even if the server call fails, otherwise there's no way out
  const signOut = useCallback(async () => {
    try {
      await apiSignOut();
    } catch {
      // the next sign-in replaces the server session anyway
    } finally {
      sessionStorage.removeItem(STORAGE_KEY);
      setUser(null);
      queryClient.clear();
    }
  }, [queryClient]);

  return <AuthContext.Provider value={{ user, expired, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}

export function RequireAuth() {
  const { user, expired } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/logowanie" replace state={{ from: location.pathname + location.search, expired }} />;
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
