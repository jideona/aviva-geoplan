// JWT auth against the GeoPlan API, with token storage in the device keychain
// and transparent refresh. Tokens persist so the surveyor stays logged in
// offline for the day.
import * as SecureStore from 'expo-secure-store';
import { getApiBase } from './config';

let accessToken: string | null = null;
let refreshToken: string | null = null;

export async function loadTokens() {
  accessToken = await SecureStore.getItemAsync('access');
  refreshToken = await SecureStore.getItemAsync('refresh');
  return !!accessToken;
}

async function setTokens(access: string | null, refresh: string | null) {
  accessToken = access; refreshToken = refresh;
  if (access) await SecureStore.setItemAsync('access', access);
  else await SecureStore.deleteItemAsync('access');
  if (refresh) await SecureStore.setItemAsync('refresh', refresh);
  else await SecureStore.deleteItemAsync('refresh');
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
