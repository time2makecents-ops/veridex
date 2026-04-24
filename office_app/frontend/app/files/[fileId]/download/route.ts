import { NextRequest } from "next/server";

import { proxyRequest } from "@/lib/backend";


type RouteContext = {
  params: {
    fileId: string;
  };
};


export async function GET(request: NextRequest, context: RouteContext) {
  const fileId = encodeURIComponent(context.params.fileId);
  const query = request.nextUrl.search;
  const response = await proxyRequest(`/files/${fileId}/download${query}`, {
    method: "GET",
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition": response.headers.get("Content-Disposition") ?? "",
    },
  });
}
