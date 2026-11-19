import {useRef,useState} from 'react'
import {api} from './api'
import {JobMetadata,type GenerationJob} from './GenerationFlow'
type Recipe={id:string;workflow_sha256:string}
type Preflight={ready:boolean; id:string; errors:{message:string}[]; warnings:({message:string}|string)[]}
export default function OwnedTake({job,onQueued,onHistory}:{job:GenerationJob;onQueued:()=>void;onHistory:()=>void}){
 const m=job.metadata
 const [prompt,setPrompt]=useState(m?.brief??''),[seedMode,setSeedMode]=useState<'same'|'new'>('same'),[receipt,setReceipt]=useState(''),[busy,setBusy]=useState(false)
 const lock=useRef(false)
 const request=useRef<{key:string,id:string,seed:number}|null>(null)
 const refs=Object.entries((m?.references??{}) as Record<string,{id?:string}>)
 const supported=!!m?.recipe_id&&typeof m.brief==='string'&&Number.isSafeInteger(m.seed)&&!m.continuation&&!m.planned_shot&&refs.every(([k,v])=>['first_frame','last_frame'].includes(k)&&typeof v?.id==='string'&&/^image\.[a-f0-9]{64}$/.test(v.id))
 const queue=async()=>{
  if(!m||!supported||!prompt.trim()||lock.current)return
  lock.current=true;setBusy(true);setReceipt('')
  try{
   const current=await api<{recipe?:Recipe;recipes?:Recipe[];worker_url:string}>('film/generation')
   const recipe=[...current.recipes??[],current.recipe].find(r=>r?.id===m.recipe_id)
   const original=(m.settings as Partial<Recipe>|undefined)?.workflow_sha256
   if(!recipe||!original||recipe.workflow_sha256!==original)throw Error('The original recipe cannot be matched to the installed recipe. Nothing was queued.')
   if(!current.worker_url)throw Error('No worker is configured. Nothing was queued.')
   const key=JSON.stringify([prompt.trim(),seedMode])
   if(request.current?.key!==key){
    let chosen=m.seed!
    if(seedMode==='new')do {chosen=crypto.getRandomValues(new Uint32Array(1))[0]&0x7fffffff}while(chosen===m.seed)
    request.current={key,id:crypto.randomUUID(),seed:chosen}
   }
   const r=request.current!
   const body={brief:prompt.trim(),seed:r.seed,recipe_id:recipe.id,worker_url:current.worker_url,...Object.fromEntries(refs.map(([k,v])=>[k+'_id',v.id]))}
   const check=await api<Preflight>('film/generation/preflight',body)
   if(!check.ready)throw Error(check.errors?.map(e=>e.message).join('; ')||'Worker check did not pass. Nothing was queued.')
   const notices=check.warnings?.map(w=>typeof w==='string'?w:w.message).join('\n')??''
   if(!window.confirm((notices?notices+'\n\n':'')+'Queue one separate picture + sound take? The timeline will not change.'))return
   await api<GenerationJob>('film/generation/jobs',{...body,label:job.label.slice(0,80)+' - alternate',request_id:r.id,preflight_id:check.id})
   request.current=null
   setReceipt('Queued separate take with seed '+r.seed+'. It appears in the Browser when finished (the Queue tab shows progress).')
   onQueued()
  }catch(e){setReceipt(e instanceof Error?e.message:String(e))}finally{lock.current=false;setBusy(false)}
 }
 return <div onKeyDown={e=>e.stopPropagation()}><JobMetadata job={job}/><p>Original prompt</p><blockquote style={{whiteSpace:'pre-wrap'}}>{m?.brief??'Not recorded'}</blockquote>{supported?<><label>Alternate prompt<textarea value={prompt} maxLength={4000} disabled={busy} onChange={e=>setPrompt(e.target.value)}/></label><label>Seed<select value={seedMode} disabled={busy} onChange={e=>setSeedMode(e.target.value as typeof seedMode)}><option value="same">Same seed</option><option value="new">New seed</option></select></label><button disabled={busy||!prompt.trim()} onClick={()=>void queue()}>{busy?'Checking…':'Check and reroll as separate take'}</button></>:<p>This receipt cannot be safely replayed here. Use its original shot-plan or continuation workflow if available.</p>}<p role="status">{receipt}</p><button onClick={onHistory}>Open job in the Queue</button></div>
}

