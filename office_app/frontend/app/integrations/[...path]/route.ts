import { NextRequest } from "next/server";

import { proxyRequest } from "@/lib/backend";

async function forward(request: NextRequest, method: string, context: { params: { path: string[] } }) {
  const path = `/integrations/${context.params.path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const sessionId = request.headers.get("X-Session-Id") ?? "";
  const response = await proxyRequest(path, {
    method,
    headers: sessionId ? { "X-Session-Id": sessionId, "Content-Type": "application/json" } : { "Content-Type": "application/json" },
    body: method === "POST" ? await request.text() : undefined,
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return forward(request, "GET", context);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return forward(request, "POST", context);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return forward(request, "DELETE", context);
}
