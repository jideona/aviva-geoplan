import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { authed } from '../auth';
import { kvGet, pendingCount, listServerFeatures, serverCacheCounts } from '../db';
import { pullChanges, runSync } from '../sync';
import { notify } from '../notify';
import { COLOR, SPACE, RADIUS, TYPE } from '../theme';
import { Icon, type IconName } from '../components/Icon';
import { getCurrentEmail } from '../permissions';

export default function DashboardScreen({
  onOpenMap, onCapture, onSwitchProject, onLogout, onResumeDraft, onOpenUploadedData,
}: {
  onOpenMap: () => void;
  onCapture: (kind: 'manhole' | 'building' | 'building_photo') => void;
  onSwitchProject: () => void;
  onLogout: () => void;
  onBioLockChanged?: (on: boolean) => void;
  onResumeDraft: (d: { buildingId: string; code: string | null }) => void;
  onOpenUploadedData?: () => void;
}) {
  const [projectId,setProjectId]=useState<string|null>(null); const [projectName,setProjectName]=useState('Project');
  const [online,setOnline]=useState(true); const [pending,setPending]=useState(0); const [syncing,setSyncing]=useState(false);
  const [counts,setCounts]=useState<Record<string,number>>({}); const [features,setFeatures]=useState<any[]>([]); const [activity,setActivity]=useState<any[]>([]); const [me,setMe]=useState('');

  const load=useCallback(async()=>{const pid=await kvGet('projectId');setProjectId(pid);setProjectName((await kvGet('projectName'))||'Project');setPending(await pendingCount());if(!pid)return;setCounts(await serverCacheCounts(pid));setFeatures(await listServerFeatures(pid));setMe(getCurrentEmail());try{const r=await authed(`/api/v1/projects/${pid}/field-data/activity?limit=12`);if(r.ok)setActivity((await r.json()).items??[]);}catch{}},[]);
  useEffect(()=>{void load();const unsub=NetInfo.addEventListener(s=>setOnline(!!s.isConnected));return unsub},[load]);
  useEffect(()=>{if(!projectId)return;pullChanges(projectId).then(load).catch(()=>{})},[projectId,load]);
  async function sync(){if(!projectId)return;setSyncing(true);try{await runSync(projectId);await pullChanges(projectId);await load();notify('Synced','Project field data refreshed.');}catch(e:any){notify('Sync',String(e?.message??e));}finally{setSyncing(false)}}
  const buildings=features.filter(f=>f._cache_kind==='buildings'); const surveyed=buildings.filter(f=>f.properties?.verification_state==='field_observed'||f.properties?.last_edited_by).length;
  const routeKm=features.filter(f=>f._cache_kind==='routes').reduce((n,f)=>n+Number(f.properties?.length_m||0),0)/1000;
  const roadsVerified=features.filter(f=>f._cache_kind==='streets'&&f.properties?.verification_state==='field_observed').length;
  const attention=features.filter(f=>['poor','damaged','impassable','inaccessible'].includes(String(f.properties?.condition||''))||f.properties?.verification_state==='needs_review').length;
  const today=new Date().toDateString(); const mineToday=activity.filter(a=>a.surveyor===me&&new Date(a.occurred_at).toDateString()===today);
  const myBuildings=mineToday.filter(a=>a.entity_type==='building').length; const myChambers=mineToday.filter(a=>a.entity_type==='manhole').length; const myRoutes=mineToday.filter(a=>a.entity_type==='survey_route').length;
  return <View style={s.root}><View style={s.header}><View><Text style={s.title}>{projectName}</Text><View style={s.status}><View style={[s.dot,{backgroundColor:online?COLOR.success500:COLOR.error}]}/><Text style={s.statusText}>{online?'Online':'Offline'} · {pending} pending</Text></View></View><TouchableOpacity style={s.sync} onPress={sync} disabled={syncing}>{syncing?<ActivityIndicator color="#fff"/>:<Icon name="synced" size={18} color="#fff"/>}</TouchableOpacity></View>
  <ScrollView contentContainerStyle={s.body}>
    <Text style={s.eyebrow}>FIELD PROGRESS · ALL SURVEYORS</Text><View style={s.card}><Metric icon="building" label="Buildings surveyed" value={`${surveyed.toLocaleString()} / ${buildings.length.toLocaleString()}`} /><Metric icon="manhole" label="Manholes / handholes" value={String(counts.manholes??0)} /><Metric icon="road" label="Roads verified" value={`${roadsVerified} / ${counts.streets??0}`} /><Metric icon="route" label="Routes walked" value={`${routeKm.toFixed(1)} km`} /><Metric icon="flagged" label="Needs attention" value={String(attention)} /></View>
    <Text style={s.eyebrow}>MY WORK TODAY</Text><View style={s.three}><Mini label="Buildings" value={myBuildings}/><Mini label="Chambers" value={myChambers}/><Mini label="Routes" value={myRoutes}/></View>
    <View style={s.sectionHead}><Text style={s.eyebrow}>RECENT ACTIVITY · PROJECT</Text><TouchableOpacity onPress={onOpenUploadedData}><Text style={s.link}>View data</Text></TouchableOpacity></View>
    <View style={s.card}>{activity.slice(0,8).map(a=><View key={a.id} style={s.activity}><View style={s.activityDot}/><View style={{flex:1}}><Text style={s.activityActor}>{a.surveyor||'Unknown surveyor'}</Text><Text style={s.activityText}>{a.change_kind==='captured'?'Captured':'Updated'} {String(a.entity_type).replace('_',' ')}</Text></View><Text style={s.activityTime}>{new Date(a.occurred_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</Text></View>)}{!activity.length&&<Text style={s.empty}>No recent project activity cached yet.</Text>}</View>
    <Text style={s.eyebrow}>PROJECT</Text><View style={s.actions}><TouchableOpacity style={s.action} onPress={onOpenMap}><Icon name="map" size={20} color={COLOR.primary700}/><Text style={s.actionText}>Open shared field map</Text></TouchableOpacity><TouchableOpacity style={s.action} onPress={onSwitchProject}><Icon name="switchProject" size={20} color={COLOR.primary700}/><Text style={s.actionText}>Switch project</Text></TouchableOpacity></View>
  </ScrollView></View>
}
function Metric({icon,label,value}:{icon:IconName;label:string;value:string}){return <View style={s.metric}><Icon name={icon} size={18} color={COLOR.primary700}/><Text style={s.metricLabel}>{label}</Text><Text style={s.metricValue}>{value}</Text></View>}
function Mini({label,value}:{label:string;value:number}){return <View style={s.mini}><Text style={s.miniValue}>{value}</Text><Text style={s.miniLabel}>{label}</Text></View>}
const s=StyleSheet.create({root:{flex:1,backgroundColor:COLOR.surface100},header:{backgroundColor:COLOR.primary900,paddingTop:54,paddingBottom:SPACE.md,paddingHorizontal:SPACE.md,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},title:{...TYPE.h2,fontSize:26,color:'#fff'},status:{flexDirection:'row',alignItems:'center',gap:6,marginTop:4},dot:{width:8,height:8,borderRadius:4},statusText:{...TYPE.small,color:'rgba(255,255,255,.8)'},sync:{width:44,height:44,borderRadius:RADIUS.full,backgroundColor:COLOR.primary700,alignItems:'center',justifyContent:'center'},body:{padding:SPACE.md,paddingBottom:SPACE.xl,gap:SPACE.sm},eyebrow:{...TYPE.mono,fontSize:11,letterSpacing:.5,color:COLOR.text500,fontWeight:'700',marginTop:4},card:{backgroundColor:COLOR.surface0,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.borderCard,padding:12},metric:{flexDirection:'row',alignItems:'center',gap:10,minHeight:39,borderBottomWidth:1,borderBottomColor:COLOR.surface100},metricLabel:{...TYPE.body,flex:1,color:COLOR.text900},metricValue:{...TYPE.mono,fontWeight:'700',color:COLOR.primary900},three:{flexDirection:'row',gap:8},mini:{flex:1,backgroundColor:COLOR.surface0,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.borderCard,padding:12,alignItems:'center'},miniValue:{...TYPE.h3,color:COLOR.primary900},miniLabel:{...TYPE.small,color:COLOR.text500},sectionHead:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},link:{...TYPE.small,color:COLOR.primary700,fontWeight:'700'},activity:{flexDirection:'row',gap:9,alignItems:'center',minHeight:48,borderBottomWidth:1,borderBottomColor:COLOR.surface100},activityDot:{width:8,height:8,borderRadius:4,backgroundColor:COLOR.success500},activityActor:{...TYPE.bodyBold,color:COLOR.text900,fontSize:13},activityText:{...TYPE.small,color:COLOR.text500},activityTime:{...TYPE.mono,fontSize:10,color:COLOR.text500},empty:{...TYPE.small,color:COLOR.text500,paddingVertical:12},actions:{gap:8},action:{backgroundColor:COLOR.surface0,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.borderCard,minHeight:50,flexDirection:'row',alignItems:'center',gap:10,paddingHorizontal:12},actionText:{...TYPE.bodyBold,color:COLOR.text900}});
