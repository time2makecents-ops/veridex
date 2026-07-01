import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const response = await proxyJsonRequest(`/admin/workspaces${request.nextUrl.search}`, {
    method: "GET",
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
