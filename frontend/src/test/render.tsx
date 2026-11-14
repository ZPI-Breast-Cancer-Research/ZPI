import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import type { User } from "../auth/api";
import { AuthProvider } from "../auth/AuthProvider";

export const radiologist: User = { login: "demo.radiologist", name: "Anna Nowak", role: "radiologist" };
export const researcher: User = { login: "demo.researcher", name: "Marta Wiśniewska", role: "researcher" };
export const admin: User = { login: "demo.admin", name: "Demo Administrator", role: "admin" };

// a screen with the app's providers, signed in as `user` (or not at all)
export function renderScreen(ui: ReactNode, { route = "/", user = null }: { route?: string; user?: User | null } = {}) {
  if (user) sessionStorage.setItem("maria.user", JSON.stringify(user));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
