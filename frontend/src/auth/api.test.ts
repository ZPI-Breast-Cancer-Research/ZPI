import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import signin from "../test/fixtures/signin.json";
import { http, HttpResponse, server } from "../test/server";
import { AuthError, signIn } from "./api";

describe("signIn", () => {
  it("returns the signed-in user", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json(signin)));
    expect(await signIn("demo.radiologist", "haslo")).toEqual({
      kind: "signed-in",
      user: { login: "demo.radiologist", name: "Anna Nowak", role: "radiologist" },
    });
  });

  it("passes on a first sign-in with a temporary password", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json({ kind: "first-login", login: "nowy" })));
    expect(await signIn("nowy", "tymczasowe")).toEqual({ kind: "first-login", login: "nowy" });
  });

  it("sends the login and password as typed", async () => {
    let body: unknown;
    server.use(
      http.post("/api/auth/signin/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(signin);
      }),
    );
    await signIn("demo.radiologist", "Demo Pass 1!");
    expect(body).toEqual({ login: "demo.radiologist", password: "Demo Pass 1!" });
  });

  it("treats 401 as a wrong login or password", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json({ detail: "bad credentials" }, { status: 401 })));
    await expect(signIn("demo.radiologist", "zle")).rejects.toBeInstanceOf(AuthError);
  });

  it("doesn't blame the password when the server fails", async () => {
    server.use(http.post("/api/auth/signin/", () => new HttpResponse(null, { status: 502 })));
    const error = await signIn("demo.radiologist", "haslo").catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(AuthError);
    expect(error).toBeInstanceOf(ApiError);
  });
});
