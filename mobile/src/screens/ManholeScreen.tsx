import { useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { getFix, Fix } from '../gps';
import { enqueue, saveAsset, newId } from '../db';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE as TXT, MIN_TOUCH, isWeb } from '../theme';
import { stampCoordinates } from '../mediaStamp';

const TYPES = ['handhole', 'manhole', 'joint_chamber', 'footway_box', 'other'];
const CONDS = ['good', 'fair', 'poor', 'damaged', 'buried', 'inaccessible', 'unknown'];
type Media = { uri: string; kind: 'photo' | 'video'; contentType: string };

export default function ManholeScreen({ onSaved }: { onSaved: () => void }) {
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixing, setFixing] = useState(true);
  const [type, setType] = useState('manhole');
  const [condition, setCondition] = useState('unknown');
  const [code, setCode] = useState('');
  const [notes, setNotes] = useState('');
  const [media, setMedia] = useState<Media[]>([]);
  const [saving, setSaving] = useState(false);

  async function refix() {
    setFixing(true);
    try { setFix(await getFix()); }
    catch (e: any) { notify('GPS', String(e?.message ?? e)); }
    finally { setFixing(false); }
  }
  useEffect(() => { void refix(); }, []);

  async function capture(kind: 'photo' | 'video') {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { notify('Camera', 'Camera permission is required.'); return; }
    const r = await ImagePicker.launchCameraAsync({
      mediaTypes: kind === 'photo' ? ImagePicker.MediaTypeOptions.Images : ImagePicker.MediaTypeOptions.Videos,
      quality: 0.6, videoMaxDuration: 60,
      // On web this sets the file input's capture="environment" — without
      // it, capture defaults to the less-reliable capture="camera", which
      // some mobile browsers treat as a generic file/gallery chooser
      // instead of jumping straight to the rear camera.
      cameraType: ImagePicker.CameraType.back,
    });
    if (r.canceled) return;
    const a = r.assets[0];
    let uri = a.uri;
    let contentType = a.mimeType ?? (kind === 'photo' ? 'image/jpeg' : 'video/mp4');
    // Burn the GPS fix this capture was taken under into the photo itself
    // (web only — see mediaStamp.ts) so the coordinates travel with the
    // image even if it's later viewed outside the app.
    if (isWeb && kind === 'photo' && fix) {
      try { uri = await stampCoordinates(uri, fix); contentType = 'image/jpeg'; }
      catch { /* stamping is best-effort — keep the unstamped photo on failure */ }
    }
    setMedia((m) => [...m, { uri, kind, contentType }]);
  }

  async function save() {
    if (!fix) { notify('GPS', 'Capture a GPS fix first.'); return; }
    setSaving(true);
    try {
      const clientId = newId('mh');
      // label must stay the raw type ('manhole' | 'handhole' | ...) — it's
      // what pinShape()/pinStatus() key off to pick the map pin shape and
      // the Dashboard status pill. An entered code is still sent to and
      // stored on the server below; it just isn't what drives local shape
      // classification (a stray code string here used to make the pin
      // silently fall back to a generic circle instead of the correct
      // square/triangle marker).
      await saveAsset({ clientId, kind: 'manhole', lat: fix.lat, lon: fix.lon,
        accuracy: fix.accuracy, label: type, sub: condition });
      await enqueue({ clientId, kind: 'manhole', payload: {
        lon: fix.lon, lat: fix.lat, manhole_type: type, condition,
        code: code || null, condition_notes: notes || null,
        gps_accuracy_m: Math.round(fix.accuracy * 100) / 100,
      }});
      for (const m of media) {
        await enqueue({ clientId: newId('md'), kind: 'media', parentClientId: clientId,
          payload: { entityType: 'manhole', kind: m.kind, contentType: m.contentType,
            uri: m.uri, lat: fix.lat, lon: fix.lon } });
      }
      onSaved();
    } finally { setSaving(false); }
  }

  // Rendered inside BottomSheet's own ScrollView (App.tsx) — a plain View
  // here, not a second ScrollView, since nesting two vertical scrollers
  // breaks gesture handling on both native and web.
  return (
    <View>
      <View style={s.gpsCard}>
        <Text style={s.gpsLabel}>GPS FIX</Text>
        {fixing ? <ActivityIndicator color={COLOR.primary900} /> : fix ? (
          <>
            {/* §08: essential field-mode metadata forces high-contrast Text/900,
                bypassing the muted-text hierarchy — Mid Grey fails in direct sun. */}
            <Text style={s.coord}>{fix.lat.toFixed(6)}, {fix.lon.toFixed(6)}</Text>
            <Text style={[s.acc, { color: fix.accuracy <= 10 ? COLOR.success500 : fix.accuracy <= 25 ? COLOR.accent700 : COLOR.error }]}>
              ± {fix.accuracy.toFixed(1)} m
            </Text>
          </>
        ) : <Text style={s.coord}>no fix</Text>}
        <TouchableOpacity style={s.refix} onPress={refix}><Text style={s.refixText}>Re-fix</Text></TouchableOpacity>
      </View>

      <Text style={s.label}>Type</Text>
      <Chips items={TYPES} value={type} onPick={setType} />
      <Text style={s.label}>Condition</Text>
      <Chips items={CONDS} value={condition} onPick={setCondition} />

      <TextInput style={s.input} placeholder="Code (optional)" placeholderTextColor={COLOR.text500} value={code} onChangeText={setCode} />
      <TextInput style={[s.input, { height: 80 }]} placeholder="Condition notes" placeholderTextColor={COLOR.text500} multiline value={notes} onChangeText={setNotes} />

      <View style={s.row}>
        <TouchableOpacity style={s.ghost} onPress={() => capture('photo')}><Text style={s.ghostText}>+ Photo</Text></TouchableOpacity>
        <TouchableOpacity style={s.ghost} onPress={() => capture('video')}><Text style={s.ghostText}>+ Video</Text></TouchableOpacity>
      </View>
      {media.length > 0 && <Text style={s.media}>{media.length} media attached</Text>}

      <TouchableOpacity style={[s.save, (!fix || saving) && { opacity: 0.5 }]} onPress={save} disabled={!fix || saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Save manhole (offline)</Text>}
      </TouchableOpacity>
    </View>
  );
}

