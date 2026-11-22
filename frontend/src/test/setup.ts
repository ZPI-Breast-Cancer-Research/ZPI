import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

// jsdom has <dialog> without its methods
HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
  this.open = true;
};
HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
  this.open = false;
  this.dispatchEvent(new Event("close"));
};

// a request the test didn't plan for fails the test, not just the request
const unhandled: string[] = [];

beforeAll(() => server.listen({ onUnhandledRequest: (request) => void unhandled.push(`${request.method} ${new URL(request.url).pathname}`) }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
  localStorage.clear();
  const missed = unhandled.splice(0);
  if (missed.length) throw new Error(`no handler for ${missed.join(", ")}`);
});

afterAll(() => server.close());
