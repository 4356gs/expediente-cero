import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const ALLOWED_ROOTS = new Set(["cases", "health", "ready"]);

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const root = path[0];
  if (!root || !ALLOWED_ROOTS.has(root)) {
    return NextResponse.json(
      { error: { code: "proxy_path_not_allowed", message: "API path is not allowed.", issues: [] } },
      { status: 404 },
    );
  }
  const configuredBase = process.env.EXPEDIENTE_CERO_API_BASE_URL ?? "http://127.0.0.1:8000";
  const base = /^https?:\/\//.test(configuredBase) ? configuredBase : `http://${configuredBase}`;
  const target = new URL(path.map(encodeURIComponent).join("/"), `${base.replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  try {
    const response = await fetch(target, {
      method: request.method,
      body: body || undefined,
      cache: "no-store",
      headers: body ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {},
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "api_unavailable",
          message: "The Expediente Cero API is unavailable.",
          issues: [],
        },
      },
      { status: 503 },
    );
  }
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
