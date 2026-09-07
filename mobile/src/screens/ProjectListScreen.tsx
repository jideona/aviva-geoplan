// Project picker — split out from the old single Home screen per the Claude
// Design redesign ("Field Survey App Redesign.dc.html", screen 1). Picking a
// project here hands off to DashboardScreen, which is where the old Home's
// capture tiles / sync / recent-captures actually live now.
import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextInput, ScrollView, ActivityIndicator } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { kvGet, kvSet, pendingCount } from '../db';
import { authed, logout } from '../auth';
import { runSync } from '../sync';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, ELEVATION, TYPE, MIN_TOUCH } from '../theme';

type ProjectSummary = { id: string; name: string; district: string; city: string | null };

export default function ProjectListScreen({ onPicked, onLogout }: {
  onPicked: () => void;
  onLogout: () => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [query, setQuery] = useState('');
  const [manualEntry, setManualEntry] = useState(false);
  const [manualId, setManualId] = useState('');
  const [online, setOnline] = useState(true);
  const [pend, setPend] = useState(0);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    const unsub = NetInfo.addEventListener((st) => setOnline(!!st.isConnected));
    void pendingCount().then(setPend);
    (async () => {
      // The device only ever has one active project's data locally (see
      // sync.ts), so "last synced" here mirrors whichever project the
      // Dashboard last synced, not a per-row figure.
      const pid = await kvGet('projectId');
      setActiveProjectId(pid);
      if (pid) setLastSync(await kvGet(`lastSync:${pid}`));
    })();
    (async () => {
      const cached = await kvGet('projectsCache');
      if (cached) { try { setProjects(JSON.parse(cached)); } catch { /* ignore bad cache */ } }
      try {
        const res = await authed('/api/v1/projects');
        if (res.ok) {
          const list: ProjectSummary[] = (await res.json()).map((p: any) => ({
            id: p.id, name: p.name, district: p.district, city: p.city,
          }));
          setProjects(list);
          await kvSet('projectsCache', JSON.stringify(list));
        }
      } catch { /* offline — cached list (if any) still stands */ }
    })();
    return unsub;
  }, []);

  async function select(p: ProjectSummary) {
    await kvSet('projectId', p.id);
    await kvSet('projectName', p.name);
    onPicked();
  }

  async function selectManual() {
    const id = manualId.trim();
    if (!id) return;
    await kvSet('projectId', id);
    await kvSet('projectName', '');
    onPicked();
  }

  async function syncNow() {
    if (!activeProjectId) {
      notify('Sync now', 'Open a project first — there\'s nothing local to sync yet.');
      return;
    }
    setSyncing(true);
    try {
      const r = await runSync(activeProjectId);
      const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const summary = `${stamp} · ${r.done} updated${r.failed ? `, ${r.failed} failed` : ''}`;
      setLastSync(summary);
      await kvSet(`lastSync:${activeProjectId}`, summary);
      setPend(await pendingCount());
      if (r.failed > 0) notify('Sync issue', `${r.done} sent · ${r.failed} couldn't send and will retry.`);
    } catch (e: any) { notify('Sync', String(e?.message ?? e)); }
    finally { setSyncing(false); }
  }

  const filtered = query.trim()
    ? projects.filter((p) => `${p.name} ${p.district} ${p.city ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))
    : projects;

  return (
    <View style={{ flex: 1, backgroundColor: COLOR.surface100 }}>
      <View style={s.header}>
        <View style={s.headerTop}>
          <Text style={s.headerTitle}>Aviva GeoPlan Survey</Text>
          <TouchableOpacity onPress={async () => { await logout(); onLogout(); }}>
            <Text style={s.signout}>Sign out</Text>
          </TouchableOpacity>
        </View>
        <View style={s.statusRow}>
          <View style={[s.dot, { backgroundColor: online ? COLOR.success500 : COLOR.error }]} />
          <Text style={s.statusText}>{online ? 'Online' : 'Offline'} · {pend} pending</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: SPACE.xl }}>
        <TextInput style={s.search} placeholder="Search projects" placeholderTextColor={COLOR.text500}
          value={query} onChangeText={setQuery} />

        {filtered.length === 0 ? (
          <Text style={s.empty}>
            {projects.length === 0
              ? (online ? 'No projects found for your account.' : 'Connect to the internet once to load your projects.')
              : 'No projects match your search.'}
          </Text>
        ) : (
          <View style={s.list}>
            {filtered.map((p, i) => (
              <TouchableOpacity key={p.id} onPress={() => select(p)}
                style={[s.row, i < filtered.length - 1 && s.rowDivider]}>
                <View style={s.avatar}><View style={s.avatarDot} /></View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.rowName} numberOfLines={1}>{p.name}</Text>
                  <Text style={s.rowSub} numberOfLines={1}>{[p.district, p.city].filter(Boolean).join(', ')}</Text>
                </View>
                <Text style={s.chevron}>›</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        <TouchableOpacity style={s.manualRow} onPress={() => setManualEntry((v) => !v)}>
          <Text style={s.manualPlus}>+</Text>
          <Text style={s.manualText}>Enter project ID manually</Text>
        </TouchableOpacity>
        {manualEntry && (
          <View style={s.manualBox}>
            <TextInput style={s.manualInput} placeholder="Project id (UUID)" placeholderTextColor={COLOR.text500}
              autoCapitalize="none" value={manualId} onChangeText={setManualId} />
            <TouchableOpacity style={s.manualGo} onPress={selectManual} disabled={!manualId.trim()}>
              <Text style={s.manualGoText}>Use this project</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      <View style={s.footer}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.footerLabel} numberOfLines={1}>
            {lastSync ? `LAST SYNCED ${lastSync.split(' · ')[0]}` : 'NOT SYNCED YET'}
          </Text>
          <Text style={s.footerValue} numberOfLines={1}>
            {pend} PENDING
          </Text>
        </View>
        <TouchableOpacity style={[s.syncBtn, syncing && { opacity: 0.7 }]} onPress={syncNow} disabled={syncing}>
          {syncing ? <ActivityIndicator color="#fff" /> : <Text style={s.syncBtnText}>Sync now</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: COLOR.primary900, paddingTop: 54, paddingBottom: SPACE.md, paddingHorizontal: SPACE.md },
  headerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerTitle: { ...TYPE.h3, fontSize: 20, color: '#fff' },
  signout: { ...TYPE.small, color: COLOR.primary500, fontWeight: '500' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: SPACE.xs + 2, marginTop: SPACE.sm + 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...TYPE.mono, fontSize: 13, color: 'rgba(244,246,249,0.85)' },
  search: { ...TYPE.body, margin: SPACE.md, marginBottom: SPACE.sm, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, padding: SPACE.md - 4, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900, minHeight: MIN_TOUCH },
  empty: { ...TYPE.small, color: COLOR.text500, marginHorizontal: SPACE.md, marginTop: SPACE.sm },
  list: { margin: SPACE.md, marginTop: SPACE.sm, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, overflow: 'hidden', ...ELEVATION[1] },
  row: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 4, padding: SPACE.md - 2, minHeight: MIN_TOUCH + 12 },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: COLOR.surface100 },
  avatar: { width: 36, height: 36, borderRadius: RADIUS.full, backgroundColor: COLOR.surface100, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  avatarDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: COLOR.primary900 },
  rowName: { ...TYPE.bodyBold, fontSize: 15, color: COLOR.text900 },
  rowSub: { ...TYPE.small, color: COLOR.text500, marginTop: 2 },
  chevron: { fontSize: 20, color: COLOR.borderDefault, flexShrink: 0 },
  manualRow: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 2, marginHorizontal: SPACE.md, marginTop: SPACE.sm, padding: SPACE.sm + 2, minHeight: MIN_TOUCH },
  manualPlus: { fontSize: 18, color: COLOR.primary500, fontWeight: '700', width: 18, textAlign: 'center' },
  manualText: { ...TYPE.body, fontSize: 15, fontWeight: '500', color: COLOR.primary700 },
  manualBox: { marginHorizontal: SPACE.md, marginTop: SPACE.xs },
  manualInput: { ...TYPE.body, backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, padding: SPACE.sm + 2, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900, marginBottom: SPACE.sm },
  manualGo: { backgroundColor: COLOR.primary700, borderRadius: RADIUS.md, alignItems: 'center', paddingVertical: SPACE.sm + 4, minHeight: MIN_TOUCH },
  manualGoText: { ...TYPE.bodyBold, fontSize: 14, color: '#fff' },
  footer: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 4, backgroundColor: COLOR.surface0, borderTopWidth: 1, borderTopColor: COLOR.borderDefault, paddingVertical: SPACE.sm + 6, paddingHorizontal: SPACE.md + 4 },
  footerLabel: { ...TYPE.mono, fontSize: 12, letterSpacing: 0.5, color: COLOR.text500 },
  footerValue: { ...TYPE.mono, fontSize: 15, fontWeight: '700', color: COLOR.text900, marginTop: 2 },
  syncBtn: { backgroundColor: COLOR.accent500, borderRadius: RADIUS.md, minHeight: MIN_TOUCH, paddingHorizontal: SPACE.md + 4, alignItems: 'center', justifyContent: 'center' },
  syncBtnText: { ...TYPE.bodyBold, fontSize: 14, color: '#fff' },
});
