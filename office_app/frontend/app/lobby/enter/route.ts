import { NextRequest } from "next/server";

import { proxyJsonRequest } from "@/lib/backend";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const response = await proxyJsonRequest("/lobby/enter", {
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
