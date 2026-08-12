import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform, ActivityIndicator } from 'react-native';
import MapView, { Marker, Polyline, PROVIDER_GOOGLE, Region } from 'react-native-maps';
import { getFix, watchRoute, Fix } from '../gps';
import { enqueue, saveAsset, saveRoute, newId, listAssets, listRoutes } from '../db';
import { COLOR, STATUS } from '../theme';
import { pinStatus } from '../pinStatus';
import { notify } from '../notify';

type Mode = 'none' | 'manhole' | 'handhole' | 'record';
type LL = { latitude: number; longitude: number };

function haversine(a: number[], b: number[]): number {
  const R = 6371000, toR = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toR, dLon = (b[0] - a[0]) * toR;
  const lat1 = a[1] * toR, lat2 = b[1] * toR;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
const lineLength = (pts: number[][]) =>
  pts.slice(1).reduce((s, p, i) => s + haversine(pts[i], p), 0);

export default function MapScreen({ onBack }: { onBack: () => void }) {
  const [region, setRegion] = useState<Region | null>(null);
  const [mode, setMode] = useState<Mode>('none');
  const [pin, setPin] = useState<LL | null>(null);
  const [manholes, setManholes] = useState<any[]>([]);
  const [routes, setRoutes] = useState<any[]>([]);
  const [recording, setRecording] = useState(false);
  const [recPts, setRecPts] = useState<number[][]>([]);   // [lon,lat]
  const [busy, setBusy] = useState(false);
  const stopRef = useRef<null | (() => void)>(null);

  async function reload() {
    setManholes((await listAssets()).filter((a) => a.kind === 'manhole'));
    setRoutes(await listRoutes());
  }

  useEffect(() => {
    (async () => {
      try {
        const f = await getFix();
        setRegion({ latitude: f.lat, longitude: f.lon, latitudeDelta: 0.004, longitudeDelta: 0.004 });
      } catch (e: any) { notify('GPS', String(e?.message ?? e)); }
      await reload();
    })();
    return () => { stopRef.current?.(); };
  }, []);

  function onMapPress(e: any) {
    if (mode === 'manhole' || mode === 'handhole') setPin(e.nativeEvent.coordinate);
  }

  async function savePin(condition: string) {
    if (!pin) return;
    setBusy(true);
    try {
      const clientId = newId('mh');
      await saveAsset({ clientId, kind: 'manhole', lat: pin.latitude, lon: pin.longitude,
        accuracy: 0, label: mode, sub: condition });
      await enqueue({ clientId, kind: 'manhole', payload: {
        lon: pin.longitude, lat: pin.latitude, manhole_type: mode, condition } });
      setPin(null); setMode('none'); await reload();
    } finally { setBusy(false); }
  }

  async function startRecord() {
    setRecPts([]); setRecording(true); setMode('record');
    try {
      stopRef.current = await watchRoute(8, (f: Fix) =>
        setRecPts((p) => [...p, [f.lon, f.lat]]));
    } catch (e: any) { notify('GPS', String(e?.message ?? e)); setRecording(false); }
  }

  async function stopRecord() {
    stopRef.current?.(); stopRef.current = null; setRecording(false);
    const pts = recPts;
    if (pts.length < 2) { notify('Route', 'Walk a bit further — need at least two points.'); setMode('none'); return; }
    setBusy(true);
    try {
      const clientId = newId('rt');
      const len = lineLength(pts);
      await saveRoute({ clientId, routeType: 'cable_route', points: pts, lengthM: len });
      await enqueue({ clientId, kind: 'route', payload: { points: pts, route_type: 'cable_route' } });
      setRecPts([]); setMode('none'); await reload();
      notify('Route saved', `${Math.round(len)} m over ${pts.length} points (offline).`);
    } finally { setBusy(false); }
  }

  if (!region) return <View style={s.center}><ActivityIndicator color={COLOR.primary900} /></View>;

  return (
    <View style={{ flex: 1 }}>
      <MapView style={{ flex: 1 }} initialRegion={region}
        provider={Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined}
        showsUserLocation showsMyLocationButton onPress={onMapPress}>
        {manholes.map((m) => (
          <Marker key={m.client_id} coordinate={{ latitude: m.lat, longitude: m.lon }}
            pinColor={STATUS[pinStatus(m)]}
            title={m.label} description={m.synced ? 'synced' : 'pending'} />
        ))}
        {routes.map((r) => {
          const pts = JSON.parse(r.points).map((p: number[]) => ({ latitude: p[1], longitude: p[0] }));
          return <Polyline key={r.client_id} coordinates={pts}
            strokeColor={r.synced ? COLOR.success500 : COLOR.text500} strokeWidth={4} />;
        })}
        {pin && <Marker coordinate={pin} pinColor={COLOR.success500} />}
        {recPts.length > 1 && <Polyline
          coordinates={recPts.map((p) => ({ latitude: p[1], longitude: p[0] }))}
          strokeColor={COLOR.error} strokeWidth={5} />}
      </MapView>

      <TouchableOpacity style={s.backBtn} onPress={onBack}>
        <Text style={s.backIcon}>←</Text>
      </TouchableOpacity>

      {/* Pin-drop confirm sheet */}
      {pin && (mode === 'manhole' || mode === 'handhole') && (
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Place {mode} here?</Text>
          <Text style={s.sheetCoord}>{pin.latitude.toFixed(6)}, {pin.longitude.toFixed(6)}</Text>
          <View style={s.condRow}>
            {['good', 'fair', 'poor', 'damaged', 'unknown'].map((c) => (
              <TouchableOpacity key={c} style={s.cond} disabled={busy} onPress={() => savePin(c)}>
                <Text style={s.condText}>{c}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity onPress={() => setPin(null)}><Text style={s.cancel}>Cancel</Text></TouchableOpacity>
        </View>
      )}

      {/* Recording banner */}
      {recording && (
        <View style={s.recBanner}>
          <View style={s.recDot} />
          <Text style={s.recText}>Recording route · {recPts.length} pts · {Math.round(lineLength(recPts))} m</Text>
        </View>
      )}

      {/* Bottom controls */}
      <View style={s.controls}>
        {!recording ? (
          <>
            <Ctrl label="Manhole pin" active={mode === 'manhole'}
              onPress={() => { setMode(mode === 'manhole' ? 'none' : 'manhole'); setPin(null); }} />
            <Ctrl label="Handhole pin" active={mode === 'handhole'}
              onPress={() => { setMode(mode === 'handhole' ? 'none' : 'handhole'); setPin(null); }} />
            <Ctrl label="Record route" primary onPress={startRecord} />
          </>
        ) : (
          <TouchableOpacity style={[s.ctrl, { backgroundColor: COLOR.error, flex: 1 }]} onPress={stopRecord} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={[s.ctrlText, { color: '#fff' }]}>Stop & save route</Text>}
          </TouchableOpacity>
        )}
      </View>
      {(mode === 'manhole' || mode === 'handhole') && !pin && (
        <View style={s.hint}><Text style={s.hintText}>Tap the map to drop the {mode} pin</Text></View>
      )}
    </View>
  );
}

function Ctrl({ label, onPress, active, primary }: { label: string; onPress: () => void; active?: boolean; primary?: boolean }) {
  return (
    <TouchableOpacity onPress={onPress}
      style={[s.ctrl, active && { backgroundColor: COLOR.primary900 }, primary && { backgroundColor: COLOR.success500 }]}>
      <Text style={[s.ctrlText, (active || primary) && { color: '#fff' }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  backBtn: {
    position: 'absolute', top: 16, left: 12, width: 44, height: 44, borderRadius: 22,
    backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center',
    elevation: 3, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 4, shadowOffset: { width: 0, height: 2 },
  },
  backIcon: { fontSize: 20, color: COLOR.primary900, fontWeight: '700' },
  controls: { position: 'absolute', bottom: 24, left: 12, right: 12, flexDirection: 'row', gap: 8 },
  ctrl: { flex: 1, backgroundColor: '#fff', borderRadius: 8, paddingVertical: 12, alignItems: 'center', elevation: 3, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 4, shadowOffset: { width: 0, height: 2 } },
  ctrlText: { color: COLOR.primary900, fontWeight: '700', fontSize: 13 },
  hint: { position: 'absolute', top: 12, alignSelf: 'center', backgroundColor: COLOR.primary900, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 7 },
  hintText: { color: '#fff', fontSize: 13 },
  recBanner: { position: 'absolute', top: 12, alignSelf: 'center', backgroundColor: '#fff', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', elevation: 3 },
  recDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLOR.error, marginRight: 8 },
  recText: { color: COLOR.primary900, fontWeight: '600' },
  sheet: { position: 'absolute', bottom: 84, left: 12, right: 12, backgroundColor: '#fff', borderRadius: 12, padding: 16, elevation: 4 },
  sheetTitle: { fontWeight: '700', color: COLOR.primary900, fontSize: 15 },
  sheetCoord: { color: COLOR.text500, marginTop: 2, marginBottom: 10 },
  condRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  cond: { backgroundColor: COLOR.surface100, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 7 },
  condText: { color: COLOR.primary900, fontWeight: '600', fontSize: 13 },
  cancel: { color: COLOR.primary700, textAlign: 'center', marginTop: 12 },
});
