// Offline store. Everything a surveyor captures lands here first (with its GPS
// fix) and is replayed to the API by the sync engine when a connection returns.
import * as SQLite from 'expo-sqlite';

let db: SQLite.SQLiteDatabase | null = null;

export async function initDb() {
  db = await SQLite.openDatabaseAsync('geoplan.db');
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS outbox (
      client_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL,             -- 'manhole' | 'building' | 'media'
      payload TEXT NOT NULL,          -- JSON
      parent_client_id TEXT,          -- media -> its asset's client_id
      status TEXT NOT NULL DEFAULT 'pending',   -- pending|syncing|done|error
      error TEXT,
      -- Set only for a media op that finished uploading (the actual byte
      -- size the sync engine already measures via fileBlob.size before
      -- discarding it) — lets the Uploaded Data screen show real "GB
      -- uploaded" instead of a placeholder.
      bytes INTEGER,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS assets (
      client_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL,
      lat REAL, lon REAL, accuracy REAL,
      label TEXT, sub TEXT,
      synced INTEGER NOT NULL DEFAULT 0,
      server_id TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS routes (
      client_id TEXT PRIMARY KEY,
      route_type TEXT NOT NULL,
      points TEXT NOT NULL,           -- JSON [[lon,lat],...]
      length_m REAL, point_count INTEGER,
      synced INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
    -- Local-only, never synced: an in-progress Update Building form the
    -- surveyor chose to save without submitting (redesign's "Save draft" /
    -- "Resume draft"). Keyed by building_id so there's at most one draft
    -- per building — picking it again just resumes/overwrites the draft.
    CREATE TABLE IF NOT EXISTS drafts (
      building_id TEXT PRIMARY KEY,
      code TEXT,
      attrs TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);
}

export async function saveRoute(r: {
  clientId: string; routeType: string; points: number[][]; lengthM: number;
}) {
  await conn().runAsync(
    `INSERT OR REPLACE INTO routes (client_id, route_type, points, length_m, point_count, synced, created_at)
     VALUES (?, ?, ?, ?, ?, 0, ?)`,
    [r.clientId, r.routeType, JSON.stringify(r.points), r.lengthM,
     r.points.length, new Date().toISOString()]
  );
}

export async function listRoutes(): Promise<any[]> {
  return conn().getAllAsync(`SELECT * FROM routes ORDER BY created_at DESC LIMIT 100`);
}

export async function markRouteSynced(clientId: string, serverId: string) {
  await conn().runAsync(`UPDATE routes SET synced = 1 WHERE client_id = ?`, [clientId]);
  await conn().runAsync(`INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)`,
    [`srv:${clientId}`, serverId]);
}

export async function deleteRoute(clientId: string) {
  await conn().runAsync(`DELETE FROM routes WHERE client_id = ?`, [clientId]);
}

function conn(): SQLite.SQLiteDatabase {
  if (!db) throw new Error('DB not initialised');
  return db;
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
  await conn().runAsync(
    `INSERT OR REPLACE INTO outbox (client_id, kind, payload, parent_client_id, status, created_at)
     VALUES (?, ?, ?, ?, 'pending', ?)`,
    [op.clientId, op.kind, JSON.stringify(op.payload), op.parentClientId ?? null,
     new Date().toISOString()]
  );
}

export async function saveAsset(a: {
  clientId: string; kind: string; lat: number; lon: number; accuracy: number;
  label: string; sub?: string;
}) {
  await conn().runAsync(
    `INSERT OR REPLACE INTO assets (client_id, kind, lat, lon, accuracy, label, sub, synced, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)`,
    [a.clientId, a.kind, a.lat, a.lon, a.accuracy, a.label, a.sub ?? '',
     new Date().toISOString()]
  );
}

export async function saveDraft(d: { buildingId: string; code: string | null; attrs: any }) {
  await conn().runAsync(
    `INSERT OR REPLACE INTO drafts (building_id, code, attrs, updated_at) VALUES (?, ?, ?, ?)`,
    [d.buildingId, d.code ?? null, JSON.stringify(d.attrs), new Date().toISOString()]
  );
}

export async function listDrafts(): Promise<{ building_id: string; code: string | null; attrs: string; updated_at: string }[]> {
  return conn().getAllAsync(`SELECT * FROM drafts ORDER BY updated_at DESC`);
}

export async function getDraft(buildingId: string) {
  return conn().getFirstAsync<{ building_id: string; code: string | null; attrs: string; updated_at: string }>(
    `SELECT * FROM drafts WHERE building_id = ?`, [buildingId]);
}

export async function deleteDraft(buildingId: string) {
  await conn().runAsync(`DELETE FROM drafts WHERE building_id = ?`, [buildingId]);
}

export async function pending(): Promise<OutboxRow[]> {
  return conn().getAllAsync<OutboxRow>(
    `SELECT * FROM outbox WHERE status IN ('pending','error') ORDER BY created_at`);
}

// Every outbox row regardless of status — the Uploaded Data screen's ledger
// (pending() above deliberately excludes 'done' rows, since the sync engine
// only needs the unfinished ones).
export async function listAllOutbox(): Promise<OutboxRow[]> {
  return conn().getAllAsync<OutboxRow>(`SELECT * FROM outbox ORDER BY created_at DESC LIMIT 1000`);
}

export async function setStatus(clientId: string, status: string, error?: string, bytes?: number) {
  await conn().runAsync(`UPDATE outbox SET status = ?, error = ?, bytes = COALESCE(?, bytes) WHERE client_id = ?`,
    [status, error ?? null, bytes ?? null, clientId]);
}

// Re-queues specific rows for the next flush() — "Retry upload" on a failed
// batch, restricted to just its rejected records rather than everything
// pending (flush() already replays 'error' rows too, but this also clears
// the stale error message so a still-in-flight retry doesn't show it).
export async function retryRows(clientIds: string[]) {
  for (const id of clientIds) {
    await conn().runAsync(`UPDATE outbox SET status = 'pending', error = NULL WHERE client_id = ?`, [id]);
  }
}

export async function mapServerId(clientId: string, serverId: string) {
  await conn().runAsync(`UPDATE assets SET synced = 1, server_id = ? WHERE client_id = ?`,
    [serverId, clientId]);
  await conn().runAsync(`INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)`,
    [`srv:${clientId}`, serverId]);
}

export async function serverIdFor(clientId: string): Promise<string | null> {
  const r = await conn().getFirstAsync<{ v: string }>(
    `SELECT v FROM kv WHERE k = ?`, [`srv:${clientId}`]);
  return r?.v ?? null;
}

export async function listAssets(): Promise<any[]> {
  return conn().getAllAsync(`SELECT * FROM assets ORDER BY created_at DESC LIMIT 200`);
}

export async function deleteAsset(clientId: string) {
  await conn().runAsync(`DELETE FROM assets WHERE client_id = ?`, [clientId]);
}

// Repositioning a capture that's already visible locally — updates the
// cached row so the map/list reflect the new spot immediately, regardless
// of whether it's synced yet.
export async function updateAssetPosition(clientId: string, lat: number, lon: number) {
  await conn().runAsync(`UPDATE assets SET lat = ?, lon = ? WHERE client_id = ?`,
    [lat, lon, clientId]);
}

// Rewrites a still-queued outbox payload in place — used when a capture is
// dragged before it's ever synced, so the eventual create request carries
// the corrected coordinates instead of the original (now stale) tap
// location. No-ops if the op already went out (nothing left to rewrite).
export async function updateOutboxPayload(clientId: string, patch: (payload: any) => any) {
  const row = await conn().getFirstAsync<{ payload: string }>(
    `SELECT payload FROM outbox WHERE client_id = ?`, [clientId]);
  if (!row) return;
  const payload = patch(JSON.parse(row.payload));
  await conn().runAsync(`UPDATE outbox SET payload = ? WHERE client_id = ?`,
    [JSON.stringify(payload), clientId]);
}

// Cancels a not-yet-synced capture (removes it from the outbox so it's never
// replayed). No-ops harmlessly if the row is already 'done' or gone.
export async function deleteOutbox(clientId: string) {
  await conn().runAsync(`DELETE FROM outbox WHERE client_id = ?`, [clientId]);
}

export async function pendingCount(): Promise<number> {
  const r = await conn().getFirstAsync<{ n: number }>(
    `SELECT COUNT(*) n FROM outbox WHERE status IN ('pending','error')`);
  return r?.n ?? 0;
}

export async function kvGet(k: string): Promise<string | null> {
  const r = await conn().getFirstAsync<{ v: string }>(`SELECT v FROM kv WHERE k = ?`, [k]);
  return r?.v ?? null;
}
export async function kvSet(k: string, v: string) {
  await conn().runAsync(`INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)`, [k, v]);
}
