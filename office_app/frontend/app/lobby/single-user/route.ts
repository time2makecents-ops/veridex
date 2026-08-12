import { proxyJsonRequest } from "@/lib/backend";

export async function POST() {
  const response = await proxyJsonRequest("/lobby/single-user", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: "{}",
  });

  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
