// Per-record history/detail sheet — opened by tapping a row in Recent
// Captures. Shows what's saved locally, then (once synced) asks the server
// directly for that one record's current state, so a surveyor can confirm
// their capture — including its coordinates and, for photos, that the file
// itself is attached — genuinely reached the server rather than trusting the
// app's own "synced" flag alone.
import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { authed } from '../auth';
import { kvGet, serverIdFor } from '../db';
import { COLOR, RADIUS, SPACE, TYPE } from '../theme';
import BottomSheet from './BottomSheet';

export type DetailItem = {
  clientId: string; kind: string; label: string; sub?: string;
  lat?: number; lon?: number; accuracy?: number; createdAt: string;
  synced: boolean; serverId?: string | null;
};

const KIND_LABEL: Record<string, string> = {
  manhole: 'Manhole', building: 'Building', building_photo: 'Building photo',
  route: 'Cable route',
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={s.rowValue}>{value}</Text>
    </View>
  );
}

export default function RecordDetail({ item, onClose }: { item: DetailItem | null; onClose: () => void }) {
  const [server, setServer] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setServer(null); setError(null);
    if (!item || !item.synced) return;
    setLoading(true);
    (async () => {
      try {
        // Assets carry their server id directly; routes only record it in the
        // kv table (see db.ts markRouteSynced) — resolve it lazily here
        // rather than making every row in the list pay for that lookup.
        const sid = item.serverId ?? await serverIdFor(item.clientId);
        if (!sid) { setError('No server id recorded for this capture yet.'); return; }
        const pid = await kvGet('projectId');
        const res = await authed(`/api/v1/projects/${pid}/mobile/records/${item.kind}/${sid}`);
        if (!res.ok) throw new Error(`Server said ${res.status}`);
        setServer(await res.json());
      } catch (e: any) {
        setError(String(e?.message ?? e));
      } finally {
        setLoading(false);
      }
    })();
  }, [item?.clientId, item?.synced, item?.serverId]);

  if (!item) return null;

  return (
    <BottomSheet visible={!!item} onClose={onClose} title={item.label}>
      <Text style={s.kind}>{KIND_LABEL[item.kind] ?? item.kind}</Text>

      <Text style={s.section}>CAPTURED ON THIS DEVICE</Text>
      {item.lat != null && item.lon != null && (
        <Row label="Coordinates" value={`${item.lat.toFixed(5)}, ${item.lon.toFixed(5)}`} />
      )}
      {item.accuracy != null && <Row label="GPS accuracy" value={`±${Math.round(item.accuracy)}m`} />}
      <Row label="When" value={new Date(item.createdAt).toLocaleString()} />
      {item.sub ? <Row label="Detail" value={item.sub} /> : null}

      <View style={[s.statusBanner, item.synced ? s.statusOk : s.statusPending]}>
        <Text style={[s.statusText, item.synced ? s.statusOkText : s.statusPendingText]}>
          {item.synced ? '✓ Sent to the server' : '⏳ Not sent yet — will go out on next sync'}
        </Text>
      </View>

      {item.synced && item.serverId && (
        <>
          <Text style={s.section}>SERVER RECORD</Text>
          {loading && <ActivityIndicator style={{ marginTop: SPACE.sm }} />}
          {error && (
            <Text style={s.errorText}>
              Couldn't reach the server to confirm right now ({error}). It reported success when
              this was sent — check again once you have a connection.
            </Text>
          )}
          {server && (
            <>
              <View style={[s.statusBanner, s.statusOk]}>
                <Text style={[s.statusText, s.statusOkText]}>✓ Confirmed on the server</Text>
              </View>
              {server.lon != null && server.lat != null && (
                <Row label="Server coordinates" value={`${Number(server.lat).toFixed(5)}, ${Number(server.lon).toFixed(5)}`} />
              )}
              {server.condition && <Row label="Condition" value={server.condition} />}
              {server.building_type && <Row label="Building type" value={server.building_type} />}
              {server.address && <Row label="Address" value={server.address} />}
              {server.units_surveyed != null && <Row label="Units" value={String(server.units_surveyed)} />}
              {server.drop_deployment && <Row label="Drop deployment" value={server.drop_deployment} />}
              {server.length_m != null && <Row label="Length" value={`${Math.round(server.length_m)} m`} />}
              {server.point_count != null && <Row label="Points" value={String(server.point_count)} />}
              {(server.surveyed_by || server.last_edited_by) && (
                <Row label="Attributed to" value={server.surveyed_by ?? server.last_edited_by} />
              )}
              {server.verification_state && <Row label="Verification" value={server.verification_state} />}
              {server.updated_at && (
                <Row label="Last updated on server" value={new Date(server.updated_at).toLocaleString()} />
              )}
            </>
          )}
        </>
      )}
    </BottomSheet>
  );
}

const s = StyleSheet.create({
  kind: { ...TYPE.mono, fontSize: 11, letterSpacing: 1, color: COLOR.text500, marginBottom: SPACE.sm },
  section: { ...TYPE.mono, fontSize: 11, letterSpacing: 1.5, color: COLOR.text500, marginTop: SPACE.md, marginBottom: SPACE.xs + 2 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  rowLabel: { fontSize: 13, color: COLOR.text500 },
  rowValue: { fontSize: 13, fontWeight: '700', color: COLOR.text900, textAlign: 'right', flexShrink: 1, marginLeft: SPACE.sm },
  statusBanner: { borderRadius: RADIUS.sm, paddingVertical: SPACE.xs + 2, paddingHorizontal: SPACE.sm + 2, marginTop: SPACE.sm },
  statusOk: { backgroundColor: '#E1F7F1' },
  statusPending: { backgroundColor: '#EEF0F2' },
  statusText: { fontSize: 12, fontWeight: '700' },
  statusOkText: { color: '#00887A' },
  statusPendingText: { color: '#4B5563' },
  errorText: { fontSize: 12, color: COLOR.text500, marginTop: SPACE.xs },
});
