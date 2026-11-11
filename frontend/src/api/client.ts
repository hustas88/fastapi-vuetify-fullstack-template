export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  /** Access-token lifetime in seconds. */
  expires_in: number;
}

export interface UserPublic {
  /** UUID (v7) issued by the API. */
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

export interface Message {
  message: string;
}

/** Mounting metadata for a collection page (`backend/app/models/common.py`). */
export interface PageMeta {
  total_count: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

/** One page of a collection, as components consume it. */
export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

const API_BASE = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "app.token";
const REFRESH_TOKEN_KEY = "app.refresh";

/** Shape of every error the API returns (`backend/app/api/errors.py`). */
export interface ApiErrorDetail {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
}

export class ApiError extends Error {
  readonly status: number;
  /** Stable machine-readable code, e.g. `validation_error`. */
  readonly code?: string;
  /** Per-field messages, when the request body was invalid. */
  readonly details?: ApiErrorDetail[];

  constructor(status: number, message: string, body?: ApiErrorBody) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code;
    this.details = body?.details;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeTokens(pair: TokenResponse): void {
  localStorage.setItem(TOKEN_KEY, pair.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, pair.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// Concurrent requests that all hit 401 must share a single refresh call,
// otherwise the rotation invalidates the token the others are about to use.
let refreshInFlight: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        return false;
      }
      const payload = (await response.json()) as { data: TokenResponse };
      storeTokens(payload.data);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

/** A success body: `{ data }`, plus `meta` on collections. */
interface Envelope<T> {
  data: T;
  meta?: PageMeta;
}

async function requestEnvelope<T>(
  path: string,
  init: RequestInit = {},
  allowRefresh = true,
): Promise<Envelope<T>> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    // The access token may simply have expired. Refresh once and retry, so an
    // active user is never interrupted; if that fails the session is over.
    if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
      if (await refreshTokens()) {
        return requestEnvelope<T>(path, init, false);
      }
      clearTokens();
    } else if (response.status === 401) {
      clearTokens();
    }

    let message = response.statusText || `HTTP ${response.status}`;
    let body: ApiErrorBody | undefined;
    try {
      const payload = (await response.json()) as { error?: ApiErrorBody };
      body = payload.error;
      if (body?.message) {
        message = body.message;
      }
    } catch {
      // Response body is not JSON — keep the status text.
    }
    throw new ApiError(response.status, message, body);
  }

  if (response.status === 204) {
    return { data: undefined as T };
  }
  return (await response.json()) as Envelope<T>;
}

/** Unwrap the envelope so callers deal with the resource, not the transport. */
async function request<T>(path: string, init: RequestInit = {}, allowRefresh = true): Promise<T> {
  return (await requestEnvelope<T>(path, init, allowRefresh)).data;
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  /**
   * Fetch one page of a collection.
   *
   * Collections answer `{ data: [...], meta: {...} }`; this reshapes that into
   * `{ items, meta }` so a `v-data-table-server` can bind both halves directly.
   */
  getPage: async <T>(path: string): Promise<Page<T>> => {
    const body = await requestEnvelope<T[]>(path);
    return {
      items: body.data,
      meta: body.meta ?? {
        total_count: body.data.length,
        page: 1,
        per_page: body.data.length,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    };
  },

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    }),

  patch: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),

  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),

  async login(email: string, password: string): Promise<TokenResponse> {
    const body = new URLSearchParams({ username: email, password });
    const tokens = await request<TokenResponse>("/auth/access-token", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    storeTokens(tokens);
    return tokens;
  },

  /** Best-effort server-side revocation; local state is cleared regardless. */
  async logout(): Promise<void> {
    const refreshToken = getRefreshToken();
    clearTokens();
    if (!refreshToken) {
      return;
    }
    try {
      await request<Message>("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      // Already signed out locally; nothing else to do.
    }
  },
};

export { API_BASE };
