
import { useEffect,useRef,useState } from 'react'
export const SHOT_BASE='/astrid-shot-controls'
export type Slot=string
export type ShotSpec={id:Slot,prompt:string,seed:number,worker_reference:string,frames:number,actual:{width:number,height:number,fps:number,frame_count:number},trim:{id:string,asset_id:string,source_in_frame:number,duration_frames:number},graph:unknown,prompt_id:string}
export type Take={id:string,shot:Slot,state:string,seed:number,prompt:string,error?:string,output?:{frame_count?:number,fps?:number}}
type State={shots:ShotSpec[],takes:Take[]}
async function req<T>(endpoint:string,payload?:object):Promise<T>{
 const response=await fetch(SHOT_BASE+endpoint,payload?{method:'POST',headers:{'Content-Type':'application/json','X-Astrid-Control':'1'},body:JSON.stringify(payload)}:{cache:'no-store'})
 const result=await response.json();if(!response.ok)throw Error(result.error??response.statusText);return result as T
}
type Props={assetId?:string,sourceIn?:number,length?:number,dirty:boolean,onAudition?:(take:Take)=>void}
export default function ShotGeneration({assetId,sourceIn,length,dirty,onAudition}:Props){
 const [state,setState]=useState<State|null>(null),[draft,setDraft]=useState(''),[seed,setSeed]=useState<'same'|'new'>('same'),[status,S]=useState(''),[busy,B]=useState(false),[chosen,C]=useState(''),[frame,F]=useState(0),[playing,P]=useState(false)
 const orig=useRef<HTMLVideoElement>(null),alt=useRef<HTMLVideoElement>(null)
 const s=state?.shots.find(x=>x.trim.asset_id===assetId)
 const slot=s?.id
 const takes=state?.takes.filter(x=>x.shot===slot)??[]
 const ready=takes.filter(x=>x.state==='ready')
 const take=ready.find(x=>x.id===chosen)??ready[0]
 const start=sourceIn??s?.trim.source_in_frame??0, frames=length??s?.trim.duration_frames??0
 const fits=!!take&&take.output?.fps===24&&(take.output?.frame_count??0)>=start+frames
 const sync=(n:number)=>{F(n);for(const v of [orig.current,alt.current]){if(v&&v.readyState)v.currentTime=(start+n)/24}}
 function stop(){orig.current?.pause();alt.current?.pause();P(false)}
 useEffect(()=>{if(!assetId)return;let live=true;const refresh=()=>req<State>('/api/state').then(x=>{if(live)setState(x)}).catch(x=>{if(live)S(String(x))});void refresh();const timer=setInterval(()=>void refresh(),5000);return()=>{live=false;clearInterval(timer)}},[assetId])
 useEffect(()=>{if(s)setDraft(s.prompt); F(0); C(''); P(false)},[s?.id,s?.trim.asset_id]) 
 useEffect(()=>{F(0);P(false)},[take?.id])
 function timeUpdate(){const v=orig.current,a=alt.current;if(!v||!playing)return;const n=Math.max(0,Math.round(v.currentTime*24)-start);if(n>=frames){stop();sync(Math.max(0,frames-1));return}F(n);if(a&&a.readyState&&Math.abs(a.currentTime-v.currentTime)>.12)a.currentTime=v.currentTime}
 async function go(){if(playing){stop();return}if(frame>=frames-1)sync(0);try {await Promise.all([orig.current?.play(),fits?alt.current?.play():undefined]);P(true)}catch(e){stop();S(String(e))}}
 async function reroll(){if(!slot||!window.confirm('Queue one SD reroll on Harbinger? Your timeline stays unchanged.'))return; B(true);try{const r=await req<Take>('/api/reroll',{shot:slot,prompt:draft,seedMode:seed});S('Take '+r.state+' · seed '+r.seed);setState(await req<State>('/api/state'))}catch(e){S(String(e))}finally{B(false)}}
 if(!s)return <p role="status">{status||(!state?'Loading original generation receipt…':'No matching generation receipt is available for this media. You can still start a new generation.')}</p>
 return <div className="astrid-generation" style={{padding:10,overflow:'auto',maxHeight:'100%'}} onKeyDown={e=>e.stopPropagation()}>
 <h3>{s.id} · original generation</h3><p>Seed {s.seed} · {s.actual.width}×{s.actual.height} · {s.actual.fps} fps · source frames {start}–{start+frames} (out exclusive)</p>
 <details><summary>Starting reference and exact workflow</summary><img style={{width:'100%',maxWidth:220}} src={SHOT_BASE+'/media/reference/'+s.id} alt="Original generation reference"/><p>{s.worker_reference} · job {s.prompt_id}</p><pre style={{maxHeight:200,overflow:'auto'}}>{JSON.stringify(s.graph,null,2)}</pre></details>
 <label style={{display:'block'}}>Prompt<textarea style={{display:'block',width:'98%',minHeight:120}} value={draft} onChange={e=>setDraft(e.target.value)} maxLength={5000}/></label>
 <div className="film-actions"><button onClick={()=>setDraft(s.prompt)}>Reset prompt</button><select aria-label="Seed" value={seed} onChange={e=>setSeed(e.target.value as 'same'|'new')}><option value="same">Same seed</option><option value="new">New seed</option></select><button disabled={busy||!draft.trim()||takes.some(t=>['submitting','rendering','unresolved'].includes(t.state))} onClick={()=>void reroll()}>Reroll shot</button></div>
 <p role="status">{status}</p><p>{takes.length?takes.map(t=>t.state+' · '+t.seed+(t.error?' ('+t.error+')':'')).join(' | '):'No rerolls for this shot yet.'}</p>
 {ready.length>1?<select aria-label="Choose reroll" value={take?.id??''} onChange={e=>{C(e.target.value);stop()}}>{ready.map(t=><option key={t.id} value={t.id}>{t.id} · seed {t.seed}</option>)}</select>:null}
 <div style={{display:'grid',gridTemplateColumns:take?'1fr 1fr':'1fr',gap:8}}><div>Original<video key={s.id} ref={orig} style={{width:'100%'}} src={SHOT_BASE+'/media/original/'+s.id} muted playsInline preload="metadata" onLoadedMetadata={e=>{e.currentTarget.currentTime=start/24}} onTimeUpdate={timeUpdate}/></div>
 {take?<div>New take<video key={take.id} ref={alt} style={{width:'100%'}} src={SHOT_BASE+'/media/take/'+take.id} muted playsInline preload="metadata" controls={!fits} onLoadedMetadata={e=>{if(fits)e.currentTarget.currentTime=start/24}}/></div>:null}</div>
 <div className="film-actions"><button onClick={()=>void go()}>{playing?'Pause':'Play trim'+(fits?' side by side':'')}</button><input aria-label="Comparison frame" type="range" min={0} max={Math.max(0,frames-1)} value={frame} onChange={e=>{stop();sync(Number(e.target.value))}}/></div>
 {take?<><details><summary>Reroll prompt actually used</summary><p>{take.prompt}</p></details><div className="film-actions"><button disabled={!fits||!onAudition} onClick={()=>{stop();onAudition?.(take)}}>Audition in context</button></div><small>{!fits?'Take cannot preserve the current trim; preview source only.':dirty?'Audition remains non-destructive.':'Context preview includes neighbouring shots and existing mix.'}</small></>:null}
 </div>
}



