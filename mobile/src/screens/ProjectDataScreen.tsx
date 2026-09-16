import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { kvGet, listServerFeatures, serverCacheCounts } from '../db';
import { pullChanges } from '../sync';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH } from '../theme';
import { Icon, type IconName } from '../components/Icon';
import { notify } from '../notify';
import { getCurrentEmail } from '../permissions';

type Filter = 'all' | 'mine' | 'recent' | 'attention';
type Kind = 'buildings' | 'manholes' | 'streets' | 'routes' | 'building_photos';
type DataTarget = { kind?: Kind; filter?: Filter };
const KIND_LABEL: Record<string, { label: string; icon: IconName }> = {
  buildings: { label: 'Buildings', icon: 'building' },
  manholes: { label: 'Manholes / Handholes', icon: 'manhole' },
  streets: { label: 'Roads / Streets', icon: 'road' },
  routes: { label: 'Survey Routes', icon: 'route' },
  building_photos: { label: 'Photos', icon: 'photo' },
};

function prop(f:any,k:string){return f?.properties?.[k]}
function title(f:any){const k=f._cache_kind; if(k==='buildings')return prop(f,'code')||'Building'; if(k==='manholes')return prop(f,'code')||prop(f,'type')||'Chamber'; if(k==='streets')return prop(f,'name')||prop(f,'code')||'Road / Street'; if(k==='routes')return prop(f,'code')||String(prop(f,'type')||'Survey route').replace('_',' '); return 'Building photo';}
function subtitle(f:any){const k=f._cache_kind; if(k==='buildings')return [prop(f,'building_type'),prop(f,'address')].filter(Boolean).join(' · '); if(k==='manholes')return [prop(f,'type'),prop(f,'condition')].filter(Boolean).join(' · '); if(k==='streets')return [prop(f,'road_class'),prop(f,'surface'),prop(f,'verification_state')].filter(Boolean).join(' · '); if(k==='routes')return `${Math.round(Number(prop(f,'length_m')||0))} m · ${prop(f,'surveyed_by')||'unknown surveyor'}`; return prop(f,'surveyed_by')||'Field photo';}
function needsAttention(f:any){const c=String(prop(f,'condition')||''); return ['poor','damaged','impassable','inaccessible'].includes(c)||prop(f,'verification_state')==='needs_review';}

export default function ProjectDataScreen({
  initialTarget,
  onTargetConsumed,
}: {
  initialTarget?: DataTarget | null;
  onTargetConsumed?: () => void;
}) {
  const [projectId,setProjectId]=useState<string|null>(null); const [projectName,setProjectName]=useState('Project');
  const [features,setFeatures]=useState<any[]>([]); const [counts,setCounts]=useState<Record<string,number>>({});
  const [query,setQuery]=useState('');
  const [filter,setFilter]=useState<Filter>('all');
  const [kindFilter,setKindFilter]=useState<Kind|null>(null);
  const [email,setEmail]=useState('');
  const [syncing,setSyncing]=useState(false);

  const reload=useCallback(async()=>{const pid=await kvGet('projectId'); setProjectId(pid); setProjectName((await kvGet('projectName'))||'Project'); if(!pid)return; setFeatures(await listServerFeatures(pid)); setCounts(await serverCacheCounts(pid));},[]);
  useEffect(()=>{setEmail(getCurrentEmail()); void reload();},[reload]);

  useEffect(() => {
    if (!initialTarget) return;
    if (initialTarget.filter) setFilter(initialTarget.filter);
    setKindFilter(initialTarget.kind ?? null);
    onTargetConsumed?.();
  }, [initialTarget, onTargetConsumed]);
  async function refresh(){if(!projectId)return; setSyncing(true); try{const n=await pullChanges(projectId); await reload(); notify('Project data', n?`Refreshed ${n} changed record${n===1?'':'s'}.`:'Project data is up to date.');}catch(e:any){notify('Sync',String(e?.message??e));}finally{setSyncing(false)}}
  const visible=useMemo(()=>features.filter(f=>{const p=f.properties||{}; if(kindFilter&&f._cache_kind!==kindFilter)return false; if(filter==='mine'&&(!email||!([p.surveyed_by,p.last_edited_by,p.name_recorded_by].filter(Boolean).includes(email))))return false; if(filter==='recent'){const d=new Date(p.updated_at||p.created_at||0).getTime(); if(Date.now()-d>30*86400000)return false;} if(filter==='attention'&&!needsAttention(f))return false; const q=query.trim().toLowerCase(); if(q&&!`${title(f)} ${subtitle(f)} ${p.surveyed_by||''} ${p.last_edited_by||''}`.toLowerCase().includes(q))return false; return true;}),[features,kindFilter,filter,email,query]);

  return <View style={s.root}>
    <View style={s.header}><View><Text style={s.title}>Project Data</Text><Text style={s.sub}>{projectName}</Text></View><TouchableOpacity style={s.refresh} onPress={refresh} disabled={syncing}>{syncing?<ActivityIndicator color="#fff"/>:<Icon name="synced" size={18} color="#fff"/>}</TouchableOpacity></View>
    <View style={s.tabs}>{(['all','mine','recent','attention'] as Filter[]).map(v=><TouchableOpacity key={v} style={[s.tab,filter===v&&s.tabOn]} onPress={()=>setFilter(v)}><Text style={[s.tabText,filter===v&&s.tabTextOn]}>{v==='attention'?'Needs Attention':v[0].toUpperCase()+v.slice(1)}</Text></TouchableOpacity>)}</View>
    <View style={s.searchWrap}><Icon name="search" size={17} color={COLOR.text500}/><TextInput value={query} onChangeText={setQuery} style={s.search} placeholder="Search buildings, manholes, roads…" placeholderTextColor={COLOR.text500}/></View>
    <ScrollView contentContainerStyle={s.body}>
      <View style={s.summary}>
        {Object.entries(KIND_LABEL).map(([k,m]) => {
          const kind = k as Kind;
          const selected = kindFilter === kind;
          return (
            <TouchableOpacity
              key={k}
              style={[s.summaryRow, selected && s.summaryRowSelected]}
              activeOpacity={0.7}
              onPress={() => setKindFilter(selected ? null : kind)}
            >
              <Icon name={m.icon} size={18} color={COLOR.primary700}/>
              <Text style={s.summaryLabel}>{m.label}</Text>
              <Text style={s.summaryCount}>{counts[k] ?? 0}</Text>
              <Icon name="chevronRight" size={15} color={COLOR.text500}/>
            </TouchableOpacity>
          );
        })}
      </View>

      {kindFilter && (
        <TouchableOpacity
          style={s.clearKind}
          onPress={() => setKindFilter(null)}
        >
          <Text style={s.clearKindText}>
            Showing {KIND_LABEL[kindFilter].label} · Clear category
          </Text>
        </TouchableOpacity>
      )}
      <Text style={s.eyebrow}>{visible.length} RECORD{visible.length===1?'':'S'}</Text>
      {visible.map((f,i)=>{const meta=KIND_LABEL[f._cache_kind]??{label:f._cache_kind,icon:'data' as IconName};return <View key={`${f._cache_kind}:${prop(f,'id')}:${i}`} style={s.card}><View style={s.iconWell}><Icon name={meta.icon} size={19} color={COLOR.primary900}/></View><View style={{flex:1,minWidth:0}}><Text style={s.cardTitle} numberOfLines={1}>{title(f)}</Text><Text style={s.cardSub} numberOfLines={2}>{subtitle(f)||meta.label}</Text><Text style={s.cardMeta}>{prop(f,'last_edited_by')?`Edited by ${prop(f,'last_edited_by')}`:prop(f,'surveyed_by')?`Captured by ${prop(f,'surveyed_by')}`:'Baseline project data'}</Text></View>{needsAttention(f)&&<Icon name="flagged" size={18} color={COLOR.accent500}/>}</View>})}
      {!visible.length&&<Text style={s.empty}>No records match this view. Sync project data if this device has not been refreshed yet.</Text>}
    </ScrollView>
  </View>
}

