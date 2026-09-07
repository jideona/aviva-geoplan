import { useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { getFix, Fix } from '../gps';
import { authed } from '../auth';
import { enqueue, saveAsset, newId, kvGet, saveDraft, getDraft, deleteDraft } from '../db';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, MIN_TOUCH, isWeb } from '../theme';
import { stampCoordinates } from '../mediaStamp';

const TYPES = ['residential', 'terrace', 'commercial', 'mixed_use', 'institutional', 'religious', 'other'];
const CONDITIONS = ['excellent', 'good', 'fair', 'poor'] as const;
type Media = { uri: string; kind: 'photo' | 'video'; contentType: string };
type LinkedManhole = { id: string; code: string | null } | null;
type NearbyManhole = { id: string; code: string | null; manhole_type: string; distance_m: number };

export default function BuildingScreen({ onSaved, onCancel, resume }: {
  onSaved: () => void; onCancel: () => void;
  // Set from the Dashboard's "Resume draft" quick action — jumps straight
  // to the edit form with this building's saved draft pre-loaded, skipping
  // the GPS-proximity search below (see the resume effect further down).
  resume?: { buildingId: string; code: string | null } | null;
}) {
  const [near, setNear] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState<any | null>(null);
  const [type, setType] = useState('residential');
  const [address, setAddress] = useState('');
  const [units, setUnits] = useState('');
  const [drop, setDrop] = useState<'aerial' | 'underground' | ''>('');
  const [notes, setNotes] = useState('');
  const [condition, setCondition] = useState<typeof CONDITIONS[number]>('good');
  const [links, setLinks] = useState<[LinkedManhole, LinkedManhole]>([null, null]);
  const [nearbyManholes, setNearbyManholes] = useState<NearbyManhole[]>([]);
  const [pickerSlot, setPickerSlot] = useState<0 | 1 | null>(null);
  const [manholesLoading, setManholesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [lastFix, setLastFix] = useState<Fix | null>(null);
  const [media, setMedia] = useState<Media[]>([]);
  const [hasDraft, setHasDraft] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function capture(kind: 'photo' | 'video') {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { notify('Camera', 'Camera permission is required.'); return; }
    const r = await ImagePicker.launchCameraAsync({
      mediaTypes: kind === 'photo' ? ImagePicker.MediaTypeOptions.Images : ImagePicker.MediaTypeOptions.Videos,
      quality: 0.6, videoMaxDuration: 60,
      cameraType: ImagePicker.CameraType.back,
    });
    if (r.canceled) return;
    const a = r.assets[0];
    let uri = a.uri;
    let contentType = a.mimeType ?? (kind === 'photo' ? 'image/jpeg' : 'video/mp4');
    if (isWeb && kind === 'photo' && lastFix) {
      try { uri = await stampCoordinates(uri, lastFix); contentType = 'image/jpeg'; }
      catch { /* stamping is best-effort — keep the unstamped photo on failure */ }
    }
    setMedia((m) => [...m, { uri, kind, contentType }]);
  }

  // Auto-resume: fetch a fresh GPS fix (submitSurvey needs one for the
  // final saved position, same as findNearby below would provide) then
  // select the target building directly — selectBuilding() already prefers
  // the saved draft's values over server ones, so a minimal {id, code} is
  // enough here without re-fetching the full building record.
  useEffect(() => {
    if (!resume) return;
    setLoading(true);
    (async () => {
      try {
        const fix = await getFix().catch(() => null);
        if (fix) setLastFix(fix);
        await selectBuilding({ id: resume.buildingId, code: resume.code });
      } finally { setLoading(false); }
    })();
  }, [resume]);

  async function findNearby() {
    setLoading(true); setNear([]); setPick(null); setMedia([]);
    try {
      const fix = await getFix();
      setLastFix(fix);
      const pid = await kvGet('projectId');
      const res = await authed(`/api/v1/projects/${pid}/mobile/buildings/near?lat=${fix.lat}&lon=${fix.lon}`);
      if (!res.ok) throw new Error('Could not load nearby buildings (need a connection).');
      setNear((await res.json()).buildings);
    } catch (e: any) { notify('Nearby', String(e?.message ?? e)); }
    finally { setLoading(false); }
  }

  async function selectBuilding(b: any) {
    setPick(b);
    setLinks([null, null]);
    setErr(null);
    // A saved draft for this building represents the surveyor's own more
    // recent, not-yet-submitted intent — prefer it over the server's
    // last-confirmed values.
    const draft = await getDraft(b.id);
    if (draft) {
      try {
        const a = JSON.parse(draft.attrs);
        setType(a.type ?? b.building_type ?? 'residential');
        setAddress(a.address ?? b.address ?? '');
        setUnits(a.units ?? (b.units_surveyed ? String(b.units_surveyed) : ''));
        setDrop(a.drop ?? b.drop_deployment ?? '');
        setNotes(a.notes ?? b.notes ?? '');
        setCondition(a.condition ?? b.condition ?? 'good');
        setHasDraft(true);
        return;
      } catch { /* fall through to server values on a corrupt draft */ }
    }
    setType(b.building_type || 'residential');
    setAddress(b.address || ''); setUnits(b.units_surveyed ? String(b.units_surveyed) : '');
    setDrop(b.drop_deployment || ''); setNotes(b.notes || '');
    setCondition(b.condition || 'good');
    setHasDraft(false);
  }

  async function openManholePicker(slot: 0 | 1) {
    setPickerSlot((s) => (s === slot ? null : slot));
    if (nearbyManholes.length || !lastFix) return;
    setManholesLoading(true);
    try {
      const pid = await kvGet('projectId');
      const res = await authed(
        `/api/v1/projects/${pid}/mobile/manholes/near?lat=${lastFix.lat}&lon=${lastFix.lon}`);
      if (res.ok) setNearbyManholes((await res.json()).manholes);
    } catch { /* offline — picker just stays empty */ }
    finally { setManholesLoading(false); }
  }

  function pickManhole(slot: 0 | 1, m: NearbyManhole) {
    setLinks((prev) => {
      const next = [...prev] as [LinkedManhole, LinkedManhole];
      next[slot] = { id: m.id, code: m.code };
      return next;
    });
    setPickerSlot(null);
  }

  function formAttrs() {
    return { type, address, units, drop, notes, condition,
             linkedManholeIds: links.filter(Boolean).map((l) => l!.id) };
  }

  async function saveDraftNow() {
    if (!pick) return;
    setSavingDraft(true);
    try {
      await saveDraft({ buildingId: pick.id, code: pick.code ?? null, attrs: formAttrs() });
      notify('Draft saved', 'Resume it later from the Dashboard’s Resume Draft tile.');
      onCancel();
    } finally { setSavingDraft(false); }
  }

  async function submitSurvey() {
    if (!pick) return;
    if (!address.trim()) { setErr('Address is required.'); return; }
    const unitsN = parseInt(units, 10);
    if (!units.trim() || !Number.isFinite(unitsN) || unitsN < 1) {
      setErr('Number of units must be at least 1.'); return;
    }
    setErr(null);
    setSaving(true);
    try {
      const attrs: any = { building_type: type, address, units_surveyed: unitsN, condition };
      if (drop) attrs.drop_deployment = drop;
      if (notes) attrs.notes = notes;
      const linkedIds = links.filter(Boolean).map((l) => l!.id);
      if (linkedIds.length) attrs.linked_manhole_ids = linkedIds;
      const clientId = newId('bld');
      await saveAsset({
        clientId, kind: 'building', lat: lastFix?.lat ?? 0, lon: lastFix?.lon ?? 0,
        accuracy: lastFix?.accuracy ?? 0, label: pick.code || 'Unnumbered', sub: type,
      });
      await enqueue({ clientId, kind: 'building', payload: { buildingId: pick.id, attrs } });
      for (const m of media) {
        await enqueue({ clientId: newId('md'), kind: 'media', parentClientId: clientId,
          payload: { entityType: 'building', entityId: pick.id, kind: m.kind, contentType: m.contentType,
            uri: m.uri, lat: lastFix?.lat ?? null, lon: lastFix?.lon ?? null } });
      }
      await deleteDraft(pick.id);
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <View>
      <TouchableOpacity style={s.find} onPress={findNearby} disabled={loading}>
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.findText}>Find buildings near me (GPS)</Text>}
      </TouchableOpacity>

      {!pick && near.map((b) => (
        <TouchableOpacity key={b.id} style={s.card} onPress={() => selectBuilding(b)}>
          <Text style={s.code}>{b.code || 'Unnumbered'} · {b.distance_m} m</Text>
          <Text style={s.meta}>{b.building_type} · {b.use_type}{b.address ? ` · ${b.address}` : ''}</Text>
        </TouchableOpacity>
      ))}

      {pick && (
        <View style={s.edit}>
          {hasDraft && (
            <View style={s.draftBanner}>
              <Text style={s.draftBannerText}>Resumed from a saved draft — review before submitting.</Text>
            </View>
          )}

          <Text style={s.sectionLabel}>LOCATION & COORDINATES</Text>

          <Text style={s.fieldLabel}>Address</Text>
          <TextInput style={s.input} placeholder="Street address" placeholderTextColor={COLOR.text500}
            value={address} onChangeText={setAddress} />

          <View style={s.coordRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.fieldLabel}>GPS Coordinates</Text>
              <Text style={s.coordValue}>{lastFix ? `${lastFix.lat.toFixed(5)}, ${lastFix.lon.toFixed(5)}` : '—'}</Text>
            </View>
            <View>
              <Text style={s.fieldLabel}>Accuracy</Text>
              <Text style={[s.coordValue, (lastFix?.accuracy ?? 0) > 10 && { color: COLOR.accent700 }]}>
                {lastFix ? `±${Math.round(lastFix.accuracy)}m` : '—'}
              </Text>
            </View>
          </View>

          <View style={s.divider} />
          <Text style={s.sectionLabel}>BUILDING DETAILS</Text>

          <Text style={s.fieldLabel}>Building Type</Text>
          <View style={s.grid}>
            {TYPES.map((t) => (
              <TouchableOpacity key={t} onPress={() => setType(t)} style={[s.gridItem, type === t && s.gridItemActive]}>
                <Text style={[s.gridItemText, type === t && s.gridItemTextActive]}>{t.replace('_', ' ')}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {type === 'terrace' && (
            <Text style={s.terraceHint}>
              Row of terraces — set the number of units below so the auto drop
              deployment plans one drop per unit, not one for the whole row.
            </Text>
          )}

          <Text style={s.fieldLabel}>Number of Units</Text>
          <TextInput style={s.input} placeholder="Enter number of units" placeholderTextColor={COLOR.text500}
            keyboardType="number-pad" value={units} onChangeText={setUnits} />

          <Text style={s.fieldLabel}>Drop Deployment</Text>
          <View style={s.pillRow}>
            {(['aerial', 'underground'] as const).map((d) => (
              <TouchableOpacity key={d} onPress={() => setDrop(drop === d ? '' : d)}
                style={[s.pill, drop === d && s.pillActive]}>
                <Text style={[s.pillText, drop === d && s.pillTextActive]}>{d}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={s.fieldLabel}>Building Condition</Text>
          <View style={s.pillRow}>
            {CONDITIONS.map((c) => (
              <TouchableOpacity key={c} onPress={() => setCondition(c)}
                style={[s.pill, condition === c && s.pillActive]}>
                <Text style={[s.pillText, condition === c && s.pillTextActive]}>{c}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={s.divider} />
          <Text style={s.sectionLabel}>ASSOCIATED ASSETS & NOTES</Text>

          <View style={s.linkRow}>
            {([0, 1] as const).map((slot) => (
              <View key={slot} style={{ flex: 1 }}>
                <TouchableOpacity style={s.linkBox} onPress={() => openManholePicker(slot)}>
                  <Text style={s.linkBoxText} numberOfLines={1}>
                    {links[slot]?.code || `Manhole ${slot === 0 ? 'A' : 'B'}`}
                  </Text>
                  <Text style={s.linkChevron}>{pickerSlot === slot ? '‹' : '›'}</Text>
                </TouchableOpacity>
                {pickerSlot === slot && (
                  <View style={s.linkDropdown}>
                    {manholesLoading ? (
                      <ActivityIndicator color={COLOR.primary700} style={{ margin: SPACE.sm }} />
                    ) : nearbyManholes.length === 0 ? (
                      <Text style={s.linkEmpty}>No nearby manholes found.</Text>
                    ) : nearbyManholes.map((m) => (
                      <TouchableOpacity key={m.id} style={s.linkOption} onPress={() => pickManhole(slot, m)}>
                        <Text style={s.linkOptionText}>{m.code || 'Unnumbered'} · {m.manhole_type} · {m.distance_m}m</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
              </View>
            ))}
          </View>

          <Text style={[s.fieldLabel, { marginTop: SPACE.md }]}>Notes</Text>
          <TextInput style={[s.input, s.notesInput]} placeholder="Add notes about this building…" placeholderTextColor={COLOR.text500}
            multiline value={notes} onChangeText={setNotes} />

          <TouchableOpacity style={s.addMedia} onPress={() => capture('photo')}>
            <Text style={s.addMediaText}>+ Add Photo/Video</Text>
          </TouchableOpacity>
          {media.length > 0 && (
            <View style={s.mediaRow}>
              <Text style={s.mediaCount}>{media.length} attached</Text>
              <TouchableOpacity onPress={() => capture('video')}><Text style={s.mediaVideoLink}>+ add a video too</Text></TouchableOpacity>
            </View>
          )}
          {media.length === 0 && (
            <TouchableOpacity onPress={() => capture('video')} style={{ marginTop: SPACE.xs + 2 }}>
              <Text style={s.mediaVideoLink}>or record a video instead</Text>
            </TouchableOpacity>
          )}

          {err && <Text style={s.err}>{err}</Text>}

          <View style={s.footer}>
            <TouchableOpacity style={[s.draftBtn, savingDraft && { opacity: 0.6 }]}
              onPress={saveDraftNow} disabled={savingDraft || saving}>
              {savingDraft ? <ActivityIndicator color={COLOR.text900} /> : <Text style={s.draftText}>Save draft</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={submitSurvey} disabled={saving || savingDraft}>
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Submit survey</Text>}
            </TouchableOpacity>
          </View>
          <TouchableOpacity onPress={() => { setPick(null); setMedia([]); }}>
            <Text style={s.differentLink}>Pick a different building</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  find: { backgroundColor: COLOR.primary500, borderRadius: RADIUS.sm, padding: 15, alignItems: 'center', minHeight: MIN_TOUCH + 6 },
  findText: { color: '#fff', fontWeight: '700' },
  card: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, padding: SPACE.sm + 4, marginTop: SPACE.sm + 2, borderWidth: 1, borderColor: COLOR.borderDefault },
  code: { fontWeight: '700', color: COLOR.text900 },
  meta: { color: COLOR.text500, marginTop: 2, fontSize: 13 },
  edit: { marginTop: SPACE.md - 2 },
  draftBanner: { backgroundColor: '#FDECE5', borderRadius: RADIUS.sm, padding: SPACE.sm + 2, marginBottom: SPACE.md - 4 },
  draftBannerText: { color: COLOR.accent700, fontSize: 12, fontWeight: '600' },
  sectionLabel: { fontFamily: 'SpaceMono_400Regular', fontSize: 11, letterSpacing: 1, color: COLOR.text500, textTransform: 'uppercase', marginBottom: SPACE.sm },
  fieldLabel: { fontSize: 13, color: COLOR.text500, marginBottom: SPACE.xs + 2, marginTop: SPACE.sm },
  terraceHint: { color: COLOR.text500, fontSize: 12, marginTop: SPACE.xs },
  input: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, padding: 12, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900, minHeight: MIN_TOUCH },
  notesInput: { minHeight: 64, textAlignVertical: 'top' },
  coordRow: { flexDirection: 'row', gap: SPACE.lg, marginBottom: SPACE.sm },
  coordValue: { fontFamily: 'SpaceMono_400Regular', fontSize: 14, fontWeight: '700', color: COLOR.text900 },
  divider: { height: 1, backgroundColor: COLOR.borderDefault, marginVertical: SPACE.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, backgroundColor: COLOR.surface100, borderRadius: RADIUS.lg - 4, padding: 6 },
  gridItem: { width: '48%', minHeight: MIN_TOUCH, borderRadius: RADIUS.sm + 2, alignItems: 'center', justifyContent: 'center' },
  gridItemActive: { backgroundColor: COLOR.surface0 },
  gridItemText: { fontSize: 13, fontWeight: '700', color: COLOR.text500, textTransform: 'capitalize' },
  gridItemTextActive: { color: COLOR.text900 },
  pillRow: { flexDirection: 'row', gap: 6, backgroundColor: COLOR.surface100, borderRadius: RADIUS.full, padding: 6 },
  pill: { flex: 1, minHeight: MIN_TOUCH - 4, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center' },
  pillActive: { backgroundColor: COLOR.surface0 },
  pillText: { fontSize: 12, fontWeight: '700', color: COLOR.text500, textTransform: 'capitalize' },
  pillTextActive: { color: COLOR.text900 },
  linkRow: { flexDirection: 'row', gap: SPACE.sm },
  linkBox: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLOR.borderDefault, paddingHorizontal: 12, minHeight: MIN_TOUCH },
  linkBoxText: { flex: 1, fontSize: 14, color: COLOR.text900 },
  linkChevron: { color: COLOR.text500, fontSize: 14, marginLeft: 4 },
  linkDropdown: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLOR.borderDefault, marginTop: 4, maxHeight: 160, overflow: 'hidden' },
  linkEmpty: { color: COLOR.text500, fontSize: 12, padding: SPACE.sm + 2 },
  linkOption: { padding: SPACE.sm + 2, borderBottomWidth: 1, borderBottomColor: COLOR.surface100, minHeight: MIN_TOUCH, justifyContent: 'center' },
  linkOptionText: { fontSize: 13, color: COLOR.text900 },
  addMedia: { width: '100%', borderWidth: 1, borderStyle: 'dashed', borderColor: COLOR.borderDefault, backgroundColor: COLOR.surface100, borderRadius: RADIUS.sm, minHeight: MIN_TOUCH + 4, alignItems: 'center', justifyContent: 'center', marginTop: SPACE.md },
  addMediaText: { color: COLOR.primary700, fontWeight: '700', fontSize: 14 },
  mediaRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: SPACE.xs + 2 },
  mediaCount: { color: COLOR.text500, fontSize: 13 },
  mediaVideoLink: { color: COLOR.primary700, fontSize: 13, fontWeight: '600' },
  err: { color: COLOR.error, fontSize: 13, marginTop: SPACE.md - 4 },
  footer: { flexDirection: 'row', gap: SPACE.sm + 4, marginTop: SPACE.lg },
  draftBtn: { width: 112, height: 48, borderWidth: 1, borderColor: COLOR.borderDefault, backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, alignItems: 'center', justifyContent: 'center' },
  draftText: { color: COLOR.text900, fontWeight: '700', fontSize: 14 },
  saveBtn: { flex: 1, height: 48, backgroundColor: COLOR.accent500, borderRadius: RADIUS.sm, alignItems: 'center', justifyContent: 'center' },
  saveText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  differentLink: { color: COLOR.primary700, textAlign: 'center', marginTop: SPACE.md - 4 },
});
