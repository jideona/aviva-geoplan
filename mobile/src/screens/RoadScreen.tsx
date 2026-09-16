import { useEffect, useRef, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import { authed } from '../auth';
import { enqueue, kvGet, listServerFeatures, newId, saveAsset } from '../db';
import { getFix, watchRoute, type Fix } from '../gps';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH } from '../theme';
import { Icon } from '../components/Icon';

const SURFACES = ['asphalt', 'concrete', 'paving', 'compacted_earth', 'unpaved', 'unknown'];
const CONDITIONS = ['good', 'fair', 'poor', 'impassable', 'unknown'];
const ACCESS = ['public', 'gated', 'restricted', 'private', 'unknown'];
const ROAD_CLASSES = ['primary', 'secondary', 'tertiary', 'residential', 'service', 'track', 'footway', 'unknown'];

type NearbyStreet = {
  id: string; code: string; name?: string | null; distance_m: number;
  road_class: string; surface?: string; condition?: string; access?: string;
  width_m?: number | null; verification_state?: string;
};

function hv(a:number[],b:number[]){const R=6371000,t=Math.PI/180;const dLat=(b[1]-a[1])*t,dLon=(b[0]-a[0])*t;const h=Math.sin(dLat/2)**2+Math.cos(a[1]*t)*Math.cos(b[1]*t)*Math.sin(dLon/2)**2;return 2*R*Math.asin(Math.sqrt(h));}
function cachedStreetDistance(f:any, lon:number, lat:number){const g=f?.geometry;const lines=g?.type==='MultiLineString'?g.coordinates:g?.type==='LineString'?[g.coordinates]:[];let best=Infinity;for(const line of lines)for(const p of line)best=Math.min(best,hv([lon,lat],p));return best;}

