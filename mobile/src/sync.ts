// Sync engine: replays the offline outbox to the API when a connection is
// available. Parents (manholes, buildings) go first; media second, once its
// parent has a server id. Every create carries its client_id, so replaying a
// queued op is idempotent — the API returns the same record, never a duplicate.
import { authed } from './auth';
import { pending, setStatus, mapServerId, serverIdFor, markRouteSynced } from './db';

export async function flush(projectId: string): Promise<{ done: number; failed: number }> {
  const ops = await pending();
  let done = 0, failed = 0;

  // Pass 1 — parents.
  for (const op of ops) {
    if (op.kind === 'media') continue;
    try {
      const payload = JSON.parse(op.payload);
      if (op.kind === 'manhole') {
        const res = await authed(`/api/v1/projects/${projectId}/mobile/manholes`, {
          method: 'POST', body: JSON.stringify({ ...payload, client_id: op.client_id }),
        });
        if (!res.ok) throw new Error(await msg(res));
        const body = await res.json();
        await mapServerId(op.client_id, body.id);
      } else if (op.kind === 'building_photo') {
        const res = await authed(`/api/v1/projects/${projectId}/mobile/building-photos`, {
          method: 'POST', body: JSON.stringify({ ...payload, client_id: op.client_id }),
        });
        if (!res.ok) throw new Error(await msg(res));
        const body = await res.json();
        await mapServerId(op.client_id, body.id);
      } else if (op.kind === 'building') {
        const res = await authed(
          `/api/v1/projects/${projectId}/mobile/buildings/${payload.buildingId}`, {
            method: 'PATCH', body: JSON.stringify(payload.attrs),
          });
        if (!res.ok) throw new Error(await msg(res));
        // Buildings are existing records being field-updated (not created), so
        // there's no fresh server id to capture — reuse the building's own id
        // to flip the locally-saved asset row to "synced" for the recent
        // captures list / map badge.
        await mapServerId(op.client_id, payload.buildingId);
      } else if (op.kind === 'route') {
        const res = await authed(`/api/v1/projects/${projectId}/mobile/routes`, {
          method: 'POST', body: JSON.stringify({ ...payload, client_id: op.client_id }),
        });
        if (!res.ok) throw new Error(await msg(res));
        const body = await res.json();
        await markRouteSynced(op.client_id, body.id);
      } else if (op.kind === 'manhole_reposition') {
        // Dragging an already-synced manhole/handhole to a new spot. Needs
        // its parent's server id, same pattern as media below — if the
        // parent hasn't synced yet, this shouldn't have been queued at all
        // (the reposition rewrites the still-pending create payload in
        // place instead), but skip-and-retry defensively either way.
        const serverId = await serverIdFor(payload.manholeClientId);
        if (!serverId) continue;
        const res = await authed(
          `/api/v1/projects/${projectId}/mobile/manholes/${serverId}`, {
            method: 'PATCH', body: JSON.stringify({ lon: payload.lon, lat: payload.lat }),
          });
        if (!res.ok) throw new Error(await msg(res));
      } else if (op.kind === 'manhole_delete') {
        const serverId = await serverIdFor(payload.manholeClientId);
        if (!serverId) continue;
        const res = await authed(
          `/api/v1/projects/${projectId}/mobile/manholes/${serverId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await msg(res));
      }
      await setStatus(op.client_id, 'done');
      done++;
    } catch (e: any) {
      await setStatus(op.client_id, 'error', String(e?.message ?? e));
      failed++;
    }
  }

  // Pass 2 — media (needs its parent's server id).
  for (const op of ops) {
    if (op.kind !== 'media') continue;
    try {
      const p = JSON.parse(op.payload);
      const entityId = p.entityId ?? (op.parent_client_id
        ? await serverIdFor(op.parent_client_id) : null);
      if (!entityId) { continue; }  // parent not synced yet; try next round

      const reqRes = await authed(
        `/api/v1/projects/${projectId}/mobile/media/request-upload`, {
          method: 'POST', body: JSON.stringify({
            entity_type: p.entityType, entity_id: entityId, kind: p.kind,
            content_type: p.contentType, client_id: op.client_id,
            captured_lat: p.lat, captured_lon: p.lon,
          }),
        });
      if (!reqRes.ok) throw new Error(await msg(reqRes));
      const { id, upload_url } = await reqRes.json();
      if (!upload_url) throw new Error('No upload URL (object storage unreachable)');

      const fileBlob = await (await fetch(p.uri)).blob();
      const put = await fetch(upload_url, {
        method: 'PUT', headers: { 'Content-Type': p.contentType }, body: fileBlob,
      });
      if (!put.ok) throw new Error(`Upload failed (${put.status})`);

      await authed(`/api/v1/projects/${projectId}/mobile/media/${id}/confirm`, {
        method: 'POST', body: JSON.stringify({ size_bytes: fileBlob.size ?? null }),
      });
      await setStatus(op.client_id, 'done');
      done++;
    } catch (e: any) {
      await setStatus(op.client_id, 'error', String(e?.message ?? e));
      failed++;
    }
  }
  return { done, failed };
}

async function msg(res: Response): Promise<string> {
  try { return (await res.json()).detail ?? `HTTP ${res.status}`; }
  catch { return `HTTP ${res.status}`; }
}
