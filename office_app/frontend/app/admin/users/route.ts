import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const response = await proxyJsonRequest(`/admin/users${request.nextUrl.search}`, {
    method: "GET",
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  const sessionId = request.headers.get("X-Session-Id") ?? "";
  const response = await proxyJsonRequest("/admin/users", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(sessionId ? { "X-Session-Id": sessionId } : {}),
    },
    body,
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
