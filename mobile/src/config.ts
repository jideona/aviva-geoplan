// API address is an in-app, persisted setting so you can change it on the phone
// (e.g. when your Mac's DHCP IP changes) without editing code. Default below is
// used until you set one in the app.
import * as SecureStore from 'expo-secure-store';

export const DEFAULT_API_BASE = 'http://192.168.1.236:8000';

let _apiBase = DEFAULT_API_BASE;

export function getApiBase(): string { return _apiBase; }

export async function loadApiBase(): Promise<string> {
  const v = await SecureStore.getItemAsync('apiBase');
  if (v) _apiBase = v;
  return _apiBase;
}

export async function setApiBase(v: string): Promise<void> {
  _apiBase = v.trim().replace(/\/+$/, '');   // strip trailing slashes
  await SecureStore.setItemAsync('apiBase', _apiBase);
}

// Colour/spacing/type tokens moved to ../theme.ts (Aviva Networx Design
// System v1.0, Vol.1/2/4.1) — import COLOR/SPACE/etc. from there instead
// of BRAND, which no longer exists.
