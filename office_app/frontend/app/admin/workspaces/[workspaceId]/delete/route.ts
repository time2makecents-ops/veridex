import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

type RouteContext = {
  params: Promise<{ workspaceId: string }>;
};

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { workspaceId } = await context.params;
  const sessionId = request.headers.get("X-Session-Id") ?? "";
  const response = await proxyJsonRequest(`/admin/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: "DELETE",
    headers: {
      ...(sessionId ? { "X-Session-Id": sessionId } : {}),
    },
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