function Chips({ items, value, onPick }: { items: string[]; value: string; onPick: (v: string) => void }) {
  return (
    <View style={s.chips}>
      {items.map((it) => (
        <TouchableOpacity key={it} onPress={() => onPick(it)}
          style={[s.chip, value === it && { backgroundColor: COLOR.primary900, borderColor: COLOR.primary900 }]}>
          <Text style={[s.chipText, value === it && { color: '#fff' }]}>{it}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  gpsCard: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, padding: SPACE.md, alignItems: 'center', marginBottom: SPACE.md - 2, borderLeftWidth: 4, borderLeftColor: COLOR.success500 },
  gpsLabel: { ...TXT.mono, fontSize: 10, letterSpacing: 1.5, color: COLOR.text500 },
  coord: { fontSize: 20, fontWeight: '700', color: COLOR.text900, marginTop: 4 },
  acc: { fontSize: 14, fontWeight: '600', marginTop: 2 },
  refix: { marginTop: SPACE.sm, paddingHorizontal: 14, paddingVertical: 6, backgroundColor: COLOR.surface100, borderRadius: RADIUS.sm, minHeight: MIN_TOUCH - 12 },
  refixText: { color: COLOR.primary700, fontWeight: '600' },
  label: { ...TXT.small, color: COLOR.text500, marginTop: SPACE.sm + 2, marginBottom: SPACE.xs + 2, letterSpacing: 0.5 },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  chip: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 7, marginRight: 6, marginBottom: 6, borderWidth: 1, borderColor: COLOR.borderDefault },
  chipText: { color: COLOR.text900, fontSize: 13 },
  input: { backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, padding: 12, marginTop: SPACE.sm, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900 },
  row: { flexDirection: 'row', gap: 10, marginTop: SPACE.md - 4 },
  ghost: { flex: 1, borderWidth: 1, borderColor: COLOR.primary700, borderRadius: RADIUS.sm, padding: 12, alignItems: 'center', minHeight: MIN_TOUCH },
  ghostText: { color: COLOR.primary700, fontWeight: '600' },
  media: { color: COLOR.text500, marginTop: SPACE.sm },
  save: { backgroundColor: COLOR.primary900, borderRadius: RADIUS.sm, padding: 16, alignItems: 'center', marginTop: SPACE.lg - 2, minHeight: MIN_TOUCH + 12 },
  saveText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