export default function RoadScreen({
  onSaved,
  onCancel,
  edit,
}: {
  onSaved: () => void;
  onCancel: () => void;
  edit?: any | null;
}) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [nearby, setNearby] = useState<NearbyStreet[]>([]);
  const [selected, setSelected] = useState<NearbyStreet | null>(null);
  const [busy, setBusy] = useState(true);
  const [name, setName] = useState('');
  const [roadClass, setRoadClass] = useState('unknown');
  const [surface, setSurface] = useState('unknown');
  const [condition, setCondition] = useState('unknown');
  const [access, setAccess] = useState('unknown');
  const [width, setWidth] = useState('');
  const [notes, setNotes] = useState('');
  const [recordNew, setRecordNew] = useState(false);
  const [recording, setRecording] = useState(false);
  const [points, setPoints] = useState<number[][]>([]);
  const stopRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    (async () => {
      const pid = await kvGet('projectId');
      setProjectId(pid);
      if (!pid) { setBusy(false); return; }

      if (edit) {
        choose({
          ...edit,
          id: String(edit.id),
          code: edit.code ?? '',
          distance_m: 0,
        });
        setBusy(false);
        return;
      }

      try {
        const fix = await getFix();
        let rows: NearbyStreet[] = [];
        try {
          const res = await authed(`/api/v1/projects/${pid}/mobile/streets/near?lat=${fix.lat}&lon=${fix.lon}&limit=10`);
          if (res.ok) rows = (await res.json()).streets ?? [];
        } catch { /* fall back to shared offline cache below */ }
        if (!rows.length) {
          const cached = await listServerFeatures(pid, 'streets');
          rows = cached.map((f:any) => ({
            id: String(f.properties?.id), code: String(f.properties?.code ?? ''), name: f.properties?.name,
            road_class: f.properties?.road_class ?? 'unknown', surface: f.properties?.surface ?? 'unknown',
            condition: f.properties?.condition ?? 'unknown', access: f.properties?.access ?? 'unknown',
            width_m: f.properties?.width_m ?? null, verification_state: f.properties?.verification_state,
            distance_m: cachedStreetDistance(f, fix.lon, fix.lat),
          })).sort((a,b)=>a.distance_m-b.distance_m).slice(0,10);
        }
        setNearby(rows);
      } catch { /* GPS unavailable — manual/new-road capture can still be attempted later */ }
      setBusy(false);
    })();
    return () => stopRef.current?.();
  }, []);

  function choose(s: NearbyStreet | any) {
    setSelected(s);
    setRecordNew(false);
    setName(s.name ?? '');
    setRoadClass(s.road_class ?? 'unknown');
    setSurface(s.surface ?? 'unknown');
    setCondition(s.condition ?? 'unknown');
    setAccess(s.access ?? 'unknown');
    setWidth(s.width_m != null ? String(s.width_m) : '');
    setNotes(s.field_notes ?? '');
  }

  async function saveExisting() {
    if (!projectId || !selected) return;
    const clientId = newId('st');
    const attrs = {
      name: name.trim() || undefined, road_class: roadClass, surface, condition, access,
      width_m: width.trim() ? Number(width) : undefined, field_notes: notes.trim() || undefined,
    };
    await enqueue({ clientId, kind: 'street', payload: { streetId: selected.id, attrs } });
    try {
      const f = await getFix();
      await saveAsset({ clientId, kind: 'street', lat: f.lat, lon: f.lon, accuracy: f.accuracy,
        label: name.trim() || selected.code, sub: 'field verification' });
    } catch { /* queued update is still valid */ }
    notify('Road saved', `${name.trim() || selected.code} queued for sync.`);
    onSaved();
  }

  async function startNew() {
    setRecordNew(true); setSelected(null); setPoints([]); setRecording(true);
    try {
      stopRef.current = await watchRoute(8, (f: Fix) => {
        if (f.accuracy > 25) return;
        setPoints((prev) => {
          const next = [...prev, [f.lon, f.lat]];
          return next;
        });
      });
    } catch (e: any) {
      setRecording(false); notify('GPS', String(e?.message ?? e));
    }
  }

  function pauseNew() { stopRef.current?.(); stopRef.current = null; setRecording(false); }
  async function resumeNew() {
    setRecording(true);
    try {
      stopRef.current = await watchRoute(8, (f: Fix) => {
        if (f.accuracy <= 25) setPoints((prev) => [...prev, [f.lon, f.lat]]);
      });
    } catch (e: any) { setRecording(false); notify('GPS', String(e?.message ?? e)); }
  }

  async function finishNew() {
    stopRef.current?.(); stopRef.current = null; setRecording(false);
    if (points.length < 2) { notify('Road', 'Record at least two GPS points.'); return; }
    const clientId = newId('st');
    await enqueue({ clientId, kind: 'street', payload: {
      points, name: name.trim() || undefined, road_class: roadClass, surface, condition, access,
      width_m: width.trim() ? Number(width) : undefined, field_notes: notes.trim() || undefined,
    }});
    const last = points[points.length - 1];
    await saveAsset({ clientId, kind: 'street', lat: last[1], lon: last[0], accuracy: 0,
      label: name.trim() || 'New road', sub: `${points.length} GPS points` });
    notify('Road recorded', `${points.length} points queued for sync.`);
    onSaved();
  }

  if (busy) return <View style={s.center}><ActivityIndicator color={COLOR.primary900} /></View>;

  return (
    <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
      {!edit && !recordNew && !selected && <>
        <Text style={s.section}>NEARBY ROADS / STREETS</Text>
        <Text style={s.help}>Choose an existing road first. Only record a new road if the real road is missing from GeoPlan.</Text>
        {nearby.map((r) => (
          <TouchableOpacity key={r.id} style={s.nearRow} onPress={() => choose(r)}>
            <Icon name="road" size={20} color={COLOR.primary700} />
            <View style={{ flex: 1 }}>
              <Text style={s.rowTitle}>{r.name || r.code}</Text>
              <Text style={s.rowSub}>{r.code} · {Math.round(r.distance_m)} m away · {r.verification_state ?? 'imported'}</Text>
            </View>
            <Icon name="chevronRight" size={16} color={COLOR.text500} />
          </TouchableOpacity>
        ))}
        <TouchableOpacity style={s.secondary} onPress={startNew}>
          <Icon name="capture" size={18} color={COLOR.primary700} />
          <Text style={s.secondaryText}>Record a missing road</Text>
        </TouchableOpacity>
      </>}

      {(selected || recordNew) && <>
        <View style={s.modeHeader}>
          <Text style={s.section}>{recordNew ? 'NEW ROAD GPS TRACE' : `VERIFY ${selected?.code}`}</Text>
          {!edit && (
            <TouchableOpacity onPress={() => { stopRef.current?.(); setRecording(false); setRecordNew(false); setSelected(null); }}>
              <Text style={s.change}>Change</Text>
            </TouchableOpacity>
          )}
        </View>
        {recordNew && <View style={s.recordCard}>
          <Text style={s.recordValue}>{points.length} GPS points</Text>
          <Text style={s.help}>{recording ? 'Recording — walk or drive along the road.' : 'Recording paused.'}</Text>
          <View style={s.rowButtons}>
            {recording
              ? <TouchableOpacity style={s.secondarySmall} onPress={pauseNew}><Text style={s.secondaryText}>Pause</Text></TouchableOpacity>
              : <TouchableOpacity style={s.secondarySmall} onPress={resumeNew}><Text style={s.secondaryText}>Resume</Text></TouchableOpacity>}
          </View>
        </View>}
        <Field label="Street name" value={name} onChange={setName} placeholder="e.g. Wuye Crescent" />
        <Choice label="Road class" value={roadClass} values={ROAD_CLASSES} onChange={setRoadClass} />
        <Choice label="Surface" value={surface} values={SURFACES} onChange={setSurface} />
        <Choice label="Condition" value={condition} values={CONDITIONS} onChange={setCondition} />
        <Choice label="Access" value={access} values={ACCESS} onChange={setAccess} />
        <Field label="Approx. width (m)" value={width} onChange={setWidth} placeholder="e.g. 7.5" keyboardType="decimal-pad" />
        <Field label="Field notes" value={notes} onChange={setNotes} placeholder="Access restrictions, drainage, obstacles…" multiline />
        <TouchableOpacity style={s.primary} onPress={recordNew ? finishNew : saveExisting}>
          <Text style={s.primaryText}>
            {recordNew
              ? 'Finish & save road'
              : edit
                ? 'Save road update'
                : 'Save road verification'}
          </Text>
        </TouchableOpacity>
      </>}
      <TouchableOpacity style={s.cancel} onPress={onCancel}><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>
    </ScrollView>
  );
}

