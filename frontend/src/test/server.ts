import { http, HttpResponse, type JsonBodyType } from "msw";
import { setupServer } from "msw/node";

// the backend as the tests see it; each test adds the endpoints it needs with server.use()
export const server = setupServer(http.get("/api/health", () => HttpResponse.json({ orthanc: "ok" })));

export { http, HttpResponse, type JsonBodyType };
