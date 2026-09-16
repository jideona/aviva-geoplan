import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, TextInput } from 'react-native';
import { watchRoute, type Fix } from '../gps';
import { enqueue, kvGet, listServerFeatures, loadActiveRoute, newId, saveActiveRoute, saveRoute } from '../db';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH } from '../theme';

const ROUTE_TYPES = ['cable_route', 'existing_fibre', 'existing_duct', 'proposed_duct', 'proposed_trench', 'aerial_route', 'distribution_route', 'feeder_route', 'site_access', 'walk', 'other'];
function haversine(a: number[], b: number[]) { const R=6371000, t=Math.PI/180; const dLat=(b[1]-a[1])*t,dLon=(b[0]-a[0])*t; const h=Math.sin(dLat/2)**2+Math.cos(a[1]*t)*Math.cos(b[1]*t)*Math.sin(dLon/2)**2; return 2*R*Math.asin(Math.sqrt(h)); }
const lengthM=(p:number[][])=>p.slice(1).reduce((n,x,i)=>n+haversine(p[i],x),0);

export default function RouteCaptureScreen({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [points, setPoints] = useState<number[][]>([]);
  const [accuracies, setAccuracies] = useState<number[]>([]);
  const [recording, setRecording] = useState(false);
  const [routeType, setRouteType] = useState('cable_route');
  const [notes, setNotes] = useState('');
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [nearbyRoutes, setNearbyRoutes] = useState<any[]>([]);
  const stopRef = useRef<null | (() => void)>(null);

  useEffect(() => { (async()=>{ const pid=await kvGet('projectId'); setProjectId(pid); if(pid){ const d=await loadActiveRoute(pid); if(d){ setPoints(d.points??[]); setAccuracies(d.accuracies??[]); setRouteType(d.routeType??'cable_route'); setNotes(d.notes??''); setStartedAt(d.startedAt??null); } try { const f=await (await import('../gps')).getFix(); const cached=await listServerFeatures(pid,'routes'); const near=cached.map((r:any)=>{const pts=r.geometry?.coordinates??[];const dist=pts.reduce((m:number,p:number[])=>Math.min(m,haversine([f.lon,f.lat],p)),Infinity);return {...r,_distance:dist};}).filter((r:any)=>r._distance<=75).sort((a:any,b:any)=>a._distance-b._distance).slice(0,3); setNearbyRoutes(near); } catch {} } })(); return()=>stopRef.current?.(); },[]);

  async function persist(nextPts=points, nextAcc=accuracies) { if(projectId) await saveActiveRoute(projectId,{points:nextPts,accuracies:nextAcc,routeType,notes,startedAt:startedAt??new Date().toISOString()}); }
  async function start() { if(!projectId)return; if(!startedAt)setStartedAt(new Date().toISOString()); setRecording(true); try { stopRef.current=await watchRoute(8,(f:Fix)=>{ if(f.accuracy>25)return; setPoints(prev=>{ const next=[...prev,[f.lon,f.lat]]; setAccuracies(ap=>{const na=[...ap,f.accuracy]; void persist(next,na); return na;}); return next;});}); } catch(e:any){setRecording(false);notify('GPS',String(e?.message??e));} }
  function pause(){stopRef.current?.();stopRef.current=null;setRecording(false);void persist();}
  async function finish(){pause(); if(!projectId)return; if(points.length<2){notify('Route','Walk or drive further — at least two GPS points are required.');return;} const clientId=newId('rt'); const len=lengthM(points); const avg=accuracies.length?accuracies.reduce((a,b)=>a+b,0)/accuracies.length:undefined; await saveRoute({clientId,routeType,points,lengthM:len}); await enqueue({clientId,kind:'route',payload:{points,route_type:routeType,notes:notes.trim()||undefined,avg_accuracy_m:avg}}); await saveActiveRoute(projectId,null); notify('Route saved',`${Math.round(len)} m · ${points.length} points queued for sync.`); onSaved();}
  async function discard(){stopRef.current?.(); if(projectId)await saveActiveRoute(projectId,null); onCancel();}
  const elapsed=startedAt?Math.max(0,Math.floor((Date.now()-new Date(startedAt).getTime())/1000)):0;
  return <ScrollView contentContainerStyle={s.body}>
    <Text style={s.section}>TRACK SURVEY ROUTE</Text>
    <Text style={s.help}>GPS points are stored locally while you work. Losing signal will not lose the route.</Text>
    {nearbyRoutes.length>0&&<View style={s.near}><Text style={s.nearTitle}>Existing survey work nearby</Text>{nearbyRoutes.map((r:any)=><Text key={r.properties?.id} style={s.help}>{Math.round(r._distance)} m · {String(r.properties?.type||'route').replace('_',' ')} · {r.properties?.surveyed_by||'another surveyor'}</Text>)}<Text style={s.help}>Review the map before recording a duplicate corridor.</Text></View>}
    <View style={s.stats}><Stat label="DISTANCE" value={`${Math.round(lengthM(points))} m`} /><Stat label="POINTS" value={String(points.length)} /><Stat label="ELAPSED" value={`${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')}`} /></View>
    <Text style={s.label}>Route type</Text><View style={s.chips}>{ROUTE_TYPES.map(v=><TouchableOpacity key={v} style={[s.chip,routeType===v&&s.chipActive]} onPress={()=>setRouteType(v)}><Text style={[s.chipText,routeType===v&&s.chipTextActive]}>{v.replace('_',' ')}</Text></TouchableOpacity>)}</View>
    <Text style={s.label}>Notes</Text><TextInput style={s.input} value={notes} onChangeText={setNotes} placeholder="Existing duct, obstruction, proposed trench…" placeholderTextColor={COLOR.text500} multiline />
    {!recording?<TouchableOpacity style={s.primary} onPress={start}><Text style={s.primaryText}>{points.length?'Resume recording':'Start recording'}</Text></TouchableOpacity>:<TouchableOpacity style={s.pause} onPress={pause}><Text style={s.primaryText}>Pause recording</Text></TouchableOpacity>}
    {points.length>=2&&<TouchableOpacity style={s.finish} onPress={finish}><Text style={s.finishText}>Finish & save route</Text></TouchableOpacity>}
    <TouchableOpacity style={s.cancel} onPress={discard}><Text style={s.cancelText}>Discard / close</Text></TouchableOpacity>
  </ScrollView>;
}
function Stat({label,value}:{label:string;value:string}){return <View style={{flex:1}}><Text style={s.statValue}>{value}</Text><Text style={s.statLabel}>{label}</Text></View>}
const s=StyleSheet.create({body:{padding:SPACE.md,paddingBottom:SPACE.xl,gap:SPACE.sm},section:{...TYPE.mono,fontWeight:'700',fontSize:12,color:COLOR.primary700},help:{...TYPE.small,color:COLOR.text500},stats:{flexDirection:'row',backgroundColor:COLOR.neutralTint,borderRadius:RADIUS.md,padding:SPACE.md},statValue:{...TYPE.h3,color:COLOR.primary900},statLabel:{...TYPE.mono,fontSize:10,color:COLOR.text500},label:{...TYPE.small,fontWeight:'700',color:COLOR.text900},chips:{flexDirection:'row',flexWrap:'wrap',gap:6},chip:{borderWidth:1,borderColor:COLOR.borderDefault,borderRadius:RADIUS.full,paddingHorizontal:10,paddingVertical:7},chipActive:{backgroundColor:COLOR.primary900,borderColor:COLOR.primary900},chipText:{...TYPE.small,color:COLOR.text500},chipTextActive:{color:'#fff'},input:{...TYPE.body,minHeight:80,borderWidth:1,borderColor:COLOR.borderDefault,borderRadius:RADIUS.md,padding:12,textAlignVertical:'top',color:COLOR.text900},primary:{minHeight:MIN_TOUCH,backgroundColor:COLOR.primary700,borderRadius:RADIUS.md,alignItems:'center',justifyContent:'center'},pause:{minHeight:MIN_TOUCH,backgroundColor:COLOR.accent500,borderRadius:RADIUS.md,alignItems:'center',justifyContent:'center'},primaryText:{...TYPE.bodyBold,color:'#fff'},finish:{minHeight:MIN_TOUCH,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.success500,alignItems:'center',justifyContent:'center'},finishText:{...TYPE.bodyBold,color:COLOR.success500},cancel:{minHeight:MIN_TOUCH,alignItems:'center',justifyContent:'center'},near:{backgroundColor:COLOR.neutralTint,borderRadius:RADIUS.md,padding:SPACE.sm+4},nearTitle:{...TYPE.bodyBold,color:COLOR.primary900,marginBottom:4},cancelText:{...TYPE.bodyBold,color:COLOR.text500}});
