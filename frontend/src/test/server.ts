import { http, HttpResponse, type JsonBodyType } from "msw";
import { setupServer } from "msw/node";

// the backend as the tests see it; each test adds the endpoints it needs with server.use()
export const server = setupServer(http.get("/api/health", () => HttpResponse.json({ orthanc: "ok" })));

export interface Sent {
  path: string;
  csrf: string | null;
  body: unknown;
}

// POSTs that reached the backend under these paths, in the order they came
export function capturePosts(...paths: string[]): Sent[] {
  const sent: Sent[] = [];
  server.use(
    ...paths.map((path) =>
      http.post(path, async ({ request }) => {
        const text = await request.text();
        sent.push({ path: new URL(request.url).pathname, csrf: request.headers.get("X-CSRFToken"), body: text ? JSON.parse(text) : null });
        return new HttpResponse(null, { status: 204 });
      }),
    ),
  );
  return sent;
}

export { http, HttpResponse, type JsonBodyType };
