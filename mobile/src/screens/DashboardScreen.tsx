// District Dashboard — the former single Home screen, split per the Claude
// Design redesign ("Field Survey App Redesign.dc.html", screen 4). Reached
// after a project is picked on ProjectListScreen; the three capture tiles
// and Recent Captures list that used to live on Home are here now.
import { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import NetInfo from '@react-native-community/netinfo';
import { listAssets, listRoutes, deleteAsset, deleteRoute, deleteOutbox, pendingCount, listDrafts, kvGet, kvSet } from '../db';
import { runSync } from '../sync';
import { notify } from '../notify';
import { confirmAction } from '../confirm';
import { logout, authed } from '../auth';
import { hasBiometricHardware, isBiometricLockEnabled, setBiometricLockEnabled, supportedTypeLabel } from '../biometrics';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH, isWeb, STATUS } from '../theme';
import { pinStatus, pinShape, type PinStatusName } from '../pinStatus';
import SwipeableRow from '../components/SwipeableRow';
import BottomSheet from '../components/BottomSheet';
import RecordDetail, { type DetailItem } from '../components/RecordDetail';

type CaptureItem = {
  clientId: string; isRoute: boolean; label: string; meta: string;
  status: PinStatusName; shape: 'square' | 'triangle' | 'circle' | 'house'; synced: boolean; createdAt: string;
  // Carried through to RecordDetail when a row is tapped — a capture's full
  // history/detail view, including the server's own confirmation of it.
  kind: string; sub?: string; lat?: number; lon?: number; accuracy?: number;
  serverId?: string | null;
};

// Tints for the status pill — companions to theme.ts's solid STATUS colours
// (used for map pins); pills need a light background + dark-on-light text
// version of the same three meanings, so kept local to this one usage.
const PILL: Record<PinStatusName, { bg: string; fg: string; label: string }> = {
  synced: { bg: '#E1F7F1', fg: '#00887A', label: 'SYNCED' },
  pending: { bg: '#EEF0F2', fg: '#4B5563', label: 'PENDING' },
  flagged: { bg: '#FDECE5', fg: '#E8590C', label: 'ATTENTION' },
};

function dayHeader(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const day = d.toLocaleDateString(undefined, { day: 'numeric', month: 'long' }).toUpperCase();
  return isToday ? `TODAY, ${day}` : day;
}

