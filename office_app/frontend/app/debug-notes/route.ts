import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const pagePath = request.nextUrl.searchParams.get("page_path") || "/";
  const activeRoom = request.nextUrl.searchParams.get("active_room") || "";
  const activePersona = request.nextUrl.searchParams.get("active_persona") || "";
  const params = new URLSearchParams({ page_path: pagePath });
  if (activeRoom) {
    params.set("active_room", activeRoom);
  }
  if (activePersona) {
    params.set("active_persona", activePersona);
  }
  const target = `/debug-notes?${params.toString()}`;
  const response = await proxyJsonRequest(target, { method: "GET" });

  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function PUT(request: NextRequest) {
  const body = await request.text();
  const response = await proxyJsonRequest("/debug-notes", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });

  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
