import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { useGenerationDestination } from './GenerationFlow'
import type { GenerationJob, GenerationPlacement, GenerationTarget } from './GenerationFlow'

type Recipe = { id: string; name: string; model: string; duration_seconds: number; bpm: number; key_scale: string; time_signature: string; steps: number; default_seed: number; instrumental: boolean; duration_options?:number[]; duration_tested?:boolean; supports_lyrics?:boolean; max_lyrics_chars?:number; max_structure_chars?:number; max_brief_chars?:number }
type Job = GenerationJob
type State = { recipe: Recipe | null; recipes?:Recipe[]; worker_url: string; jobs: Job[] }
type Check = { id: string; ready: boolean; expires_at: string; errors: {code: string; message: string}[]; warnings: ({message: string} | string)[] }
function readDraft(): {worker?: string; brief?: string; label?: string; seed?: string; recipeId?:string; duration?:number; instrumental?:boolean; lyrics?:string; structure?:string} { try { return JSON.parse(localStorage.getItem('llr.film.music.draft.v1')??'{}') } catch { return {} } }
const message = (error: unknown) => error instanceof Error ? error.message : String(error)

export default function MusicGeneration({ target, timelineDirty, frame, selectedJob, onJobsChanged, onOpenHistory }: { onImported: (assetId: string) => Promise<void>; target:GenerationTarget|null; timelineDirty:boolean;frame:number;placements:GenerationPlacement[];selectedJob:string;onPlaced:()=>Promise<void>;onReviewVideo:(id:string)=>void;onReviewAudio:(id:string)=>void;onJobsChanged:()=>void;onOpenHistory?:()=>void }) {
  const destinationFlow=useGenerationDestination('A2',target,frame)
  useEffect(()=>{if(selectedJob)document.getElementById(`generation-job-${selectedJob}`)?.scrollIntoView({block:'nearest'})},[selectedJob])
  const [state, setState] = useState<State | null>(null)
  const [worker, setWorker] = useState(()=>readDraft().worker??'')
  const [brief, setBrief] = useState(()=>readDraft().brief??'')
  const [label, setLabel] = useState(()=>readDraft().label??'')
  const [seed, setSeed] = useState(()=>readDraft().seed??'20261112')
  const [recipeId,setRecipeId]=useState(()=>readDraft().recipeId??'')
  const [duration,setDuration]=useState(()=>readDraft().duration??180)
  const [instrumental,setInstrumental]=useState(()=>readDraft().instrumental??true)
  const [lyrics,setLyrics]=useState(()=>readDraft().lyrics??'')
  const [structure,setStructure]=useState(()=>readDraft().structure??'')
  const [check, setCheck] = useState<Check | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const lock = useRef(false)
  const request = useRef<{ fingerprint: string; id: string } | null>(null)
  useEffect(() => { try { localStorage.setItem('llr.film.music.draft.v1',JSON.stringify({worker,brief,label,seed,recipeId,duration,instrumental,lyrics,structure})) } catch { /* optional local draft */ } }, [worker,brief,label,seed,recipeId,duration,instrumental,lyrics,structure])
  useEffect(() => { if(!check)return; const timer=window.setTimeout(()=>setCheck(null),Math.max(0,Date.parse(check.expires_at)-Date.now())); return ()=>clearTimeout(timer) }, [check])
  const recipe = state?.recipes?.find(r=>r.id===recipeId)??state?.recipe
  const fullSong=!!recipe?.duration_options?.length
  const selectedDuration=fullSong&&recipe?.duration_options?.includes(duration)?duration:recipe?.duration_seconds
  const songSettings=fullSong?{duration_seconds:selectedDuration,instrumental,lyrics:instrumental?'':lyrics,structure}:{}
  const fingerprint = JSON.stringify([recipe?.id, worker, brief, seed, label,destinationFlow.destination,songSettings])
  const current = useRef(fingerprint)
  current.current = fingerprint
  useEffect(() => { setCheck(null) }, [fingerprint])
  async function refresh(initial = false) {
    const next = await api<State>('film/music'); setState(next)
    if(initial) { setWorker(value=>value||next.worker_url) }
  }
  useEffect(() => { void refresh(true).catch(e=>setError(message(e))) }, [])
  useEffect(() => {
    if(!state?.jobs.some(j=>['pending','submitting','queued','running'].includes(j.status))) return
    const timer = window.setInterval(()=>{void refresh().catch(e=>setError(message(e)))}, 2500)
    return ()=>clearInterval(timer)
  }, [state?.jobs])
  async function action(work:()=>Promise<void>) {
    if(lock.current) return
    lock.current=true;setBusy(true);setError('')
    try { await work() } catch(e) { setError(message(e)) } finally {lock.current=false;setBusy(false)}
  }
  const body = {recipe_id:recipe?.id,worker_url:worker,brief,seed:Number(seed),...songSettings}
  const valid = (!fullSong||instrumental||!!lyrics.trim()) && brief.length<=(recipe?.max_brief_chars??4000) && lyrics.length<=(recipe?.max_lyrics_chars??20000) && structure.length<=(recipe?.max_structure_chars??4000) && destinationFlow.valid && (!destinationFlow.destination||!timelineDirty) && !!recipe && !!brief.trim() && !!worker.trim() && !!seed.trim() && Number.isSafeInteger(Number(seed)) && Number(seed)>=0 && Number(seed)<=2147483647
  const ready = check?.ready && Date.parse(check.expires_at)>Date.now()
  return <details open className="film-generation film-bin">
    <summary>Generate a music cue · ACE-Step</summary>
    <p>Check the worker before explicitly generating. Finished cues import into the Browser by themselves.</p>
    {state?.recipes?.length?<label>Music recipe<select aria-label="Music recipe" value={recipe?.id??''} disabled={busy} onChange={e=>setRecipeId(e.target.value)}>{state.recipes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>:null}
    {recipe?<><h2>{recipe.name}</h2><p>{recipe.model} · {selectedDuration}s requested · {recipe.steps} steps · {recipe.bpm} BPM · {recipe.key_scale}. No language-model planning.</p></>:<p>No ACE-Step recipe is registered.</p>}
    {fullSong?<fieldset><legend>Whole-song settings</legend><p>Long-duration and vocal controls are supported by the adapter but have not yet been verified with a live full-song render. Requested duration is a target; the decoded result is recorded separately.</p><label>Requested song duration<select aria-label="Requested song duration" disabled={busy} value={selectedDuration} onChange={e=>setDuration(Number(e.target.value))}>{recipe?.duration_options?.map(seconds=><option key={seconds} value={seconds}>{seconds}s ({seconds/60} min)</option>)}</select></label><label><input type="checkbox" checked={instrumental} disabled={busy} onChange={e=>setInstrumental(e.target.checked)}/>Instrumental (no lyrics sent)</label>{!instrumental?<label>Full lyrics / section tags<textarea aria-label="Full lyrics" rows={10} value={lyrics} maxLength={recipe?.max_lyrics_chars??20000} disabled={busy} onChange={e=>setLyrics(e.target.value)} placeholder="Your full lyrics, including any [Verse] / [Chorus] tags"/></label>:null}<label>Song structure<textarea aria-label="Song structure" rows={4} value={structure} maxLength={recipe?.max_structure_chars??4000} disabled={busy} onChange={e=>setStructure(e.target.value)} placeholder="Optional arrangement instructions; appended to the musical brief unchanged"/></label><p>Submission may remain in progress while ACE-Step generates synchronously. No task identifier or completion estimate is invented before the service replies.</p></fieldset>:<p>Proven 30-second instrumental recipe. Lyrics and structure settings are not sent on this route.</p>}
    <label>Cue label<input value={label} disabled={busy} onChange={e=>setLabel(e.target.value)} placeholder="Name this take" maxLength={100}/></label>
    <label>Music cue brief<textarea value={brief} disabled={busy} onChange={e=>setBrief(e.target.value)} placeholder="Describe the mood, instruments and musical development. Describe vocals when enabled." rows={4} maxLength={recipe?.max_brief_chars??4000}/></label>
    <div className="film-imports"><label>ACE-Step worker URL<input value={worker} disabled={busy} onChange={e=>setWorker(e.target.value)}/></label><label>Music seed<input type="number" min={0} max={2147483647} step={1} value={seed} disabled={busy} onChange={e=>setSeed(e.target.value)}/></label></div>
    {destinationFlow.controls}{timelineDirty&&destinationFlow.destination?<p>Save or discard the timeline draft before requesting a clip for this sequence.</p>:null}
    <div className="film-actions"><button disabled={busy} onClick={()=>void action(async()=>{await refresh();onJobsChanged()})}>Refresh music recipe & jobs</button><button disabled={busy||!valid} onClick={()=>void action(async()=>{const key=current.current;const next=await api<Check>('film/music/preflight',body);if(key===current.current)setCheck(next);setNotice('Worker check finished. No generation was submitted.')})}>Check music worker & recipe</button><button className="ed-primary" disabled={busy||!valid||!ready} onClick={()=>void action(async()=>{if(!check||Date.parse(check.expires_at)<=Date.now())throw new Error('Worker check expired. Check again before generating.');if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()};await api<Job>('film/music/jobs',{...body,label:label.trim()||'ACE-Step music cue',preflight_id:check.id,request_id:request.current.id,...(destinationFlow.destination?{destination:destinationFlow.destination}:{})});request.current=null;setCheck(null);onJobsChanged();setNotice('Generation requested. Follow it in the Queue tab; it appears in the Browser when finished.');await refresh()})}>Generate music cue</button></div>
    {check?<div role="status"><p>{ready?'Worker check passed. Generate is available for these exact settings.':'Not ready to generate. Check again after resolving the issues below.'}</p>{check.errors.map((e,i)=><p key={i}>{e.code}: {e.message}</p>)}{check.warnings.map((w,i)=><p key={i}>{typeof w==='string'?w:w.message}</p>)}</div>:null}
    <p className="generation-history-link">Requested cues, their progress and what to do next are in the <button onClick={onOpenHistory}>History</button> tab.</p>
    {notice?<p role="status">{notice}</p>:null}{error?<p role="alert">{error}</p>:null}
  </details>
}





