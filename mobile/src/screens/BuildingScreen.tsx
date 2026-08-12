import { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { getFix, Fix } from '../gps';
import { authed } from '../auth';
import { enqueue, saveAsset, newId, kvGet } from '../db';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, MIN_TOUCH, isWeb } from '../theme';
import { stampCoordinates } from '../mediaStamp';

// The Claude Design redesign's "Update Building" screen also shows Building
// Condition (Excellent/Good/Fair/Poor) and Associated Assets (linked nearby
// manholes) sections — deliberately left out of this build: the backend has
// no `condition` concept for buildings at all (only manholes have one, on a
// different scale), and no FK/junction table links a building to nearby
// manhole records. Both would need real backend schema work first; adding
// the UI without it would just silently drop whatever a surveyor entered.
const TYPES = ['residential', 'commercial', 'mixed_use', 'institutional', 'religious', 'other'];
type Media = { uri: string; kind: 'photo' | 'video'; contentType: string };

export default function BuildingScreen({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [near, setNear] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState<any | null>(null);
  const [type, setType] = useState('residential');
  const [address, setAddress] = useState('');
  const [units, setUnits] = useState('');
  const [drop, setDrop] = useState<'aerial' | 'underground' | ''>('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [lastFix, setLastFix] = useState<Fix | null>(null);
  const [media, setMedia] = useState<Media[]>([]);

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

  async function save() {
    if (!pick) return;
    setSaving(true);
    try {
      const attrs: any = { building_type: type };
      if (address) attrs.address = address;
      if (units) attrs.units_surveyed = parseInt(units, 10);
      if (drop) attrs.drop_deployment = drop;
      if (notes) attrs.notes = notes;
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
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <View>
      <TouchableOpacity style={s.find} onPress={findNearby} disabled={loading}>
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.findText}>Find buildings near me (GPS)</Text>}
      </TouchableOpacity>

      {!pick && near.map((b) => (
        <TouchableOpacity key={b.id} style={s.card} onPress={() => {
          setPick(b); setType(b.building_type || 'residential');
          setAddress(b.address || ''); setUnits(b.units_surveyed ? String(b.units_surveyed) : '');
          setDrop(b.drop_deployment || ''); setNotes(b.notes || ''); }}>
          <Text style={s.code}>{b.code || 'Unnumbered'} · {b.distance_m} m</Text>
          <Text style={s.meta}>{b.building_type} · {b.use_type}{b.address ? ` · ${b.address}` : ''}</Text>
        </TouchableOpacity>
      ))}

      {pick && (
        <View style={s.edit}>
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
              <Text style={s.coordValue}>{lastFix ? `±${Math.round(lastFix.accuracy)}m` : '—'}</Text>
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

          <View style={s.divider} />
          <Text style={s.sectionLabel}>NOTES</Text>
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

          <View style={s.footer}>
            <TouchableOpacity style={s.cancelBtn} onPress={() => { setPick(null); setMedia([]); onCancel(); }}>
              <Text style={s.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Save Changes</Text>}
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
  sectionLabel: { fontFamily: 'SpaceMono_400Regular', fontSize: 11, letterSpacing: 1, color: COLOR.text500, textTransform: 'uppercase', marginBottom: SPACE.sm },
  fieldLabel: { fontSize: 13, color: COLOR.text500, marginBottom: SPACE.xs + 2, marginTop: SPACE.sm },
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
  pillText: { fontSize: 13, fontWeight: '700', color: COLOR.text500, textTransform: 'capitalize' },
  pillTextActive: { color: COLOR.text900 },
  addMedia: { width: '100%', borderWidth: 1, borderStyle: 'dashed', borderColor: COLOR.borderDefault, backgroundColor: COLOR.surface100, borderRadius: RADIUS.sm, minHeight: MIN_TOUCH + 4, alignItems: 'center', justifyContent: 'center', marginTop: SPACE.md },
  addMediaText: { color: COLOR.primary700, fontWeight: '700', fontSize: 14 },
  mediaRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: SPACE.xs + 2 },
  mediaCount: { color: COLOR.text500, fontSize: 13 },
  mediaVideoLink: { color: COLOR.primary700, fontSize: 13, fontWeight: '600' },
  footer: { flexDirection: 'row', gap: SPACE.sm + 4, marginTop: SPACE.lg },
  cancelBtn: { flex: 1, height: 48, borderWidth: 1, borderColor: COLOR.borderDefault, backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, alignItems: 'center', justifyContent: 'center' },
  cancelText: { color: COLOR.text900, fontWeight: '700', fontSize: 14 },
  saveBtn: { flex: 1, height: 48, backgroundColor: COLOR.accent500, borderRadius: RADIUS.sm, alignItems: 'center', justifyContent: 'center' },
  saveText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  differentLink: { color: COLOR.primary700, textAlign: 'center', marginTop: SPACE.md - 4 },
});
