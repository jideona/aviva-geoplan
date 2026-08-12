// Quick building photo capture — deliberately NOT the same as Update
// Building (BuildingScreen.tsx), which requires finding and picking an
// existing building footprint before editing its attributes. This is the
// fast path: snap a photo, the GPS fix is captured and shown right away so
// the surveyor can see it's right, then Save. No lookup, no form — the
// point this creates shows up as a house icon on the map (MapScreen.web.tsx)
// for anyone else to tap and view the photo, on both mobile and desktop.
import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { getFix, Fix } from '../gps';
import { enqueue, saveAsset, newId } from '../db';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE as TXT, MIN_TOUCH, isWeb } from '../theme';
import { stampCoordinates } from '../mediaStamp';

export default function BuildingPhotoScreen({ onSaved }: { onSaved: () => void }) {
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixing, setFixing] = useState(true);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [contentType, setContentType] = useState('image/jpeg');
  const [saving, setSaving] = useState(false);

  async function refix() {
    setFixing(true);
    try { setFix(await getFix()); }
    catch (e: any) { notify('GPS', String(e?.message ?? e)); }
    finally { setFixing(false); }
  }
  useEffect(() => { void refix(); }, []);

  async function capture() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { notify('Camera', 'Camera permission is required.'); return; }
    const r = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images, quality: 0.6,
      cameraType: ImagePicker.CameraType.back,
    });
    if (r.canceled) return;
    // Re-fix at the moment of capture — more accurate than whatever was read
    // when the screen first opened (the surveyor may have walked since
    // then), and the coordinates on screen update to match, so what's shown
    // is what actually gets saved.
    let capturedFix = fix;
    try { capturedFix = await getFix(); setFix(capturedFix); } catch { /* keep the earlier fix */ }
    const a = r.assets[0];
    let uri = a.uri;
    let ct = a.mimeType ?? 'image/jpeg';
    if (isWeb && capturedFix) {
      try { uri = await stampCoordinates(uri, capturedFix); ct = 'image/jpeg'; }
      catch { /* stamping is best-effort — keep the unstamped photo on failure */ }
    }
    setPhotoUri(uri); setContentType(ct);
  }

  async function save() {
    if (!fix || !photoUri) return;
    setSaving(true);
    try {
      const clientId = newId('bp');
      await saveAsset({
        clientId, kind: 'building_photo', lat: fix.lat, lon: fix.lon,
        accuracy: fix.accuracy, label: 'building_photo',
      });
      await enqueue({ clientId, kind: 'building_photo', payload: {
        lon: fix.lon, lat: fix.lat, gps_accuracy_m: Math.round(fix.accuracy * 100) / 100,
      }});
      await enqueue({ clientId: newId('md'), kind: 'media', parentClientId: clientId,
        payload: { entityType: 'building_photo', kind: 'photo', contentType,
          uri: photoUri, lat: fix.lat, lon: fix.lon } });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <View>
      <View style={s.gpsCard}>
        <Text style={s.gpsLabel}>GPS FIX</Text>
        {fixing ? <ActivityIndicator color={COLOR.primary900} /> : fix ? (
          <>
            <Text style={s.coord}>{fix.lat.toFixed(6)}, {fix.lon.toFixed(6)}</Text>
            <Text style={[s.acc, { color: fix.accuracy <= 10 ? COLOR.success500 : fix.accuracy <= 25 ? COLOR.accent700 : COLOR.error }]}>
              ± {fix.accuracy.toFixed(1)} m
            </Text>
          </>
        ) : <Text style={s.coord}>no fix</Text>}
        <TouchableOpacity style={s.refix} onPress={refix}><Text style={s.refixText}>Re-fix</Text></TouchableOpacity>
      </View>

      <TouchableOpacity style={s.captureBtn} onPress={capture}>
        <Text style={s.captureBtnText}>{photoUri ? '↻ Retake photo' : '+ Take photo'}</Text>
      </TouchableOpacity>
      {photoUri && (
        <Text style={s.confirmed}>Photo captured at the coordinates above — ready to save.</Text>
      )}

      <TouchableOpacity style={[s.save, (!fix || !photoUri || saving) && { opacity: 0.5 }]}
        onPress={save} disabled={!fix || !photoUri || saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Save (offline)</Text>}
      </TouchableOpacity>
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
  captureBtn: { borderWidth: 1, borderColor: COLOR.primary700, borderRadius: RADIUS.sm, padding: 14, alignItems: 'center', minHeight: MIN_TOUCH + 4, marginTop: SPACE.sm },
  captureBtnText: { color: COLOR.primary700, fontWeight: '700', fontSize: 15 },
  confirmed: { color: COLOR.success500, fontWeight: '600', fontSize: 13, textAlign: 'center', marginTop: SPACE.sm },
  save: { backgroundColor: COLOR.primary900, borderRadius: RADIUS.sm, padding: 16, alignItems: 'center', marginTop: SPACE.lg - 2, minHeight: MIN_TOUCH + 12 },
  saveText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
