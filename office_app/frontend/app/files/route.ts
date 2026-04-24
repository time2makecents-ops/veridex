import { NextRequest } from "next/server";

import { proxyRequest } from "@/lib/backend";


export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  const response = await proxyRequest(`/files${query}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}


export async function POST(request: NextRequest) {
  const body = await request.text();
  const response = await proxyRequest("/files/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });

  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
