// Uploaded Data — new screen (redesign screen 5): lets a surveyor confirm
// what actually reached the server and recover failures without leaving
// the field. Built entirely from the local outbox ledger (db.ts's
// listAllOutbox) — there's no server-side "batch" concept in this app (a
// surveyor works one project at a time), so a "batch" here is simply one
// day's worth of that project's local capture history, grouped the same
// way DashboardScreen groups Recent Captures.
import { useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Image, Share, ActivityIndicator } from 'react-native';
import { kvGet, listAllOutbox, retryRows, type OutboxRow } from '../db';
import { flush, runSync } from '../sync';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH, isWeb } from '../theme';
import BottomSheet from '../components/BottomSheet';

// Kinds that represent a surveyed entity — everything else in the outbox
// (media, and the reposition/delete/exclude housekeeping ops) isn't a new
// "record" for the header/meta counts, though it's still a real row that
// can succeed or fail.
const RECORD_KINDS = new Set(['manhole', 'building', 'building_photo', 'route']);

type BatchStatus = 'synced' | 'pending' | 'failed';
type Batch = { key: string; dayLabel: string; rows: OutboxRow[] };

function dayLabel(dateStr: string): string {
  const d = new Date(dateStr);
  const today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  const fmt = d.toLocaleDateString(undefined, { day: 'numeric', month: 'long' }).toUpperCase();
  if (d.toDateString() === today.toDateString()) return `TODAY · ${fmt}`;
  if (d.toDateString() === yest.toDateString()) return `YESTERDAY · ${fmt}`;
  return fmt;
}

function batchStatus(rows: OutboxRow[]): BatchStatus {
  if (rows.some((r) => r.status === 'error')) return 'failed';
  if (rows.some((r) => r.status === 'pending')) return 'pending';
  return 'synced';
}