export default function DashboardScreen({
  onOpenMap, onCapture, onSwitchProject, onLogout, onBioLockChanged, onResumeDraft, onOpenUploadedData,
}: {
  onOpenMap: () => void;
  onCapture: (kind: 'manhole' | 'building' | 'building_photo') => void;
  onSwitchProject: () => void;
  onLogout: () => void;
  onBioLockChanged?: (on: boolean) => void;
  // Jumps straight into the Update Building sheet with this draft's saved
  // values pre-loaded, skipping the GPS-proximity search — wired to the
  // Quick Actions "Resume draft" tile below.
  onResumeDraft: (d: { buildingId: string; code: string | null }) => void;
  // Wired by App.tsx to the Uploaded Data screen (redesign screen 5).
  // Kept optional (with a "coming soon" fallback below) so this screen
  // still compiles/works standalone if that wiring is ever missing.
  onOpenUploadedData?: () => void;
}) {
  const [projectName, setProjectName] = useState('');
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [assets, setAssets] = useState<any[]>([]);
  const [routes, setRoutes] = useState<any[]>([]);
  const [pend, setPend] = useState(0);
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<DetailItem | null>(null);
  const [bioAvailable, setBioAvailable] = useState(false);
  const [bioLabel, setBioLabel] = useState('Device biometrics');
  const [bioOn, setBioOn] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  // District-progress KPI: total buildings in the project vs how many carry
  // a mobile-submitted `condition` (Task #12's field — the one signal that
  // distinguishes "surveyed" from just "imported footprint"). null while
  // unknown (not yet loaded, or offline) rather than 0/0, so the ring shows
  // a dash instead of a misleading "0%".
  const [buildingTotal, setBuildingTotal] = useState<number | null>(null);
  const [buildingSurveyed, setBuildingSurveyed] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<{ building_id: string; code: string | null; updated_at: string }[]>([]);
  const [draftPicker, setDraftPicker] = useState(false);

  useEffect(() => {
    (async () => {
      const avail = await hasBiometricHardware();
      setBioAvailable(avail);
      if (avail) {
        setBioLabel(await supportedTypeLabel());
        setBioOn(await isBiometricLockEnabled());
      }
    })();
  }, []);

  async function toggleBioLock() {
    const next = !bioOn;
    await setBiometricLockEnabled(next);
    setBioOn(next);
    onBioLockChanged?.(next);
    notify(`${bioLabel} lock`, next
      ? `Turned on — you'll unlock GeoPlan with ${bioLabel} from now on.`
      : 'Turned off.');
  }

  const reload = useCallback(async () => {
    setAssets(await listAssets());
    setRoutes(await listRoutes());
    setPend(await pendingCount());
    setDrafts(await listDrafts());
    const pid = await kvGet('projectId');
    setProjectId(pid);
    if (pid) setLastSync(await kvGet(`lastSync:${pid}`));
    const pname = await kvGet('projectName');
    setProjectName(pname || 'Project');
  }, []);

  // Building total/surveyed for the KPI ring — fetched once per project
  // (not on every 4s poll like reload() above), same read-only endpoint
  // MapScreen already uses for its buildings layer. Left as null (ring
  // shows a dash) if the project has no id yet or the device is offline.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await authed(`/api/v1/projects/${projectId}/buildings.geojson`);
        if (!res.ok || cancelled) return;
        const feats = ((await res.json()).features ?? []) as any[];
        if (cancelled) return;
        setBuildingTotal(feats.length);
        setBuildingSurveyed(feats.filter((f) => f.properties?.condition != null).length);
      } catch { /* offline — leave as unknown */ }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    void reload();
    const unsub = NetInfo.addEventListener((st) => setOnline(!!st.isConnected));
    const t = setInterval(reload, 4000);
    return () => { unsub(); clearInterval(t); };
  }, [reload]);

  async function sync() {
    const pid = await kvGet('projectId');
    if (!pid) { notify('Project', 'No project selected.'); return; }
    setSyncing(true);
    try {
      const r = await runSync(pid);
      const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const summary = `${stamp} · ${r.done} updated${r.failed ? `, ${r.failed} failed` : ''}`;
      setLastSync(summary);
      // Persisted (not just React state) so the Project List screen's own
      // "last synced" line — and this screen on next mount — see it too.
      // This was previously read on mount but never actually written.
      await kvSet(`lastSync:${pid}`, summary);
      if (r.failed > 0) {
        notify('Sync issue', `${r.done} sent · ${r.failed} couldn't send and will retry on the next sync.`);
      } else if (r.done > 0) {
        notify('Synced', `${projectName || 'This project'} is synced — ${r.done} update${r.done === 1 ? '' : 's'} sent.`);
      } else {
        notify('Synced', `${projectName || 'This project'} is already up to date — nothing new to send.`);
      }
      await reload();
    } catch (e: any) { notify('Sync', String(e?.message ?? e)); }
    finally { setSyncing(false); }
  }

  const captures: CaptureItem[] = [
    ...assets.map((a): CaptureItem => ({
      clientId: a.client_id, isRoute: false,
      label: a.kind === 'building_photo' ? 'Building photo' : `${a.kind} · ${a.label}`,
      meta: `${a.lat?.toFixed(5)}, ${a.lon?.toFixed(5)} · ±${Math.round(a.accuracy)}m`,
      status: pinStatus(a), shape: pinShape(a), synced: !!a.synced, createdAt: a.created_at,
      kind: a.kind, sub: a.sub, lat: a.lat, lon: a.lon, accuracy: a.accuracy,
      serverId: a.server_id ?? null,
    })),
    ...routes.map((r): CaptureItem => ({
      clientId: r.client_id, isRoute: true, label: `route · ${Math.round(r.length_m)} m`,
      meta: `${r.point_count} pts`,
      status: r.synced ? 'synced' : 'pending', shape: 'circle', synced: !!r.synced, createdAt: r.created_at,
      kind: 'route', sub: `${r.route_type ?? 'cable_route'}`, serverId: undefined,
    })),
  ].sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  // KPI ring inputs derived from the same local data the capture list uses
  // — "synced" and "flagged" here mean exactly what the pin colours mean
  // elsewhere on this screen and on the map (pinStatus.ts), so the ring
  // percentages can't drift from what a surveyor sees in Recent Captures.
  const totalCaptures = captures.length;
  const syncedCaptures = captures.filter((c) => c.synced).length;
  const flaggedCaptures = captures.filter((c) => c.status === 'flagged').length;
  const pointAssets = assets.filter((a) => a.kind === 'manhole');
  const pointAssetsSynced = pointAssets.filter((a) => !!a.synced).length;

  async function onTapResumeDraft() {
    if (drafts.length === 0) {
      notify('Drafts', "No saved drafts yet — use \u201cSave draft\u201d from the Update Building sheet.");
      return;
    }
    if (drafts.length === 1) {
      onResumeDraft({ buildingId: drafts[0].building_id, code: drafts[0].code });
      return;
    }
    setDraftPicker(true);
  }

  function onTapUploadedData() {
    if (onOpenUploadedData) onOpenUploadedData();
    else notify('Uploaded data', 'Coming soon.');
  }

  // Group into date sections for the FlatList (mono "TODAY, 2 AUGUST" headers).
  type Row = { type: 'header'; key: string; text: string } | { type: 'item'; key: string; item: CaptureItem };
  const rows: Row[] = [];
  let lastDay = '';
  for (const item of captures) {
    const day = new Date(item.createdAt).toDateString();
    if (day !== lastDay) { rows.push({ type: 'header', key: `h-${day}`, text: dayHeader(item.createdAt) }); lastDay = day; }
    rows.push({ type: 'item', key: item.clientId, item });
  }

  async function deleteItem(item: CaptureItem) {
    const ok = await confirmAction('Delete capture', item.synced
      ? 'This removes it from your device only — it already synced, so the saved record on the server is unaffected.'
      : 'This removes it from your device and cancels sending it — nothing has reached the server yet.');
    if (!ok) return;
    if (item.isRoute) await deleteRoute(item.clientId); else await deleteAsset(item.clientId);
    if (!item.synced) await deleteOutbox(item.clientId);
    await reload();
  }

  return (
    <View style={{ flex: 1, backgroundColor: COLOR.surface100 }}>
      <View style={s.header}>
        <View style={s.headerTop}>
          <Text style={s.headerTitle} numberOfLines={1}>{projectName}</Text>
          <TouchableOpacity onPress={() => setMenuOpen(true)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={s.kebab}>⋮</Text>
          </TouchableOpacity>
        </View>
        <View style={s.statusRow}>
          <View style={[s.dot, { backgroundColor: online ? COLOR.success500 : COLOR.error }]} />
          <Text style={s.statusText}>{online ? 'Online' : 'Offline'} · {pend} pending</Text>
        </View>
      </View>

      <FlatList
        data={rows}
        keyExtractor={(r) => r.key}
        contentContainerStyle={{ paddingBottom: SPACE.xl }}
        ListHeaderComponent={
          <>
            <View style={s.syncCard}>
              <View>
                <Text style={s.syncLabel}>LAST SYNC</Text>
                <Text style={s.syncValue}>{lastSync ?? 'Not synced yet'}</Text>
              </View>
              <TouchableOpacity style={s.syncBtn} onPress={sync} disabled={syncing}>
                {syncing ? <ActivityIndicator color="#fff" /> : <Text style={s.syncBtnText}>Sync now</Text>}
              </TouchableOpacity>
            </View>

            <Text style={s.sectionLabel}>DISTRICT PROGRESS</Text>
            <View style={s.kpiGrid}>
              <KpiTile icon="\u2302" label="Buildings surveyed"
                value={buildingSurveyed == null ? '\u2014' : String(buildingSurveyed)}
                unit={`/${buildingTotal == null ? '\u2014' : buildingTotal}`}
                pct={buildingTotal ? (buildingSurveyed! / buildingTotal) * 100 : 0} />
              <KpiTile icon="\u25A2" label="Manholes & handholes synced"
                value={String(pointAssetsSynced)} unit={`/${pointAssets.length}`}
                pct={pointAssets.length ? (pointAssetsSynced / pointAssets.length) * 100 : 0} />
              <KpiTile icon="\u25B3" label="Flagged \u2014 needs attention"
                value={String(flaggedCaptures)} unit={`/${totalCaptures}`}
                pct={totalCaptures ? (flaggedCaptures / totalCaptures) * 100 : 0} alert />
              <KpiTile icon="\u21C6" label="Captures synced"
                value={String(syncedCaptures)} unit={`/${totalCaptures}`}
                pct={totalCaptures ? (syncedCaptures / totalCaptures) * 100 : 0} />
            </View>

            <Text style={s.sectionLabel}>QUICK ACTIONS</Text>
            <View style={s.quickGrid}>
              <QuickTile icon="\u25C9" label="Map & Routes" onPress={onOpenMap} />
              <QuickTile icon="\u25A2" label="Manhole Data" onPress={() => onCapture('manhole')} />
              <QuickTile icon="\u2302" label="Building Info" onPress={() => onCapture('building')} />
              <QuickTile icon="\u25A3" label="Building Photo" onPress={() => onCapture('building_photo')} />
              <QuickTile icon="\u21BA" label="Resume Draft" badge={drafts.length || undefined} onPress={onTapResumeDraft} />
              <QuickTile icon="\u21E7" label="Uploaded Data" onPress={onTapUploadedData} />
            </View>

            <Text style={s.sectionLabel}>RECENT CAPTURES</Text>
          </>
        }
        renderItem={({ item: r }) => {
          if (r.type === 'header') return <Text style={s.dayHeader}>{r.text}</Text>;
          const item = r.item;
          const pill = PILL[item.status];
          return (
            <View style={{ paddingHorizontal: SPACE.md }}>
              <SwipeableRow onDelete={() => deleteItem(item)} onSync={!item.synced ? sync : undefined} syncLabel="Sync now"
                onPress={() => setDetailItem({
                  clientId: item.clientId, kind: item.kind, label: item.label, sub: item.sub,
                  lat: item.lat, lon: item.lon, accuracy: item.accuracy, createdAt: item.createdAt,
                  synced: item.synced, serverId: item.serverId,
                })}>
                <View style={s.row}>
                  {item.shape === 'triangle' ? (
                    <View style={s.avatarTriangleWrap}>
                      <View style={[s.avatarTriangle, { borderBottomColor: STATUS[item.status] }]} />
                    </View>
                  ) : item.shape === 'house' ? (
                    <View style={[s.avatar, { backgroundColor: STATUS[item.status] }]}>
                      <Text style={s.avatarHouseGlyph}>⌂</Text>
                    </View>
                  ) : (
                    <View style={[s.avatar, item.shape === 'square' && s.avatarSquare, { backgroundColor: STATUS[item.status] }]} />
                  )}
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.rowLabel} numberOfLines={1}>{item.label}</Text>
                    <Text style={[s.rowMeta, isWeb && ({ userSelect: 'text' } as any)]} numberOfLines={1}>{item.meta}</Text>
                  </View>
                  <View style={[s.pill, { backgroundColor: pill.bg }]}>
                    <Text style={[s.pillText, { color: pill.fg }]}>{pill.label}</Text>
                  </View>
                </View>
              </SwipeableRow>
            </View>
          );
        }}
        ListEmptyComponent={<Text style={s.empty}>No captures yet. Use a tile above to add one.</Text>}
      />

      <RecordDetail item={detailItem} onClose={() => setDetailItem(null)} />

      <BottomSheet visible={menuOpen} onClose={() => setMenuOpen(false)} title="Project">
        <TouchableOpacity style={s.menuItem} onPress={() => { setMenuOpen(false); onSwitchProject(); }}>
          <Text style={s.menuItemText}>Switch project</Text>
        </TouchableOpacity>
        {bioAvailable && (
          <TouchableOpacity style={s.menuItem} onPress={toggleBioLock}>
            <Text style={s.menuItemText}>{bioOn ? `Turn off ${bioLabel} lock` : `Turn on ${bioLabel} lock`}</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={s.menuItem} onPress={async () => { setMenuOpen(false); await logout(); onLogout(); }}>
          <Text style={[s.menuItemText, { color: COLOR.error }]}>Sign out</Text>
        </TouchableOpacity>
      </BottomSheet>

      {/* Only shown when more than one draft exists — a single draft resumes
          straight from the Quick Actions tile with no extra tap. */}
      <BottomSheet visible={draftPicker} onClose={() => setDraftPicker(false)} title="Resume a draft">
        {drafts.map((d) => (
          <TouchableOpacity key={d.building_id} style={s.menuItem}
            onPress={() => { setDraftPicker(false); onResumeDraft({ buildingId: d.building_id, code: d.code }); }}>
            <Text style={s.menuItemText}>{d.code || 'Unnumbered building'}</Text>
            <Text style={s.draftMeta}>Saved {new Date(d.updated_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</Text>
          </TouchableOpacity>
        ))}
      </BottomSheet>
    </View>
  );
}

// SVG viewBox="0 0 36 36", r=15 → circumference ≈ 94.25 (2πr). Matches
// the redesign's ring maths exactly (Vol.4.1-adjacent, screen 4).
const RING_CIRCUMFERENCE = 94.2478;

function ProgressRing({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(pct)));
  const dash = (clamped / 100) * RING_CIRCUMFERENCE;
  return (
    <View style={s.ring}>
      <Svg width={36} height={36} viewBox="0 0 36 36">
        <Circle cx={18} cy={18} r={15} stroke={COLOR.neutralTint} strokeWidth={3} fill="none" />
        {clamped > 0 && (
          <Circle cx={18} cy={18} r={15} stroke={color} strokeWidth={3} fill="none"
            strokeDasharray={`${dash} ${RING_CIRCUMFERENCE}`} strokeLinecap="round"
            rotation={-90} origin="18, 18" />
        )}
      </Svg>
      <Text style={s.ringPct}>{clamped}%</Text>
    </View>
  );
}

// District Progress KPI tile — 2×2 grid, screen 4. `alert` swaps the
// icon well/ring to the orange treatment for the one tile that means
// "needs attention" (never used decoratively elsewhere, per theme.ts's
// FAB_PRIMARY_COLOR comment on the same orange-is-reserved rule).
function KpiTile({ icon, label, value, unit, pct, alert }: {
  icon: string; label: string; value: string; unit: string; pct: number; alert?: boolean;
}) {
  return (
    <View style={[s.kpiTile, alert && s.kpiTileAlert]}>
      <View style={s.kpiTop}>
        <View style={[s.kpiIconWell, alert && s.kpiIconWellAlert]}>
          <Text style={[s.kpiIconGlyph, alert && { color: COLOR.accent700 }]}>{icon}</Text>
        </View>
        <ProgressRing pct={pct} color={alert ? COLOR.accent500 : COLOR.primary900} />
      </View>
      <Text style={s.kpiLabel} numberOfLines={2}>{label}</Text>
      <View style={s.kpiValueRow}>
        <Text style={s.kpiValue}>{value}</Text>
        <Text style={s.kpiUnit}>{unit}</Text>
      </View>
    </View>
  );
}

// Quick Actions tile — 4-column grid, screen 4: "the visible label is the
// point," so just an icon well + two-line label, no sub-description (unlike
// the old 3-tile capture grid this replaces). `badge` puts a small pending-
// count dot on the icon well — used for Resume Draft so a surveyor can see
// there's something to resume without opening the sheet.
function QuickTile({ icon, label, onPress, badge }: {
  icon: string; label: string; onPress: () => void; badge?: number;
}) {
  return (
    <TouchableOpacity style={s.quickTile} onPress={onPress}>
      <View style={s.quickIconWell}>
        <Text style={s.quickIconGlyph}>{icon}</Text>
        {!!badge && (
          <View style={s.quickBadge}><Text style={s.quickBadgeText}>{badge > 9 ? '9+' : badge}</Text></View>
        )}
      </View>
      <Text style={s.quickLabel} numberOfLines={2}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: COLOR.primary900, paddingTop: 54, paddingBottom: SPACE.md, paddingHorizontal: SPACE.md },
  headerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerTitle: { ...TYPE.h2, fontSize: 26, color: '#fff', flex: 1, marginRight: SPACE.sm },
  kebab: { fontSize: 22, color: '#fff', fontWeight: '700' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: SPACE.xs + 2, marginTop: SPACE.sm + 2 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...TYPE.mono, fontSize: 13, color: 'rgba(244,246,249,0.85)' },
  syncCard: { margin: SPACE.md, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, padding: SPACE.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  syncLabel: { ...TYPE.mono, fontSize: 11, letterSpacing: 1, color: COLOR.text500 },
  syncValue: { ...TYPE.mono, fontSize: 15, fontWeight: '700', color: COLOR.text900, marginTop: 2 },
  syncBtn: { backgroundColor: COLOR.accent500, borderRadius: RADIUS.md, paddingHorizontal: SPACE.md, minHeight: MIN_TOUCH, alignItems: 'center', justifyContent: 'center' },
  syncBtnText: { ...TYPE.bodyBold, fontSize: 14, color: '#fff' },
  sectionLabel: { ...TYPE.mono, fontSize: 11, letterSpacing: 1.5, color: COLOR.text500, marginHorizontal: SPACE.md, marginTop: SPACE.lg, marginBottom: SPACE.sm },
  // District Progress — 2x2 KPI grid (screen 4).
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: SPACE.md, gap: 10 },
  kpiTile: { width: '47%', backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderCard, padding: SPACE.sm + 6 },
  kpiTileAlert: { backgroundColor: COLOR.alertTint, borderColor: COLOR.alertBorder },
  kpiTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  kpiIconWell: { width: 32, height: 32, borderRadius: RADIUS.sm + 4, backgroundColor: COLOR.neutralTint, alignItems: 'center', justifyContent: 'center' },
  kpiIconWellAlert: { backgroundColor: COLOR.surface0 },
  kpiIconGlyph: { fontSize: 16, color: COLOR.primary900 },
  ring: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  ringPct: { position: 'absolute', ...TYPE.mono, fontSize: 10, fontWeight: '700', color: COLOR.text900 },
  kpiLabel: { fontSize: 13, lineHeight: 17, color: COLOR.text500, marginTop: SPACE.sm },
  kpiValueRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: 2 },
  kpiValue: { ...TYPE.mono, fontSize: 24, lineHeight: 30, fontWeight: '700', color: COLOR.text900 },
  kpiUnit: { ...TYPE.mono, fontSize: 12, color: COLOR.text500, marginLeft: 3 },
  // Quick Actions — 4-column grid (screen 4); wraps to a second row since
  // this app has six real actions, not the mockup's four.
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: SPACE.md, gap: SPACE.sm },
  quickTile: { width: '22.5%', minHeight: 76, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderCard, alignItems: 'center', justifyContent: 'center', paddingVertical: SPACE.xs + 2, paddingHorizontal: SPACE.xs, gap: 6 },
  quickIconWell: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  quickIconGlyph: { fontSize: 20, color: COLOR.primary900 },
  quickBadge: { position: 'absolute', top: -4, right: -8, minWidth: 16, height: 16, borderRadius: 8, paddingHorizontal: 3, backgroundColor: COLOR.accent500, alignItems: 'center', justifyContent: 'center' },
  quickBadgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },
  quickLabel: { fontSize: 11, lineHeight: 14, fontWeight: '700', color: COLOR.text900, textAlign: 'center' },
  dayHeader: { ...TYPE.mono, fontSize: 11, color: COLOR.text500, marginHorizontal: SPACE.md, marginBottom: SPACE.xs + 2, marginTop: SPACE.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 4, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, padding: SPACE.sm + 4, marginBottom: SPACE.sm },
  avatar: { width: 28, height: 28, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  avatarSquare: { borderRadius: RADIUS.sm + 2 },
  avatarHouseGlyph: { color: '#fff', fontSize: 15, fontWeight: '700', lineHeight: 16 },
  // CSS/RN border-trick triangle — a plain View can't take a triangular
  // borderRadius, so this fakes one with transparent side borders and a
  // solid bottom border carrying the status colour. Wrapper keeps the same
  // 28×28 footprint as the circle/square avatar so the row layout doesn't shift.
  avatarTriangleWrap: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  avatarTriangle: {
    width: 0, height: 0,
    borderLeftWidth: 12, borderRightWidth: 12, borderBottomWidth: 20,
    borderLeftColor: 'transparent', borderRightColor: 'transparent',
  },
  rowLabel: { ...TYPE.bodyBold, fontSize: 14, color: COLOR.text900 },
  rowMeta: { ...TYPE.mono, fontSize: 12, color: COLOR.text500, marginTop: 2 },
  pill: { borderRadius: RADIUS.full, paddingHorizontal: SPACE.sm + 2, paddingVertical: 5, flexShrink: 0 },
  pillText: { fontSize: 11, fontWeight: '700' },
  empty: { ...TYPE.body, color: COLOR.text500, textAlign: 'center', marginTop: 30 },
  menuItem: { paddingVertical: SPACE.md, borderBottomWidth: 1, borderBottomColor: COLOR.surface100 },
  menuItemText: { ...TYPE.bodyBold, color: COLOR.text900 },
  draftMeta: { ...TYPE.mono, fontSize: 12, color: COLOR.text500, marginTop: 2 },
});
