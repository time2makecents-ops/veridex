const BACKEND_BASE_URL = process.env.VERIDEX_BACKEND_URL ?? "http://127.0.0.1:8078";

export async function proxyJsonRequest(path: string, init: RequestInit): Promise<Response> {
  return fetch(`${BACKEND_BASE_URL}${path}`, init);
}