function formatBytes(n: number): string {
  if (n <= 0) return '0.0 MB';
  const gb = n / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(n / 1e6).toFixed(1)} MB`;
}

export default function UploadedDataScreen({ onBack }: { onBack: () => void }) {
  const [rows, setRows] = useState<OutboxRow[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState('Project');
  const [filter, setFilter] = useState<'all' | 'synced' | 'pending' | 'failed'>('all');
  // Which run is currently in flight, if any — a per-batch retry only ever
  // touches that batch's own rejected records, while the footer's "Upload
  // pending" can span every day at once, so its progress isn't attributed
  // to any one card (see the render logic below).
  const [activeOp, setActiveOp] = useState<{ kind: 'batch'; dayKey: string } | { kind: 'global' } | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [errorsBatch, setErrorsBatch] = useState<string | null>(null);
  const [mediaExpandedDay, setMediaExpandedDay] = useState<string | null>(null);
  // Per-photo manual upload — separate from the batch-level retryBatch()
  // below (a surveyor can want to push just one stuck photo without
  // retrying its whole batch). Scoped, so like retryBatch it calls flush()
  // directly rather than runSync() — see sync.ts's runSync comment.
  const [uploadingIds, setUploadingIds] = useState<Set<string>>(new Set());

  async function reload() {
    setRows(await listAllOutbox());
    const pid = await kvGet('projectId');
    setProjectId(pid);
    const pname = await kvGet('projectName');
    setProjectName(pname || 'Project');
  }

  useEffect(() => {
    void reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, []);

  const batches: Batch[] = useMemo(() => {
    const map = new Map<string, OutboxRow[]>();
    for (const r of rows) {
      const day = new Date(r.created_at).toDateString();
      const list = map.get(day);
      if (list) list.push(r); else map.set(day, [r]);
    }
    return [...map.entries()]
      .sort((a, b) => new Date(b[0]).getTime() - new Date(a[0]).getTime())
      .map(([day, rs]) => ({ key: day, dayLabel: dayLabel(day), rows: rs }));
  }, [rows]);

  const visibleBatches = batches.filter((b) => filter === 'all' || batchStatus(b.rows) === filter);

  const allRecordRows = rows.filter((r) => RECORD_KINDS.has(r.kind));
  const allMediaRows = rows.filter((r) => r.kind === 'media');
  const totalBytes = rows.reduce((sum, r) => sum + (r.bytes ?? 0), 0);
  const pendingRows = rows.filter((r) => r.status === 'pending' || r.status === 'error');

  // Only one batch's media grid is shown at a time (per the design's single
  // "Media in Batch N" section) — the most recent day that actually has any.
  const mediaBatch = batches.find((b) => b.rows.some((r) => r.kind === 'media')) ?? null;

  async function runGlobalUpload() {
    if (!projectId || pendingRows.length === 0) return;
    setActiveOp({ kind: 'global' });
    setProgress({ done: 0, total: pendingRows.length });
    try {
      const r = await runSync(projectId, {
        onProgress: (done, total) => { setProgress({ done, total }); void reload(); },
      });
      notify('Upload', r.failed
        ? `${r.done} uploaded · ${r.failed} couldn't send and will retry next time.`
        : `${r.done} uploaded — all caught up.`);
    } catch (e: any) { notify('Upload', String(e?.message ?? e)); }
    finally { setActiveOp(null); setProgress(null); await reload(); }
  }

  async function retryBatch(batch: Batch) {
    if (!projectId) return;
    const failedIds = batch.rows.filter((r) => r.status === 'error').map((r) => r.client_id);
    if (failedIds.length === 0) return;
    await retryRows(failedIds);
    setActiveOp({ kind: 'batch', dayKey: batch.key });
    setProgress({ done: 0, total: failedIds.length });
    try {
      const r = await flush(projectId, {
        onlyClientIds: failedIds,
        onProgress: (done, total) => { setProgress({ done, total }); void reload(); },
      });
      notify('Retry', r.failed ? `${r.done} sent · ${r.failed} still failing.` : `${r.done} sent — resolved.`);
    } catch (e: any) { notify('Retry', String(e?.message ?? e)); }
    finally { setActiveOp(null); setProgress(null); await reload(); }
  }

  async function uploadOne(row: OutboxRow) {
    if (!projectId || uploadingIds.has(row.client_id)) return;
    setUploadingIds((s) => new Set(s).add(row.client_id));
    try {
      const r = await flush(projectId, { onlyClientIds: [row.client_id] });
      if (r.failed > 0) notify('Upload', "Still couldn't send — check its error in View errors.");
    } catch (e: any) { notify('Upload', String(e?.message ?? e)); }
    finally {
      setUploadingIds((s) => { const n = new Set(s); n.delete(row.client_id); return n; });
      await reload();
    }
  }

  async function exportCsv() {
    const target = visibleBatches.flatMap((b) => b.rows);
    const header = 'created_at,kind,status,error\n';
    const body = target.map((r) => [r.created_at, r.kind, r.status, r.error ?? '']
      .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const csv = header + body;
    if (isWeb) {
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `geoplan-export-${Date.now()}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else {
      try { await Share.share({ message: csv, title: 'GeoPlan export' }); }
      catch (e: any) { notify('Export', String(e?.message ?? e)); }
    }
  }

  const errorsBatchData = batches.find((b) => b.key === errorsBatch);

  return (
    <View style={{ flex: 1, backgroundColor: COLOR.surface100 }}>
      <View style={s.header}>
        <View style={s.headerTop}>
          <TouchableOpacity onPress={onBack} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={s.chevron}>‹</Text>
          </TouchableOpacity>
          <Text style={s.headerTitle} numberOfLines={1}>Uploaded Data</Text>
          <TouchableOpacity onPress={reload} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={s.reloadIcon}>⟳</Text>
          </TouchableOpacity>
        </View>
        <View style={s.summaryGrid}>
          <View style={s.summaryCell}>
            <Text style={s.summaryValue}>{allRecordRows.length.toLocaleString()}</Text>
            <Text style={s.summaryLabel}>RECORDS</Text>
          </View>
          <View style={s.summaryCell}>
            <Text style={s.summaryValue}>{allMediaRows.length.toLocaleString()}</Text>
            <Text style={s.summaryLabel}>PHOTOS</Text>
          </View>
          <View style={s.summaryCell}>
            <Text style={s.summaryValue}>{formatBytes(totalBytes)}</Text>
            <Text style={s.summaryLabel}>UPLOADED</Text>
          </View>
        </View>
      </View>

      <View style={s.filterBar}>
        <View style={s.filterTrack}>
          {(['all', 'synced', 'pending', 'failed'] as const).map((f) => (
            <TouchableOpacity key={f} style={[s.filterSeg, filter === f && s.filterSegActive]}
              onPress={() => setFilter(f)}>
              <Text style={[s.filterSegText, filter === f && s.filterSegTextActive]}>
                {f === 'all' ? 'All' : f[0].toUpperCase() + f.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: SPACE.xl }}>
        {visibleBatches.length === 0 && (
          <Text style={s.empty}>Nothing here yet — captures you make will show up as a batch for today.</Text>
        )}
        {visibleBatches.map((batch) => {
          const status = batchStatus(batch.rows);
          const recordRows = batch.rows.filter((r) => RECORD_KINDS.has(r.kind));
          const mediaRows = batch.rows.filter((r) => r.kind === 'media');
          const failedRows = batch.rows.filter((r) => r.status === 'error');
          const isActive = activeOp?.kind === 'batch' && activeOp.dayKey === batch.key && !!progress;
          const pct = isActive ? Math.round((progress!.done / Math.max(1, progress!.total)) * 100) : 0;
          const latest = batch.rows.reduce((max, r) => (r.created_at > max ? r.created_at : max), batch.rows[0]?.created_at ?? '');
          const timeLabel = latest ? new Date(latest).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

          const pill = status === 'synced'
            ? { bg: '#E1F7F1', fg: '#00887A', label: 'SYNCED' }
            : status === 'pending'
            ? { bg: COLOR.neutralTint, fg: COLOR.text500, label: 'PENDING UPLOAD' }
            : { bg: COLOR.alertTint, fg: COLOR.accent700, label: 'NEEDS ATTENTION' };

          const rightValue = isActive ? `${pct}%` : failedRows.length > 0 ? String(failedRows.length) : String(mediaRows.length);
          const rightUnit = isActive ? 'complete' : failedRows.length > 0 ? 'failed' : 'photos';
          const metaText = isActive
            ? `uploading · ${progress!.done} of ${progress!.total} records`
            : failedRows.length > 0
            ? `${failedRows.length} record${failedRows.length === 1 ? '' : 's'} rejected · ${failedRows[0]?.error ?? 'see errors'}`
            : `${timeLabel} · ${recordRows.length} record${recordRows.length === 1 ? '' : 's'}`;

          return (
            <View key={batch.key}>
              <Text style={s.dayEyebrow}>{batch.dayLabel}</Text>
              <View style={s.batchCard}>
                <View style={s.batchTop}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.batchTitle} numberOfLines={1}>{projectName}</Text>
                    <View style={s.batchMetaRow}>
                      <View style={[s.pill, { backgroundColor: pill.bg }]}>
                        <Text style={[s.pillText, { color: pill.fg }]} numberOfLines={1}>{pill.label}</Text>
                      </View>
                      <Text style={s.metaText} numberOfLines={1}>{metaText}</Text>
                    </View>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={s.batchValue}>{rightValue}</Text>
                    <Text style={s.batchUnit}>{rightUnit}</Text>
                  </View>
                </View>

                {isActive && (
                  <View style={s.progressTrack}>
                    <View style={[s.progressFill, { width: `${pct}%` }]} />
                  </View>
                )}

                {!isActive && failedRows.length > 0 && (
                  <View style={s.actionRow}>
                    <TouchableOpacity style={s.ghostBtn} onPress={() => setErrorsBatch(batch.key)}>
                      <Text style={s.ghostBtnText}>View errors</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.retryBtn} onPress={() => retryBatch(batch)}>
                      <Text style={s.retryBtnText}>Retry upload</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>

              {mediaBatch?.key === batch.key && mediaRows.length > 0 && (
                <View style={s.mediaSection}>
                  <View style={s.mediaHeader}>
                    <Text style={s.mediaEyebrow}>MEDIA IN THIS BATCH</Text>
                    {mediaRows.length > 8 && mediaExpandedDay !== batch.key && (
                      <TouchableOpacity onPress={() => setMediaExpandedDay(batch.key)}>
                        <Text style={s.mediaLink}>View all {mediaRows.length}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                  <View style={s.mediaGrid}>
                    {(mediaExpandedDay === batch.key ? mediaRows : mediaRows.slice(0, 7)).map((r) => {
                      let uri: string | null = null; let kind = 'photo';
                      try { const p = JSON.parse(r.payload); uri = p.uri; kind = p.kind ?? 'photo'; } catch { /* ignore */ }
                      const isUploading = uploadingIds.has(r.client_id);
                      const needsUpload = r.status === 'pending' || r.status === 'error';
                      return (
                        <View key={r.client_id} style={s.mediaThumbWrap}>
                          {uri && kind === 'photo' ? (
                            <Image source={{ uri }} style={s.mediaThumb} resizeMode="cover" />
                          ) : (
                            <View style={[s.mediaThumb, s.mediaThumbFallback]}>
                              <Text style={s.mediaThumbGlyph}>{kind === 'video' ? '▶' : '◻'}</Text>
                            </View>
                          )}
                          {!!r.bytes && (
                            <View style={s.mediaChip}><Text style={s.mediaChipText}>{(r.bytes / 1e6).toFixed(1)} MB</Text></View>
                          )}
                          {/* Status badge — every photo shows one, not just
                              uploaded ones (previously the bytes chip above
                              was the only signal, and it's silent for
                              anything not yet synced). */}
                          <View style={[
                            s.mediaStatusBadge,
                            r.status === 'done' ? s.mediaStatusDone
                              : r.status === 'error' ? s.mediaStatusError : s.mediaStatusPending,
                          ]}>
                            <Text style={s.mediaStatusGlyph}>
                              {r.status === 'done' ? '✓' : r.status === 'error' ? '!' : '•'}
                            </Text>
                          </View>
                          {/* Manual per-photo upload — "in case for some
                              reason" the automatic/batch sync hasn't
                              picked this one up yet. */}
                          {needsUpload && (
                            <TouchableOpacity
                              style={s.mediaUploadBtn} disabled={isUploading}
                              hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                              onPress={() => uploadOne(r)}>
                              {isUploading
                                ? <ActivityIndicator color="#fff" size="small" />
                                : <Text style={s.mediaUploadGlyph}>⇑</Text>}
                            </TouchableOpacity>
                          )}
                        </View>
                      );
                    })}
                    {mediaExpandedDay !== batch.key && mediaRows.length > 8 && (
                      <View style={[s.mediaThumbWrap, s.mediaThumb, s.mediaOverflow]}>
                        <Text style={s.mediaOverflowText}>+{mediaRows.length - 7}</Text>
                      </View>
                    )}
                  </View>
                </View>
              )}
            </View>
          );
        })}
      </ScrollView>

      <View style={s.footer}>
        <TouchableOpacity style={s.exportBtn} onPress={exportCsv}>
          <Text style={s.exportBtnText}>Export CSV</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.uploadBtn, pendingRows.length === 0 && s.uploadBtnDisabled]}
          disabled={pendingRows.length === 0 || activeOp !== null}
          onPress={runGlobalUpload}>
          {activeOp?.kind === 'global'
            ? <ActivityIndicator color="#fff" />
            : (
              <>
                {pendingRows.length > 0 && <View style={s.uploadDot} />}
                <Text style={s.uploadBtnText}>
                  {pendingRows.length === 0 ? 'Nothing to upload' : `Upload ${pendingRows.length} pending`}
                </Text>
              </>
            )}
        </TouchableOpacity>
      </View>

      <BottomSheet visible={!!errorsBatch} onClose={() => setErrorsBatch(null)} title="Upload errors">
        {(errorsBatchData?.rows.filter((r) => r.status === 'error') ?? []).map((r) => (
          <View key={r.client_id} style={s.errorRow}>
            <Text style={s.errorKind}>{r.kind}</Text>
            <Text style={s.errorText}>{r.error || 'Unknown error'}</Text>
          </View>
        ))}
      </BottomSheet>
    </View>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: COLOR.primary900, paddingTop: 54, paddingBottom: SPACE.md, paddingHorizontal: SPACE.md },
  headerTop: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm },
  chevron: { fontSize: 28, color: '#fff', fontWeight: '700', width: 20 },
  headerTitle: { ...TYPE.h3, fontSize: 18, lineHeight: 24, color: '#fff', flex: 1 },
  reloadIcon: { fontSize: 20, color: '#fff' },
  summaryGrid: { flexDirection: 'row', marginTop: SPACE.md, gap: 8 },
  summaryCell: { flex: 1 },
  summaryValue: { ...TYPE.mono, fontSize: 20, lineHeight: 26, fontWeight: '700', color: '#fff' },
  summaryLabel: { fontSize: 11, color: 'rgba(244,246,249,0.6)', marginTop: 2 },
  filterBar: { backgroundColor: COLOR.surface0, borderBottomWidth: 1, borderBottomColor: COLOR.borderCard, paddingVertical: SPACE.sm + 2, paddingHorizontal: SPACE.md },
  filterTrack: { flexDirection: 'row', backgroundColor: COLOR.surface100, borderRadius: RADIUS.full, padding: 5, gap: 6 },
  filterSeg: { flex: 1, minHeight: MIN_TOUCH, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center' },
  filterSegActive: { backgroundColor: COLOR.primary900 },
  filterSegText: { fontSize: 13, fontWeight: '700', color: COLOR.text500 },
  filterSegTextActive: { color: '#fff' },
  empty: { ...TYPE.body, color: COLOR.text500, textAlign: 'center', marginTop: 40, paddingHorizontal: SPACE.lg },
  dayEyebrow: { ...TYPE.mono, fontSize: 11, color: COLOR.text500, marginHorizontal: SPACE.md, marginTop: SPACE.md, marginBottom: SPACE.sm },
  batchCard: { marginHorizontal: SPACE.md, marginBottom: SPACE.sm + 2, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderCard, padding: SPACE.md - 2 },
  batchTop: { flexDirection: 'row', alignItems: 'flex-start', gap: SPACE.sm },
  batchTitle: { ...TYPE.bodyBold, fontSize: 15, color: COLOR.text900 },
  batchMetaRow: { flexDirection: 'row', alignItems: 'center', gap: SPACE.xs + 2, marginTop: 4, flexWrap: 'wrap' },
  pill: { borderRadius: RADIUS.full, paddingHorizontal: SPACE.sm, paddingVertical: 3, flexShrink: 0 },
  pillText: { fontSize: 11, fontWeight: '700' },
  metaText: { ...TYPE.mono, fontSize: 11, color: COLOR.text500, flexShrink: 1 },
  batchValue: { ...TYPE.mono, fontSize: 18, lineHeight: 22, fontWeight: '700', color: COLOR.text900 },
  batchUnit: { ...TYPE.mono, fontSize: 11, color: COLOR.text500 },
  progressTrack: { height: 6, borderRadius: RADIUS.full, backgroundColor: COLOR.neutralTint, marginTop: SPACE.sm + 4, overflow: 'hidden' },
  progressFill: { height: 6, borderRadius: RADIUS.full, backgroundColor: COLOR.primary900 },
  actionRow: { flexDirection: 'row', gap: SPACE.sm, marginTop: SPACE.sm + 4 },
  ghostBtn: { flex: 1, minHeight: MIN_TOUCH, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderDefault, alignItems: 'center', justifyContent: 'center' },
  ghostBtnText: { fontSize: 13, fontWeight: '700', color: COLOR.text900 },
  retryBtn: { flex: 1, minHeight: MIN_TOUCH, borderRadius: RADIUS.md, backgroundColor: COLOR.accent500, alignItems: 'center', justifyContent: 'center' },
  retryBtnText: { fontSize: 13, fontWeight: '700', color: '#fff' },
  mediaSection: { marginHorizontal: SPACE.md, marginTop: SPACE.xs, marginBottom: SPACE.md },
  mediaHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACE.sm },
  mediaEyebrow: { ...TYPE.mono, fontSize: 11, color: COLOR.text500 },
  mediaLink: { fontSize: 13, fontWeight: '700', color: COLOR.primary700 },
  mediaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  mediaThumbWrap: { width: '22.5%', aspectRatio: 1, position: 'relative' },
  mediaThumb: { width: '100%', height: '100%', borderRadius: RADIUS.sm + 2, backgroundColor: COLOR.neutralTint },
  mediaThumbFallback: { alignItems: 'center', justifyContent: 'center' },
  mediaThumbGlyph: { fontSize: 18, color: COLOR.text500 },
  mediaChip: { position: 'absolute', left: 4, bottom: 4, backgroundColor: 'rgba(255,255,255,0.85)', borderRadius: 3, paddingHorizontal: 4, paddingVertical: 1 },
  mediaChipText: { ...TYPE.mono, fontSize: 9, color: COLOR.text900 },
  mediaStatusBadge: { position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: '#fff' },
  mediaStatusDone: { backgroundColor: COLOR.success500 },
  mediaStatusPending: { backgroundColor: COLOR.text500 },
  mediaStatusError: { backgroundColor: COLOR.accent500 },
  mediaStatusGlyph: { fontSize: 11, fontWeight: '700', color: '#fff', lineHeight: 13 },
  mediaUploadBtn: { position: 'absolute', bottom: 4, right: 4, width: MIN_TOUCH - 12, height: MIN_TOUCH - 12, borderRadius: (MIN_TOUCH - 12) / 2, backgroundColor: COLOR.primary900, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: '#fff' },
  mediaUploadGlyph: { fontSize: 15, fontWeight: '700', color: '#fff' },
  mediaOverflow: { alignItems: 'center', justifyContent: 'center', backgroundColor: COLOR.surface100 },
  mediaOverflowText: { ...TYPE.mono, fontSize: 13, fontWeight: '700', color: COLOR.text500 },
  footer: { flexDirection: 'row', gap: SPACE.sm + 4, backgroundColor: COLOR.surface0, borderTopWidth: 1, borderTopColor: COLOR.borderDefault, padding: SPACE.md - 2, paddingBottom: SPACE.lg - 2 },
  exportBtn: { width: 120, minHeight: 48, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderDefault, alignItems: 'center', justifyContent: 'center' },
  exportBtnText: { fontSize: 13, fontWeight: '700', color: COLOR.text900 },
  uploadBtn: { flex: 1, minHeight: 48, borderRadius: RADIUS.md, backgroundColor: COLOR.primary900, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACE.sm },
  uploadBtnDisabled: { backgroundColor: COLOR.text500 },
  uploadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLOR.accent500 },
  uploadBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  errorRow: { paddingVertical: SPACE.sm + 2, borderBottomWidth: 1, borderBottomColor: COLOR.surface100 },
  errorKind: { ...TYPE.bodyBold, fontSize: 13, color: COLOR.text900, textTransform: 'capitalize' },
  errorText: { fontSize: 13, color: COLOR.accent700, marginTop: 2 },
});
