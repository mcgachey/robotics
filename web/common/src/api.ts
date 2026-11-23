export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** JSON request to the server. Throws ApiError with the server's friendly message. */
export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your network connection.');
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* no body */
  }
  if (!res.ok) {
    const msg = (data as { error?: string } | null)?.error ?? `The server returned an error (${res.status}).`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export const get = <T>(path: string) => api<T>('GET', path);
export const post = <T>(path: string, body: unknown = {}) => api<T>('POST', path, body);
export const put = <T>(path: string, body: unknown) => api<T>('PUT', path, body);
export const patch = <T>(path: string, body: unknown) => api<T>('PATCH', path, body);

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
