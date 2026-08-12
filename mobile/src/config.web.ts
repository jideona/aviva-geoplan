// Web counterpart to config.ts — same reasoning as auth.web.ts: expo-secure-
// store's web implementation throws, so this persists the API base URL in
// localStorage instead. Metro resolves this automatically on web builds.
export const DEFAULT_API_BASE = 'https://api.avivanetworx.com';

let _apiBase = DEFAULT_API_BASE;

export function getApiBase(): string { return _apiBase; }

export async function loadApiBase(): Promise<string> {
  try {
    const v = window.localStorage.getItem('apiBase');
    if (v) _apiBase = v;
  } catch {}
  return _apiBase;
}

export async function setApiBase(v: string): Promise<void> {
  _apiBase = v.trim().replace(/\/+$/, '');   // strip trailing slashes
  try { window.localStorage.setItem('apiBase', _apiBase); } catch {}
}

// Colour/spacing/type tokens moved to ../theme.ts (Aviva Networx Design
// System v1.0, Vol.1/2/4.1) — import COLOR/SPACE/etc. from there instead
// of BRAND, which no longer exists.
