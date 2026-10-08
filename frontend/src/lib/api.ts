// Browser API client. The access token lives only in memory; the refresh token is an
// HttpOnly cookie the browser sends to /api/v1/auth automatically.

export interface ApiErrorDetail {
  loc?: (string | number)[];
  msg?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
    public requestId: string | null = null,
  ) {
    super(message);
  }

  fieldErrors(): ApiErrorDetail[] {
    return Array.isArray(this.details) ? (this.details as ApiErrorDetail[]) : [];
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

const XHR = { "X-Requested-With": "XMLHttpRequest" };

async function toError(response: Response): Promise<ApiError> {
  // The API sets X-Request-ID on every response, including ones that are not JSON.
  const headerId = response.headers.get("x-request-id");
  try {
    const body = await response.json();
    return new ApiError(
      response.status,
      body?.error?.code ?? "http_error",
      body?.error?.message ?? response.statusText,
      body?.error?.details ?? null,
      body?.request_id ?? headerId,
    );
  } catch {
    // The API always answers in JSON. A plain-text 5xx comes from the dashboard's proxy,
    // which means the API server is not running or cannot be reached.
    if (response.status >= 500) {
      return new ApiError(
        response.status,
        "api_unreachable",
        "The API server is not responding. Check that it is running (and that the database is upgraded), then try again.",
        null,
        headerId,
      );
    }
    return new ApiError(response.status, "http_error", response.statusText || "Request failed", null, headerId);
  }
}

/** What a failed sign-in shows: the reason when it helps the person, a generic line otherwise. */
export function signInErrorText(err: unknown): string {
  if (err instanceof ApiError && (err.status === 401 || err.status === 429 || err.code === "api_unreachable")) {
    return err.message;
  }
  return "Sign-in is unavailable right now. Please try again.";
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: XHR,
        credentials: "same-origin",
      });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      const body = (await response.json()) as { access_token: string };
      setAccessToken(body.access_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

type Options = { method?: Method; body?: unknown; query?: Record<string, string | number | undefined> };

/** Sends an authenticated request, refreshing the session once on 401. Throws ApiError. */
async function request(path: string, options: Options = {}): Promise<Response> {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  const send = () =>
    fetch(url, {
      method: options.method ?? "GET",
      credentials: "same-origin",
      headers: {
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

  let response = await send();
  if (response.status === 401 && !path.startsWith("/auth/login")) {
    if (await refreshSession()) {
      response = await send();
    } else {
      onSessionExpired?.();
    }
  }
  if (!response.ok) throw await toError(response);
  return response;
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** A text body, such as a stored HTML report. */
export async function apiText(path: string): Promise<string> {
  return (await request(path)).text();
}

/** Downloads a binary response (for example a PDF) as a file with the given name. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await (await request(path)).blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export async function login(email: string, password: string): Promise<void> {
  const body = await api<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
  setAccessToken(body.access_token);
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST", headers: XHR, credentials: "same-origin" });
  } finally {
    setAccessToken(null);
  }
}
