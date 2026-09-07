// Offline store — web build. expo-sqlite's modern async API
// (openDatabaseAsync, used by db.ts) has no browser implementation in this
// Expo version (only its legacy WebSQL-era API ships a .web.js, and WebSQL
// itself is gone from every current browser) — so the native db.ts can't
// run here. This is a straight IndexedDB reimplementation of the exact same
// exported functions db.ts provides; Metro picks this file automatically on
// web builds, so every importer (sync.ts, the screens) needs no changes.
//
// Row counts for a field survey app are small (hundreds, not millions), so
// "read the whole store into memory and filter/sort in JS" is simpler than
// IndexedDB's cursor/index machinery and plenty fast enough.

const DB_NAME = 'geoplan';
const DB_VERSION = 2;
const STORES = ['outbox', 'assets', 'routes', 'kv', 'drafts'] as const;

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('outbox')) {
        db.createObjectStore('outbox', { keyPath: 'client_id' });
      }
      if (!db.objectStoreNames.contains('assets')) {
        db.createObjectStore('assets', { keyPath: 'client_id' });
      }
      if (!db.objectStoreNames.contains('routes')) {
        db.createObjectStore('routes', { keyPath: 'client_id' });
      }
      if (!db.objectStoreNames.contains('kv')) {
        db.createObjectStore('kv', { keyPath: 'k' });
      }
      // Local-only, never synced — see db.ts's drafts table comment.
      if (!db.objectStoreNames.contains('drafts')) {
        db.createObjectStore('drafts', { keyPath: 'building_id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function tx(store: (typeof STORES)[number], mode: IDBTransactionMode) {
  return openDb().then((db) => db.transaction(store, mode).objectStore(store));
}

function wrap<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function getAll(store: (typeof STORES)[number]): Promise<any[]> {
  return wrap((await tx(store, 'readonly')).getAll());
}

async function getOne(store: (typeof STORES)[number], key: string): Promise<any | undefined> {
  return wrap((await tx(store, 'readonly')).get(key));
}

async function put(store: (typeof STORES)[number], value: any): Promise<void> {
  await wrap((await tx(store, 'readwrite')).put(value));
}

async function del(store: (typeof STORES)[number], key: string): Promise<void> {
  await wrap((await tx(store, 'readwrite')).delete(key));
}

export async function initDb() {
  await openDb();
}

export async function saveRoute(r: {
  clientId: string; routeType: string; points: number[][]; lengthM: number;
}) {
  await put('routes', {
    client_id: r.clientId, route_type: r.routeType, points: JSON.stringify(r.points),
    length_m: r.lengthM, point_count: r.points.length, synced: 0,
    created_at: new Date().toISOString(),
  });
}

export async function listRoutes(): Promise<any[]> {
  const rows = await getAll('routes');
  return rows.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 100);
}

export async function markRouteSynced(clientId: string, serverId: string) {
  const row = await getOne('routes', clientId);
  if (row) await put('routes', { ...row, synced: 1 });
  await put('kv', { k: `srv:${clientId}`, v: serverId });
}

export async function deleteRoute(clientId: string) {
  await del('routes', clientId);
}

export async function saveDraft(d: { buildingId: string; code: string | null; attrs: any }) {
  await put('drafts', {
    building_id: d.buildingId, code: d.code ?? null,
    attrs: JSON.stringify(d.attrs), updated_at: new Date().toISOString(),
  });
}

export async function listDrafts(): Promise<any[]> {
  const rows = await getAll('drafts');
  return rows.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export async function getDraft(buildingId: string): Promise<any | undefined> {
  return getOne('drafts', buildingId);
}

export async function deleteDraft(buildingId: string) {
  await del('drafts', buildingId);
}

export function newId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export type OutboxRow = {
  client_id: string; kind: string; payload: string;
  parent_client_id: string | null; status: string; error: string | null;
  bytes: number | null;
  created_at: string;
};

export async function enqueue(op: {
  clientId: string; kind: string; payload: any; parentClientId?: string;
}) {
  await put('outbox', {
    client_id: op.clientId, kind: op.kind, payload: JSON.stringify(op.payload),
    parent_client_id: op.parentClientId ?? null, status: 'pending', error: null, bytes: null,
    created_at: new Date().toISOString(),
  });
}

export async function saveAsset(a: {
  clientId: string; kind: string; lat: number; lon: number; accuracy: number;
  label: string; sub?: string;
}) {
  await put('assets', {
    client_id: a.clientId, kind: a.kind, lat: a.lat, lon: a.lon, accuracy: a.accuracy,
    label: a.label, sub: a.sub ?? '', synced: 0, created_at: new Date().toISOString(),
  });
}

export async function pending(): Promise<OutboxRow[]> {
  const rows = await getAll('outbox');
  return rows
    .filter((r) => r.status === 'pending' || r.status === 'error')
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

// Every outbox row regardless of status — see db.ts's listAllOutbox comment.
export async function listAllOutbox(): Promise<OutboxRow[]> {
  const rows = await getAll('outbox');
  return rows.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 1000);
}

export async function setStatus(clientId: string, status: string, error?: string, bytes?: number) {
  const row = await getOne('outbox', clientId);
  if (row) await put('outbox', { ...row, status, error: error ?? null, bytes: bytes ?? row.bytes ?? null });
}

// See db.ts's retryRows comment.
export async function retryRows(clientIds: string[]) {
  for (const id of clientIds) {
    const row = await getOne('outbox', id);
    if (row) await put('outbox', { ...row, status: 'pending', error: null });
  }
}

export async function mapServerId(clientId: string, serverId: string) {
  const row = await getOne('assets', clientId);
  if (row) await put('assets', { ...row, synced: 1, server_id: serverId });
  await put('kv', { k: `srv:${clientId}`, v: serverId });
}

export async function serverIdFor(clientId: string): Promise<string | null> {
  const row = await getOne('kv', `srv:${clientId}`);
  return row?.v ?? null;
}

export async function listAssets(): Promise<any[]> {
  const rows = await getAll('assets');
  return rows.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 200);
}

export async function deleteAsset(clientId: string) {
  await del('assets', clientId);
}

// Repositioning a capture that's already visible locally — updates the
// cached row so the map/list reflect the new spot immediately, regardless
// of whether it's synced yet.
export async function updateAssetPosition(clientId: string, lat: number, lon: number) {
  const row = await getOne('assets', clientId);
  if (row) await put('assets', { ...row, lat, lon });
}

// Rewrites a still-queued outbox payload in place — used when a capture is
// dragged before it's ever synced, so the eventual create request carries
// the corrected coordinates instead of the original (now stale) tap
// location. No-ops if the op already went out (nothing left to rewrite).
export async function updateOutboxPayload(clientId: string, patch: (payload: any) => any) {
  const row = await getOne('outbox', clientId);
  if (!row) return;
  const payload = patch(JSON.parse(row.payload));
  await put('outbox', { ...row, payload: JSON.stringify(payload) });
}

// Cancels a not-yet-synced capture (removes it from the outbox so it's never
// replayed). No-ops harmlessly if the row is already 'done' or gone.
export async function deleteOutbox(clientId: string) {
  await del('outbox', clientId);
}

export async function pendingCount(): Promise<number> {
  return (await pending()).length;
}

export async function kvGet(k: string): Promise<string | null> {
  const row = await getOne('kv', k);
  return row?.v ?? null;
}

export async function kvSet(k: string, v: string) {
  await put('kv', { k, v });
}
