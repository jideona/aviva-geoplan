// Client-side view of the server's role/permission model (backend:
// app/core/permissions.py). This is for deciding what to show/hide/enable —
// the server remains the sole authority for whether an action is actually
// allowed, so every gate here is a UX convenience, never a security
// boundary on its own.
//
// The cached copy is for offline/startup display only: it's refreshed
// from /auth/me on login, whenever the access token gets silently
// refreshed (auth.ts's refresh-and-retry — if enough time passed for the
// access token to expire, permissions may have changed too), and whenever
// the app comes back to the foreground while online. It is never treated
// as permanently authoritative.
import { authed, onTokenRefreshed } from './auth';
import { kvGet, kvSet } from './db';

export type Permission =
  | 'project:create' | 'project:edit' | 'project:view'
  | 'gis:import' | 'gis:edit'
  | 'building:edit' | 'building:field_update'
  | 'export' | 'audit:view' | 'user:manage' | 'inventory:manage' | 'task:manage'
  | 'field:capture' | 'field_data:view' | 'field_activity:view' | 'qa:review';

type Cached = { roles: string[]; permissions: Permission[] };

let cache: Cached = { roles: [], permissions: [] };
let loaded = false;

const KV_KEY = 'authz'; // roles+permissions, JSON — separate from the access/refresh tokens in SecureStore

// Read whatever was cached from the last successful refresh, so a screen
// rendered before the network round-trip completes (or fully offline)
// still has last-known roles/permissions instead of defaulting to "no
// permissions" and hiding everything.
export async function loadCachedPermissions(): Promise<Cached> {
  if (!loaded) {
    try {
      const raw = await kvGet(KV_KEY);
      if (raw) cache = JSON.parse(raw);
    } catch {
      // Corrupt/missing cache — fall through with the empty default;
      // refreshPermissions() will fix it as soon as it can reach the server.
    }
    loaded = true;
  }
  return cache;
}

// Pulls the current roles/permissions from the server and updates the
// cache. Called after login, after a silent token refresh, and on
// foreground-resume — never gates a security-sensitive action by itself,
// just keeps what the UI shows in sync with the server's view. Returns
// false (keeping the existing cache) if the server can't be reached, e.g.
// offline — that's expected and not an error the caller needs to surface.
export async function refreshPermissions(): Promise<boolean> {
  try {
    const res = await authed('/api/v1/auth/me');
    if (!res.ok) return false;
    const body = await res.json();
    cache = { roles: body.roles ?? [], permissions: body.permissions ?? [] };
    loaded = true;
    await kvSet(KV_KEY, JSON.stringify(cache));
    return true;
  } catch {
    return false;
  }
}

export function clearPermissions() {
  cache = { roles: [], permissions: [] };
  loaded = true;
  kvSet(KV_KEY, JSON.stringify(cache)).catch(() => {});
}

export function hasPermission(perm: Permission): boolean {
  return cache.permissions.includes(perm);
}

export function getRoles(): string[] {
  return cache.roles;
}

// Keeps the cache in step with auth.ts's transparent 401-triggered token
// refresh, without auth.ts needing to know permissions.ts exists.
onTokenRefreshed(() => { refreshPermissions().catch(() => {}); });
