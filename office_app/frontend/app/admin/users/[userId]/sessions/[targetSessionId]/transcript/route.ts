import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

type RouteContext = {
  params: Promise<{ userId: string; targetSessionId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { userId, targetSessionId } = await context.params;
  const response = await proxyJsonRequest(
    `/admin/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(targetSessionId)}/transcript${request.nextUrl.search}`,
    {
      method: "GET",
    },
  );
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
