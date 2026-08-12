// Web counterpart to auth.ts. expo-secure-store's web implementation calls
// into an internal method (`getValueWithKeyAsync`) that isn't present in the
// installed version, throwing on every call — confirmed by actually running
// the exported PWA in a browser, not assumed. Same fix pattern as db.web.ts:
// a same-signature reimplementation over a browser-native API, here
// localStorage instead of IndexedDB. Metro resolves this file automatically
// on web builds; every caller just imports '../auth' and gets the right one.
import { getApiBase } from './config';

let accessToken: string | null = null;
let refreshToken: string | null = null;

function getItem(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function setItem(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch {}
}

function removeItem(key: string) {
  try { window.localStorage.removeItem(key); } catch {}
}

export async function loadTokens() {
  accessToken = getItem('access');
  refreshToken = getItem('refresh');
  return !!accessToken;
}

async function setTokens(access: string | null, refresh: string | null) {
  accessToken = access; refreshToken = refresh;
  if (access) setItem('access', access);
  else removeItem('access');
  if (refresh) setItem('refresh', refresh);
  else removeItem('refresh');
}

export async function login(email: string, password: string) {
  const res = await fetch(`${getApiBase()}/api/v1/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    let detail = 'Sign in failed';
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(detail);
  }
  const body = await res.json();
  await setTokens(body.access_token, body.refresh_token);
}

export async function logout() { await setTokens(null, null); }

async function refresh(): Promise<boolean> {
  if (!refreshToken) return false;
  const res = await fetch(`${getApiBase()}/api/v1/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) { await setTokens(null, null); return false; }
  const body = await res.json();
  await setTokens(body.access_token, body.refresh_token ?? refreshToken);
  return true;
}

// Authenticated fetch with one refresh-and-retry on 401.
export async function authed(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let res = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  if (res.status === 401 && await refresh()) {
    headers.set('Authorization', `Bearer ${accessToken}`);
    res = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  }
  return res;
}

export function isAuthed() { return !!accessToken; }
