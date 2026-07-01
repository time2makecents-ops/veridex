import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

type RouteContext = {
  params: Promise<{ userId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { userId } = await context.params;
  const response = await proxyJsonRequest(`/admin/users/${encodeURIComponent(userId)}${request.nextUrl.search}`, {
    method: "GET",
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { userId } = await context.params;
  const sessionId = request.headers.get("X-Session-Id") ?? "";
  const response = await proxyJsonRequest(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      ...(sessionId ? { "X-Session-Id": sessionId } : {}),
    },
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
