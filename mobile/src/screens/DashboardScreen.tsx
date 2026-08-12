// District Dashboard — the former single Home screen, split per the Claude
// Design redesign ("Field Survey App Redesign.dc.html", screen 4). Reached
// after a project is picked on ProjectListScreen; the three capture tiles
// and Recent Captures list that used to live on Home are here now.
import { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, FlatList, ActivityIndicator, ScrollView } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { listAssets, listRoutes, deleteAsset, deleteRoute, deleteOutbox, pendingCount, kvGet } from '../db';
import { flush } from '../sync';
import { notify } from '../notify';
import { confirmAction } from '../confirm';
import { logout } from '../auth';
import { hasBiometricHardware, isBiometricLockEnabled, setBiometricLockEnabled, supportedTypeLabel } from '../biometrics';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH, isWeb, STATUS } from '../theme';
import { pinStatus, pinShape, type PinStatusName } from '../pinStatus';
import SwipeableRow from '../components/SwipeableRow';
import BottomSheet from '../components/BottomSheet';

type CaptureItem = {
  clientId: string; isRoute: boolean; label: string; meta: string;
  status: PinStatusName; shape: 'square' | 'triangle' | 'circle' | 'house'; synced: boolean; createdAt: string;
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

export default function DashboardScreen({ onOpenMap, onCapture, onSwitchProject, onLogout, onBioLockChanged }: {
  onOpenMap: () => void;
  onCapture: (kind: 'manhole' | 'building' | 'building_photo') => void;
  onSwitchProject: () => void;
  onLogout: () => void;
  onBioLockChanged?: (on: boolean) => void;
}) {
  const [projectName, setProjectName] = useState('');
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [assets, setAssets] = useState<any[]>([]);
  const [routes, setRoutes] = useState<any[]>([]);
  const [pend, setPend] = useState(0);
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [bioAvailable, setBioAvailable] = useState(false);
  const [bioLabel, setBioLabel] = useState('Device biometrics');
  const [bioOn, setBioOn] = useState(false);

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
    const pid = await kvGet('projectId');
    if (pid) setLastSync(await kvGet(`lastSync:${pid}`));
    const pname = await kvGet('projectName');
    setProjectName(pname || 'Project');
  }, []);

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
      const r = await flush(pid);
      const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setLastSync(`${stamp} · ${r.done} updated${r.failed ? `, ${r.failed} failed` : ''}`);
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
    })),
    ...routes.map((r): CaptureItem => ({
      clientId: r.client_id, isRoute: true, label: `route · ${Math.round(r.length_m)} m`,
      meta: `${r.point_count} pts`,
      status: r.synced ? 'synced' : 'pending', shape: 'circle', synced: !!r.synced, createdAt: r.created_at,
    })),
  ].sort((a, b) => b.createdAt.localeCompare(a.createdAt));

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

            <View style={s.tileGrid}>
              <Tile label="Map & Routes" sub="Drop asset pins, record cable routes" onPress={onOpenMap} />
              <Tile label="Manhole Data" sub="Add GPS, condition, photos" onPress={() => onCapture('manhole')} />
              <Tile label="Building Info" sub="Enter type, address, units" onPress={() => onCapture('building')} />
              <Tile label="Building Photo" sub="Snap a photo, GPS auto-captured" onPress={() => onCapture('building_photo')} />
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
              <SwipeableRow onDelete={() => deleteItem(item)} onSync={!item.synced ? sync : undefined} syncLabel="Sync now">
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
    </View>
  );
}

function Tile({ label, sub, onPress }: { label: string; sub: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={s.tile} onPress={onPress}>
      <View style={s.tileIcon} />
      <Text style={s.tileLabel}>{label}</Text>
      <Text style={s.tileSub}>{sub}</Text>
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
  tileGrid: { flexDirection: 'row', marginHorizontal: SPACE.md, gap: SPACE.sm + 2 },
  tile: { flex: 1, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, paddingVertical: SPACE.md - 2, paddingHorizontal: SPACE.xs + 2, alignItems: 'center', gap: SPACE.xs + 2, minHeight: MIN_TOUCH + 40 },
  tileIcon: { width: 44, height: 44, borderRadius: RADIUS.full, backgroundColor: COLOR.primary900 },
  tileLabel: { ...TYPE.bodyBold, fontSize: 13, color: COLOR.text900, textAlign: 'center' },
  tileSub: { fontSize: 11, lineHeight: 14, color: COLOR.text500, textAlign: 'center' },
  sectionLabel: { ...TYPE.mono, fontSize: 11, letterSpacing: 1.5, color: COLOR.text500, marginHorizontal: SPACE.md, marginTop: SPACE.lg, marginBottom: SPACE.sm },
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
});
