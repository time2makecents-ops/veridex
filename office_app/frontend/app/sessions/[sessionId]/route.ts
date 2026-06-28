import { NextRequest } from "next/server";

import { proxyRequest } from "@/lib/backend";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId: rawSessionId } = await params;
  const sessionId = encodeURIComponent(String(rawSessionId || "").trim());
  const response = await proxyRequest(`/sessions/${sessionId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": request.headers.get("Content-Type") ?? "application/json",
      ...(request.headers.get("X-Session-Id")
        ? { "X-Session-Id": request.headers.get("X-Session-Id") as string }
        : {}),
    },
  });

  return new Response(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
