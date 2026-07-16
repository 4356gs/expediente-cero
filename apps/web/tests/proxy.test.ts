import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";

import { GET, POST } from "@/app/api/backend/[...path]/route";

afterEach(() => {
  delete process.env.EXPEDIENTE_CERO_API_BASE_URL;
});

it("proxies only the bounded API path through the server-only base URL", async () => {
  process.env.EXPEDIENTE_CERO_API_BASE_URL = "http://api.internal:9000";
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  const response = await GET(
    new NextRequest("http://localhost/api/backend/cases?limit=20"),
    { params: Promise.resolve({ path: ["cases"] }) },
  );
  expect(response.status).toBe(200);
  expect(fetchMock).toHaveBeenCalledWith(
    new URL("http://api.internal:9000/cases?limit=20"),
    expect.objectContaining({ method: "GET", cache: "no-store" }),
  );
});

it("forwards JSON mutations without exposing another upstream", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ id: "case-1" }), { status: 201 }),
  );
  const request = new NextRequest("http://localhost/api/backend/cases", {
    method: "POST",
    body: JSON.stringify({ is_synthetic: true }),
    headers: { "Content-Type": "application/json" },
  });
  const response = await POST(request, { params: Promise.resolve({ path: ["cases"] }) });
  expect(response.status).toBe(201);
  expect(fetchMock).toHaveBeenCalledWith(
    new URL("http://127.0.0.1:8000/cases"),
    expect.objectContaining({ method: "POST", body: JSON.stringify({ is_synthetic: true }) }),
  );
});

it("normalizes a private-network hostport without exposing it to the browser", async () => {
  process.env.EXPEDIENTE_CERO_API_BASE_URL = "expediente-cero-api:10000";
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await GET(new NextRequest("http://localhost/api/backend/cases"), {
    params: Promise.resolve({ path: ["cases"] }),
  });

  expect(fetchMock).toHaveBeenCalledWith(
    new URL("http://expediente-cero-api:10000/cases"),
    expect.any(Object),
  );
});

it("rejects unbounded paths and normalizes an unavailable API", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  const denied = await GET(new NextRequest("http://localhost/api/backend/openai"), {
    params: Promise.resolve({ path: ["openai"] }),
  });
  expect(denied.status).toBe(404);
  expect(fetchMock).not.toHaveBeenCalled();

  fetchMock.mockRejectedValue(new Error("network detail"));
  const unavailable = await GET(new NextRequest("http://localhost/api/backend/cases"), {
    params: Promise.resolve({ path: ["cases"] }),
  });
  expect(unavailable.status).toBe(503);
  await expect(unavailable.json()).resolves.toMatchObject({ error: { code: "api_unavailable" } });
});
