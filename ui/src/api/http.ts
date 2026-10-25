type ErrorSpec = string | ((res: Response) => Promise<Error>);

export async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === "string" && body.detail) return body.detail;
  } catch {
    return fallback;
  }
  return fallback;
}

export async function request(url: string, error: ErrorSpec, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init);
  if (res.ok) return res;
  throw typeof error === "string" ? new Error(await errorDetail(res, error)) : await error(res);
}

export async function getJson<T>(url: string, error: ErrorSpec, init?: RequestInit): Promise<T> {
  return (await request(url, error, init)).json() as Promise<T>;
}

export function jsonBody(body: unknown, method = "POST"): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
