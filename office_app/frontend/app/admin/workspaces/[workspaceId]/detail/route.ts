import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

type RouteContext = {
  params: { workspaceId: string };
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { workspaceId } = context.params;
  const response = await proxyJsonRequest(
    `/admin/workspaces/${encodeURIComponent(workspaceId)}${request.nextUrl.search}`,
    {
      method: "GET",
    },
  );
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