const s=StyleSheet.create({root:{flex:1,backgroundColor:COLOR.surface100},header:{backgroundColor:COLOR.primary900,paddingTop:54,paddingBottom:SPACE.md,paddingHorizontal:SPACE.md,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},title:{...TYPE.h2,fontSize:26,color:'#fff'},sub:{...TYPE.small,color:'rgba(255,255,255,.78)',marginTop:2},refresh:{width:44,height:44,borderRadius:RADIUS.full,backgroundColor:COLOR.primary700,alignItems:'center',justifyContent:'center'},tabs:{flexDirection:'row',paddingHorizontal:SPACE.md,paddingTop:SPACE.sm,gap:4},tab:{flex:1,minHeight:38,borderRadius:RADIUS.full,alignItems:'center',justifyContent:'center',paddingHorizontal:4},tabOn:{backgroundColor:COLOR.primary900},tabText:{...TYPE.small,fontSize:10,color:COLOR.text500,textAlign:'center'},tabTextOn:{color:'#fff',fontWeight:'700'},searchWrap:{margin:SPACE.md,marginBottom:SPACE.sm,flexDirection:'row',alignItems:'center',gap:8,backgroundColor:COLOR.surface0,borderWidth:1,borderColor:COLOR.borderDefault,borderRadius:RADIUS.md,paddingHorizontal:12},search:{...TYPE.body,flex:1,minHeight:MIN_TOUCH,color:COLOR.text900},body:{padding:SPACE.md,paddingTop:SPACE.sm,paddingBottom:SPACE.xl,gap:SPACE.sm},summary:{backgroundColor:COLOR.surface0,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.borderCard,overflow:'hidden'},summaryRow:{flexDirection:'row',alignItems:'center',gap:10,minHeight:44,paddingHorizontal:12,borderBottomWidth:1,borderBottomColor:COLOR.surface100},summaryRowSelected:{backgroundColor:COLOR.neutralTint},clearKind:{alignSelf:'flex-start',paddingVertical:6,paddingHorizontal:2},clearKindText:{...TYPE.small,color:COLOR.primary700,fontWeight:'700'},summaryLabel:{...TYPE.body,flex:1,color:COLOR.text900},summaryCount:{...TYPE.mono,fontWeight:'700',color:COLOR.primary900},eyebrow:{...TYPE.mono,fontSize:11,color:COLOR.text500,marginTop:SPACE.sm},card:{flexDirection:'row',gap:10,alignItems:'center',backgroundColor:COLOR.surface0,borderRadius:RADIUS.md,borderWidth:1,borderColor:COLOR.borderCard,padding:12},iconWell:{width:38,height:38,borderRadius:RADIUS.md,backgroundColor:COLOR.neutralTint,alignItems:'center',justifyContent:'center'},cardTitle:{...TYPE.bodyBold,color:COLOR.text900},cardSub:{...TYPE.small,color:COLOR.text500,marginTop:1},cardMeta:{...TYPE.small,fontSize:10,color:COLOR.primary700,marginTop:3},empty:{...TYPE.small,color:COLOR.text500,textAlign:'center',padding:24}});