function Field({ label, value, onChange, placeholder, multiline, keyboardType }: any) {
  return <View style={s.field}><Text style={s.label}>{label}</Text><TextInput style={[s.input, multiline && { minHeight: 80, textAlignVertical: 'top' }]}
    value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={COLOR.text500}
    multiline={multiline} keyboardType={keyboardType} /></View>;
}
function Choice({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (v: string) => void }) {
  return <View style={s.field}><Text style={s.label}>{label}</Text><View style={s.chips}>{values.map((v) => <TouchableOpacity key={v}
    style={[s.chip, value === v && s.chipActive]} onPress={() => onChange(v)}><Text style={[s.chipText, value === v && s.chipTextActive]}>{v.replace('_', ' ')}</Text></TouchableOpacity>)}</View></View>;
}

const s = StyleSheet.create({
  body: { padding: SPACE.md, paddingBottom: SPACE.xl, gap: SPACE.sm }, center: { padding: 40, alignItems: 'center' },
  section: { ...TYPE.mono, fontSize: 12, color: COLOR.primary700, letterSpacing: 0.6, fontWeight: '700' },
  help: { ...TYPE.small, color: COLOR.text500, lineHeight: 18 }, nearRow: { flexDirection: 'row', alignItems: 'center', gap: SPACE.sm,
    padding: SPACE.sm + 4, backgroundColor: COLOR.surface0, borderWidth: 1, borderColor: COLOR.borderCard, borderRadius: RADIUS.md },
  rowTitle: { ...TYPE.bodyBold, color: COLOR.text900 }, rowSub: { ...TYPE.small, color: COLOR.text500, marginTop: 2 },
  secondary: { minHeight: MIN_TOUCH, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1,
    borderColor: COLOR.primary700, borderRadius: RADIUS.md, marginTop: SPACE.sm }, secondarySmall: { borderWidth: 1, borderColor: COLOR.primary700, borderRadius: RADIUS.md, padding: 10 },
  secondaryText: { ...TYPE.bodyBold, color: COLOR.primary700 }, modeHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  change: { ...TYPE.small, color: COLOR.primary700, fontWeight: '700' }, recordCard: { backgroundColor: COLOR.neutralTint, borderRadius: RADIUS.md, padding: SPACE.sm + 4 },
  recordValue: { ...TYPE.h3, color: COLOR.primary900 }, rowButtons: { flexDirection: 'row', marginTop: 8 }, field: { gap: 6 }, label: { ...TYPE.small, color: COLOR.text900, fontWeight: '700' },
  input: { ...TYPE.body, minHeight: MIN_TOUCH, borderWidth: 1, borderColor: COLOR.borderDefault, borderRadius: RADIUS.md, backgroundColor: COLOR.surface0, padding: 12, color: COLOR.text900 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 }, chip: { borderWidth: 1, borderColor: COLOR.borderDefault, borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: COLOR.surface0 },
  chipActive: { backgroundColor: COLOR.primary900, borderColor: COLOR.primary900 }, chipText: { ...TYPE.small, color: COLOR.text500 }, chipTextActive: { color: '#fff' },
  primary: { minHeight: MIN_TOUCH, backgroundColor: COLOR.primary700, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center', marginTop: SPACE.sm },
  primaryText: { ...TYPE.bodyBold, color: '#fff' }, cancel: { minHeight: MIN_TOUCH, alignItems: 'center', justifyContent: 'center' }, cancelText: { ...TYPE.bodyBold, color: COLOR.text500 },
});
