/**
 * Typed client for the MediaFlow API.
 * - Base URL comes from app config (EXPO_PUBLIC_API_URL). No secrets live in the app.
 * - Every install gets an anonymous session on first use; the token sits in the OS keychain/keystore.
 * - Release builds refuse plain-http API URLs (except emulator loopback in dev builds).
 */
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';

import type { Account, Analysis, Connection, DownloadTicket, PlatformInfo, ServerDownload, SessionOut } from './types';

const TOKEN_KEY = 'mediaflow.session';
const REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export function apiBaseUrl(): string {
  const raw = (Constants.expoConfig?.extra as { apiUrl?: string } | undefined)?.apiUrl ?? '';
  const url = raw.replace(/\/+$/, '');
  if (!__DEV__ && !url.startsWith('https://')) {
    throw new ApiError(0, 'insecure_api_url', 'This build is misconfigured: the API address must use HTTPS.');
  }
  return url;
}

let tokenCache: string | null | undefined;
let sessionPromise: Promise<string> | null = null;

async function getToken(): Promise<string | null> {
  if (tokenCache === undefined) tokenCache = await SecureStore.getItemAsync(TOKEN_KEY);
  return tokenCache;
}

export async function setToken(token: string | null): Promise<void> {
  tokenCache = token;
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

async function ensureSession(): Promise<string> {
  const existing = await getToken();
  if (existing) return existing;
  sessionPromise ??= raw<SessionOut>('POST', '/api/v1/auth/anonymous', undefined, null)
    .then(async (s) => {
      await setToken(s.token);
      return s.token;
    })
    .finally(() => {
      sessionPromise = null;
    });
  return sessionPromise;
}

async function raw<T>(method: string, path: string, body?: unknown, token?: string | null, query?: Record<string, string | number | undefined>): Promise<T> {
  const qs = query
    ? '?' + Object.entries(query).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')
    : '';
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl()}${path}${qs === '?' ? '' : qs}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    const aborted = (e as Error)?.name === 'AbortError';
    throw new ApiError(0, 'network', aborted ? 'The server took too long to respond.' : 'Can’t reach the MediaFlow server. Check your connection.');
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const d = (data ?? {}) as { code?: string; message?: string };
    throw new ApiError(res.status, d.code ?? `http_${res.status}`, d.message ?? `Request failed (HTTP ${res.status}).`);
  }
  return data as T;
}

/** Authenticated request; transparently re-creates an anonymous session if the old one expired. */
async function call<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | undefined>): Promise<T> {
  const token = await ensureSession();
  try {
    return await raw<T>(method, path, body, token, query);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      await setToken(null);
      return raw<T>(method, path, body, await ensureSession(), query);
    }
    throw e;
  }
}

export const api = {
  health: () => raw<{ status: string; version: string }>('GET', '/api/v1/health'),
  analyze: (url: string) => call<Analysis>('POST', '/api/v1/media/analyze', { url }),
  platforms: () => call<PlatformInfo[]>('GET', '/api/v1/platforms'),
  authorizeDownload: (analysisId: string, optionId: string) =>
    call<DownloadTicket>('POST', '/api/v1/downloads', { analysis_id: analysisId, option_id: optionId }),
  reportDownload: (id: string, status: 'in_progress' | 'completed' | 'failed', receivedBytes?: number, errorCode?: string) =>
    call<ServerDownload>('PATCH', `/api/v1/downloads/${id}`, { status, received_bytes: receivedBytes, error_code: errorCode }),
  cancelDownload: (id: string) => call<ServerDownload>('POST', `/api/v1/downloads/${id}/cancel`),
  deleteDownload: (id: string) => call<void>('DELETE', `/api/v1/downloads/${id}`),
  listDownloads: (q?: { status?: string; q?: string; cursor?: string; limit?: number }) =>
    call<{ items: ServerDownload[]; next_cursor: string | null }>('GET', '/api/v1/downloads', undefined, q),
  account: () => call<Account>('GET', '/api/v1/account'),
  updateAccount: (keepServerHistory: boolean) => call<Account>('PATCH', '/api/v1/account/settings', { keep_server_history: keepServerHistory }),
  deleteServerHistory: () => call<void>('DELETE', '/api/v1/account/history'),
  deleteAccount: async () => {
    await call<void>('DELETE', '/api/v1/account');
    await setToken(null);
  },
  register: async (email: string, password: string) => {
    const s = await call<SessionOut>('POST', '/api/v1/auth/register', { email, password });
    await setToken(s.token);
    return s;
  },
  login: async (email: string, password: string) => {
    const s = await raw<SessionOut>('POST', '/api/v1/auth/login', { email, password });
    await setToken(s.token);
    return s;
  },
  logout: async () => {
    try {
      await call<void>('POST', '/api/v1/auth/logout');
    } finally {
      await setToken(null);
    }
  },
  connections: () => call<Connection[]>('GET', '/api/v1/connections'),
  startConnection: (platform: string) =>
    call<{ authorize_url: string; return_url: string; verifier: string }>('POST', `/api/v1/connections/${platform}/start`),
  completeConnection: (platform: string, handoff: string, verifier: string) =>
    call<{ platform: string; connected: boolean; username: string | null }>('POST', `/api/v1/connections/${platform}/complete`, { handoff, verifier }),
  disconnect: (platform: string) => call<void>('DELETE', `/api/v1/connections/${platform}`),
};
