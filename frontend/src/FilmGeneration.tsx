import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import FilmReferences from './FilmReferences'
import Thumb from './Thumb'
import { JobStage } from './GenerationFlow'
import { importTakeJob } from './FilmHistory'
import { LIMIT_KEY, framesFor, framesForInterval, lengthNote, limitOf, rulesOf } from './clipLength'
import type { PlannedSetup } from './FilmShotPlan'
import type { ReferenceImage, ReferenceSource } from './FilmReferences'
import type { TakeSpot } from './filmEdits'
import type { GenerationJob, GenerationPlacement, GenerationTarget } from './GenerationFlow'

export type ContinuationDraft={id:string;first_frame_id:string;image:ReferenceImage;destination:{sequence_id:string;expected_revision:number;track:'V1';insert_index:number};source:{shot_id:string;sequence_revision:number;source_in_frame:number;duration_frames:number;last_used_source_frame:number;rendered_frame:number;sequence_manifest_hash:string};boundary_policy:{drop_generated_first_frames:number;audio_source_in_frame:number;guarantee:string}}

type Recipe = { id: string; name: string; width: number; height: number; frames: number; fps: number; steps: number; default_seed: number; workflow_sha256: string; reference_supported?:boolean; last_frame_tested?:boolean; min_frames?:number; max_frames?:number; frame_step?:number; proven_frames?:number[] }
type Job = GenerationJob
type State = { recipe: Recipe | null; recipes?:Recipe[]; worker_url: string; jobs: Job[] }
type Check = { id: string; ready: boolean; expires_at: string; errors: {code: string; message: string}[]; warnings: ({message: string} | string)[] }
/** What the generation guide reads from this form, and the setters it drives. The guide never keeps its own copy of the brief. */
export type GenWhere = 'library'|TakeSpot['kind']
export type GenSnapshot = { brief:string; label:string; where:GenWhere; locked:string|null; valid:boolean; busy:boolean; awaitingWarningConfirm:boolean; notice:string; error:string; checkLines:string[]; blockers:string[]; selectedClipLabel:string|null; showsWhere:boolean; setup:GenSetup|null }
/** A continuation or shot-plan setup fixes where the take goes; `stale` says why it can no longer be generated as prepared. */
export type GenSetup = { kind:'continuation'|'plan'; where:string; stale:string|null; sequenceId:string; shotId?:string }
export type GenControl = { setBrief:(v:string)=>void; setLabel:(v:string)=>void; setWhere:(v:GenWhere)=>void; generate:()=>void; clearSetup:()=>void }
function readDraft():{worker?: string; brief?: string; label?: string; seed?: string; length?: string;first?:string;last?:string;from?:StartFrom;continuation?:ContinuationDraft|null;planned?:PlannedSetup|null} { try { return JSON.parse(localStorage.getItem('llr.film.generation.draft.v1')??'{}') } catch { return {} } }
const message = (error: unknown) => error instanceof Error ? error.message : String(error)
/** What a new take starts from. Text only never sends the reference slots (they are kept, so switching back restores them). */
type StartFrom = 'text'|'reference'

/** ---- Recent takes: an audition strip, not a second job manager (finished takes import themselves into the Browser; the Queue tab tracks jobs). */
type TakeJob = GenerationJob & { prompt?: string; references?: Record<string, { media_url?: string; label?: string } | null | undefined> }
type TakeKind = 'text'|'reference'|'continuation'|'plan'
const KIND_LABEL: Record<TakeKind,string> = { text:'Text only', reference:'From reference', continuation:'Continues a shot', plan:'Shot plan' }
const ACTIVE = ['pending','submitting','queued','running']
function takeKind(j: TakeJob): TakeKind {
  const m = j.metadata as Record<string, unknown> | undefined
  if (m?.continuation) return 'continuation'
  if (m?.planned_shot) return 'plan'
  return takeRefs(j).length ? 'reference' : 'text'
}
function takeRefs(j: TakeJob): { role: string; url: string; label: string }[] {
  const out: { role: string; url: string; label: string }[] = []
  for (const [key, role] of [['first_frame','First frame'],['last_frame','Last frame']] as const) { const r = j.references?.[key]; if (r?.media_url) out.push({ role, url: r.media_url, label: r.label ?? role }) }
  const imgs = (j.metadata as { reference_images?: { image_id?: string; role?: string }[] } | undefined)?.reference_images
  if (Array.isArray(imgs)) for (const r of imgs) if (r?.image_id) out.push({ role: r.role ?? 'Reference', url: `/api/film/images/${r.image_id}/media`, label: r.role ?? 'Reference' })
  return out
}
const briefOf = (j: TakeJob) => (j.metadata?.brief ?? j.prompt ?? '').trim()

export default function FilmGeneration({ target, timelineDirty, frame, selectedJob, onJobsChanged, referenceSource, preparedContinuation, preparedPlan, onGuide, onOpenHistory, selectedClip=null, onRequested, control, onSnapshot, onSubmitted, onReviewVideo, mediaFor, assetStatus, onAudition, auditionBlocked, onLibraryChanged, epoch, active=true }: { control?:{current:GenControl|null}; onSnapshot?:(s:GenSnapshot)=>void; onSubmitted?:(jobId:string)=>void; onImported: (assetId: string) => Promise<void>; target:GenerationTarget|null; timelineDirty:boolean;frame:number;placements:GenerationPlacement[];selectedJob:string;onPlaced:()=>Promise<void>;onReviewVideo:(id:string)=>void;onReviewAudio:(id:string)=>void;onJobsChanged:()=>void;referenceSource:ReferenceSource;preparedContinuation:ContinuationDraft|null;preparedPlan:PlannedSetup|null;onOpenPlan:()=>void;onGuide?:(jobId:string|null)=>void;onOpenHistory?:(jobId?:string)=>void;selectedClip?:{id:string;label:string}|null;onRequested?:(jobId:string,spot:TakeSpot|null)=>void
  /** Library media for an imported take's picture (it carries its production sound). */ mediaFor?:(videoAssetId:string)=>string|undefined
  /** Kept for callers; review status no longer matters (2026-11-19). */ assetStatus?:(videoAssetId:string)=>string|undefined
  /** Play the take between its neighbours (the editor's Audition in context). */ onAudition?:(job:GenerationJob)=>void
  /** Why Audition in context is unavailable (e.g. no sequence open), or null. */ auditionBlocked?:string|null
  /** Reload the library after Import to audition, so the new take's media resolves. */ onLibraryChanged?:()=>Promise<unknown>
  /** Bumped by the editor when jobs change elsewhere (History import, the guide), so Recent takes reloads. */ epoch?:number
  /** False while the Generate tab is hidden: the inline player pauses. */ active?:boolean }) {
  // Where the take should go (Boden 2026-11-17). Picture + sound takes are requested library-only; the spot is remembered in the editor and the take goes in with Insert (or a drag) once it is in the Browser.
  const [where,setWhere]=useState<'library'|TakeSpot['kind']>(()=>{try{const v=localStorage.getItem('llr.film.generation.where.v1');return v==='library'||v==='before'||v==='after'||v==='playhead'||v==='end'?v:'playhead'}catch{return 'playhead'}})
  useEffect(()=>{try{localStorage.setItem('llr.film.generation.where.v1',where)}catch{/* optional preference */}},[where])
  const needsClip=where==='before'||where==='after'
  const spot:TakeSpot|null=where==='library'||!target?null:{sequence_id:target.id,kind:where,...(needsClip&&selectedClip?{clipId:selectedClip.id,clipLabel:selectedClip.label}:{}),...(where==='playhead'?{frame}:{})}
  useEffect(()=>{if(selectedJob)document.getElementById(`generation-job-${selectedJob}`)?.scrollIntoView({block:'nearest'})},[selectedJob])
  const [state, setState] = useState<State | null>(null)
  const [worker, setWorker] = useState(()=>readDraft().worker??'')
  const [brief, setBrief] = useState(()=>readDraft().brief??'')
  const [label, setLabel] = useState(()=>readDraft().label??'')
  const [seed, setSeed] = useState(()=>readDraft().seed??'2026111301')
  /** Desired clip length in seconds (2026-11-19); snapped to legal frames and capped by the creator's longest-clip limit. */
  const [lengthSec, setLengthSec] = useState(()=>readDraft().length??'')
  const [limitStored, setLimitStored] = useState<number|null>(()=>{try{const v=Number(localStorage.getItem(LIMIT_KEY));return v>0?v:null}catch{return null}})
  useEffect(()=>{try{if(limitStored===null)localStorage.removeItem(LIMIT_KEY);else localStorage.setItem(LIMIT_KEY,String(limitStored))}catch{/* optional preference */}},[limitStored])
  const [first,setFirst]=useState(()=>readDraft().first??'')
  const [last,setLast]=useState(()=>readDraft().last??'')
  const [startFrom,setStartFrom]=useState<StartFrom>(()=>{const d=readDraft();return d.from==='text'||d.from==='reference'?d.from:d.first||d.last?'reference':'text'})
  const [planned,setPlanned]=useState<PlannedSetup|null>(()=>readDraft().planned??null)
  useEffect(()=>{if(preparedPlan){setPlanned(preparedPlan);setContinuation(null);setFirst(preparedPlan.first_frame_id??'');setLast(preparedPlan.last_frame_id??'');setBrief(preparedPlan.brief);setLabel(preparedPlan.label)}},[preparedPlan])
  const [continuation,setContinuation]=useState<ContinuationDraft|null>(()=>readDraft().continuation??null)
  // Preparing the same shot again (e.g. after the sequence was saved) keeps the brief and label you already wrote.
  useEffect(()=>{if(preparedContinuation){const same=continuation?.source.shot_id===preparedContinuation.source.shot_id;setPlanned(null);setContinuation(preparedContinuation);setFirst(preparedContinuation.first_frame_id);setLast('');if(!same||!label.trim())setLabel('Continuation take');if(!same||!brief.trim())setBrief('Continue naturally from the supplied final frame. Preserve the subject, lighting and camera continuity. Describe the next action and sound here.')}},[preparedContinuation?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const [check, setCheck] = useState<Check | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [lastRequested,setLastRequested]=useState<string|null>(null)
  const lock = useRef(false)
  const request = useRef<{ fingerprint: string; id: string } | null>(null)
  useEffect(() => { try { localStorage.setItem('llr.film.generation.draft.v1',JSON.stringify({worker,brief,label,seed,length:lengthSec,first,last,from:startFrom,continuation,planned})) } catch { /* optional local draft */ } }, [worker,brief,label,seed,lengthSec,first,last,startFrom,continuation,planned])
  useEffect(() => { if(!check)return; const timer=window.setTimeout(()=>setCheck(null),Math.max(0,Date.parse(check.expires_at)-Date.now())); return ()=>clearTimeout(timer) }, [check])
  const recipe = planned?.recipe_id?(state?.recipes??[]).find(r=>r.id===planned.recipe_id):state?.recipe
  const referenceImages=planned?.reference_images??[]
  const rules=recipe?rulesOf(recipe):null, lengthLimit=rules?limitOf(rules,limitStored):0
  const plannedInterval=planned?planned.end_frame-planned.start_frame:0
  // A shot-plan take is made just long enough to cover its interval; otherwise the creator's chosen length.
  const lengthFrames=!rules?0:planned?framesForInterval(plannedInterval,rules,lengthLimit):framesFor(lengthSec.trim()===''?rules.fallback/rules.fps:Number(lengthSec),rules,lengthLimit)
  const lengthTooShortForPlan=!!planned&&!!rules&&lengthFrames===null
  const destination=planned?null:continuation?.destination??null
  const continuationStale=!!continuation&&(target?.id!==continuation.destination.sequence_id||target.revision!==continuation.destination.expected_revision)
  // The slots only count when the take starts from references (or a continuation / shot plan fixed them).
  const usesRefs=!!continuation||!!planned||startFrom==='reference'
  const sentFirst=usesRefs?first:'', sentLast=usesRefs?last:''
  /** Request idempotency covers everything sent; the worker check only covers what the server binds it to (not label or destination). */
  const fingerprint = JSON.stringify([recipe?.id, worker, brief, seed, lengthFrames, label,sentFirst,sentLast,referenceImages,continuation?.id,planned,destination])
  const checkKey = JSON.stringify([recipe?.id, worker, brief, seed, lengthFrames,sentFirst,sentLast,referenceImages,continuation?.id,planned])
  const current = useRef(checkKey)
  current.current = checkKey
  useEffect(() => { setCheck(null) }, [checkKey])
  async function refresh(initial = false) {
    const next = await api<State>('film/generation'); setState(next)
    if(initial) { setWorker(value=>value||next.worker_url) }
  }
  useEffect(() => { void refresh(true).catch(e=>setError(message(e))) }, [])
  // Imports done in the Queue or the guide bump the editor's epoch; our own refresh never bumps it, so this cannot loop.
  useEffect(() => { if(epoch) void refresh().catch(()=>{/* the next poll or action shows errors */}) }, [epoch]) // eslint-disable-line react-hooks/exhaustive-deps
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
  const body = {recipe_id:recipe?.id,worker_url:worker,brief,seed:Number(seed),...(rules?.adjustable&&lengthFrames?{length_frames:lengthFrames}:{}),first_frame_id:referenceImages.length?null:recipe?.reference_supported?sentFirst||null:null,last_frame_id:referenceImages.length?null:recipe?.reference_supported?sentLast||null:null,...(referenceImages.length?{reference_images:referenceImages}:{}),continuation_id:continuation?.id??null,...(planned?{planned_shot_id:planned.id,planned_revision:planned.revision}:{})}
  const valid = (!planned||!timelineDirty&&!lengthTooShortForPlan) && (planned?target?.id===planned.sequence_id:continuation?!continuationStale:!needsClip||!!selectedClip) && (!destination||!timelineDirty) && !!recipe && !!brief.trim() && !!worker.trim() && !!seed.trim() && Number.isSafeInteger(Number(seed)) && Number(seed)>=0 && Number(seed)<=2147483647
  const ready = check?.ready && Date.parse(check.expires_at)>Date.now()
  const [acceptedWarnings,setAcceptedWarnings]=useState('')
  useEffect(()=>{setAcceptedWarnings('')},[checkKey])
  const awaitingWarningConfirm=!!check&&acceptedWarnings==='pending:'+check.id
  /** A2: Generate runs the worker check itself and submits only if it passes. Nothing reaches the worker without this click. */
  function generate(){const confirmedNow=awaitingWarningConfirm?check?.id:undefined/* this click accepts the warnings shown for this check */;if(confirmedNow)setAcceptedWarnings(confirmedNow);void action(async()=>{
    const key=current.current
    let c=check
    if(!c||!c.ready||Date.parse(c.expires_at)<=Date.now()){c=await api<Check>('film/generation/preflight',body);if(key!==current.current)throw new Error('Settings changed during the worker check. Click Generate again.');setCheck(c)}
    if(!c.ready){setNotice('The worker check did not pass, so nothing was submitted. See the issues below.');return}
    // A passing check can still carry warnings (e.g. untested last-frame conditioning): show them and ask for a second click.
    if(c.warnings.length&&acceptedWarnings!==c.id&&confirmedNow!==c.id){setCheck(c);setAcceptedWarnings('pending:'+c.id);setNotice('The worker check passed with warnings (below). Nothing was submitted. Click Generate again to submit anyway.');return}
    if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()}
    const job=await api<Job>('film/generation/jobs',{...body,label:label.trim()||'H3 joint AV take',preflight_id:c.id,request_id:request.current.id,...(destination?{destination}:{})})
    if(!continuation&&!planned)onRequested?.(job.id,spot)
    onSubmitted?.(job.id)
    setLastRequested(job.id)
    request.current=null;setCheck(null);setAcceptedWarnings('');onJobsChanged();setNotice('Generation requested. It appears under Recent takes below and plays there once it is imported.');await refresh()
  })}
  // Why Generate is unavailable, in words (mirrors `valid`), for the guide.
  const blockers:string[]=[]
  if(!recipe)blockers.push('The recipe is unavailable (Settings · Refresh recipe & jobs).')
  if(!brief.trim())blockers.push('Write the shot brief.')
  if(!worker.trim())blockers.push('Set the H3 worker URL (Settings).')
  if(!seed.trim()||!Number.isSafeInteger(Number(seed))||Number(seed)<0||Number(seed)>2147483647)blockers.push('The seed must be a whole number from 0 to 2147483647 (Settings).')
  if(planned){if(timelineDirty)blockers.push('Save or discard the timeline edits first.');if(target?.id!==planned.sequence_id)blockers.push('Open the planned sequence first.');if(lengthTooShortForPlan)blockers.push(`The planned interval (${(plannedInterval/24).toFixed(2)} s) is longer than the longest clip allowed (${(lengthLimit/24).toFixed(2)} s). Shorten the interval, or raise the limit in Settings.`)}
  else if(continuation){if(continuationStale)blockers.push('The continuation is out of date; prepare it again.')}
  else if(needsClip&&!selectedClip)blockers.push('Click a clip on V1 to place it before or after (or choose another spot).')
  if(destination&&timelineDirty&&!planned)blockers.push('Save or discard the timeline edits first.')
  if(!valid&&!blockers.length)blockers.push('Generate is not available with these settings.')
  if(control)control.current={setBrief,setLabel,setWhere,generate,clearSetup:()=>{setContinuation(null);setPlanned(null);setFirst('');setLast('')}}
  const setup:GenSetup|null=continuation?{kind:'continuation',sequenceId:continuation.destination.sequence_id,shotId:continuation.source.shot_id,
      where:`Right after the shot it continues (cut ${continuation.destination.insert_index}), starting from that shot’s last frame.`,
      stale:!continuationStale?null:target?.id!==continuation.destination.sequence_id?'This continuation was prepared in another sequence. Open that sequence, or drop it.':'The sequence was changed and saved after this continuation was prepared, so it no longer lines up.'}
    :planned?{kind:'plan',sequenceId:planned.sequence_id,where:`The planned interval “${planned.label}” (frames ${planned.start_frame}–${planned.end_frame}).`,stale:target?.id!==planned.sequence_id?'Open the planned sequence first.':null}:null
  const checkLines=check&&(!ready||check.warnings.length)?[...check.errors.map(e=>`${e.code}: ${e.message}`),...check.warnings.map(w=>typeof w==='string'?w:w.message)]:[]
  const snapshot:GenSnapshot={brief,label,where,locked:planned?'The brief comes from the saved shot plan; edit it in Shot plan.':null,valid,busy,awaitingWarningConfirm,notice,error,checkLines,blockers:valid?[]:blockers,selectedClipLabel:selectedClip?.label??null,showsWhere:!continuation&&!planned,setup}
  const snapKey=JSON.stringify(snapshot)
  useEffect(()=>{onSnapshot?.(snapshot)},[snapKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const fromRefs=!continuation&&!planned&&startFrom==='reference'&&!!recipe?.reference_supported
  const refCount=(sentFirst?1:0)+(sentLast?1:0)
  const startSummary=planned?'Shot plan':continuation?'Continues a shot':refCount?(sentFirst&&sentLast?'First + last frame':sentFirst?'First frame':'Last frame'):'Text only'
  return <div className="film-generation film-bin gen-tab">
    <div className="gen-head"><h3>New take <small>H3 picture + sound{recipe&&lengthFrames?` · ${(lengthFrames/recipe.fps).toFixed(2)} s · ${recipe.width}×${recipe.height}`:''}</small></h3>{onGuide?<p className="generation-guide-link"><button onClick={()=>onGuide(null)}>Guide me through generating a take</button></p>:null}</div>
    {recipe?null:<p role="alert">The requested recipe is unavailable. Refresh recipes or prepare the saved shot again; generation is blocked rather than using a different recipe.</p>}
    <label>Shot brief<textarea value={brief} disabled={busy||!!planned} onChange={e=>setBrief(e.target.value)} placeholder="What happens in the shot, and what we hear. With reference frames, say how they should guide it." rows={4}/></label>
    {rules&&recipe?<div className="gen-length"><label>Clip length<input type="range" aria-label="Clip length" min={rules.min} max={Math.max(rules.min,lengthLimit)} step={rules.step} value={lengthFrames??lengthLimit} disabled={busy||!!planned||!rules.adjustable} onChange={e=>setLengthSec(String(Number(e.target.value)/rules.fps))}/><input type="number" aria-label="Clip length in seconds" min={rules.min/rules.fps} max={lengthLimit/rules.fps} step={rules.step/rules.fps} value={lengthSec.trim()===''||planned?Number(((lengthFrames??0)/rules.fps).toFixed(2)):lengthSec} disabled={busy||!!planned||!rules.adjustable} onChange={e=>setLengthSec(e.target.value)} onBlur={()=>{if(lengthFrames)setLengthSec(String(Number((lengthFrames/rules.fps).toFixed(4))))}}/><span>s</span></label>
      <small className="gen-length-note">{!rules.adjustable?'This worker setup makes a fixed length.':planned?(lengthFrames?`Set by the shot-plan interval: ${lengthFrames} frames.`:'The planned interval is longer than the longest clip allowed.'):`${lengthFrames} frames · longest allowed ${(lengthLimit/rules.fps).toFixed(2)} s (Settings). Shorter clips stay more coherent.`}{lengthFrames&&rules.adjustable?(n=>n?' '+n:'')(lengthNote(lengthFrames,rules)):''}</small></div>:null}
    <label>Take label<input value={label} disabled={busy} onChange={e=>setLabel(e.target.value)} placeholder="Name this take" maxLength={100}/></label>
    {!continuation&&!planned?<><div className="gen-start" role="radiogroup" aria-label="Starting point">
      <button type="button" role="radio" aria-checked={!fromRefs} disabled={busy} onClick={()=>setStartFrom('text')}><strong>Text only</strong><small>The brief alone</small></button>
      <button type="button" role="radio" aria-checked={fromRefs} disabled={busy||!recipe?.reference_supported} title={recipe&&!recipe.reference_supported?'This recipe is text-only':undefined} onClick={()=>setStartFrom('reference')}><strong>From reference frames</strong><small>Start and/or end on a picture</small></button>
    </div>
    {fromRefs?<FilmReferences first={first} last={last} onChange={(a,b)=>{setFirst(a);setLast(b)}} disabled={busy} source={referenceSource} lastTested={!!recipe?.last_frame_tested}/>:null}
    {fromRefs&&!first&&!last?<p className="gen-hint">No frames chosen yet, so this take would be text only.</p>:null}
    {recipe&&!recipe.reference_supported?<p className="gen-hint">This recipe is text-only; reference inputs are unavailable.</p>:null}</>:null}
    {planned?<fieldset className="gen-setup"><legend>Shot plan: {planned.label}</legend><p>Frames {planned.start_frame}–{planned.end_frame}, plan revision {planned.revision}. Brief and references are locked to the plan (edit them in Shot plan, save, then prepare again). Placing it is picture-only; existing audio stays fixed.</p>{target?.id!==planned.sequence_id?<p role="alert">Return to the planned sequence before generating.</p>:null}{planned.end_frame-planned.start_frame>(recipe?.frames??0)?<p role="alert">{`This interval needs ${planned.end_frame-planned.start_frame} frames; the current recipe yields ${recipe?.frames??0}. Use a longer existing take or split the assignment; generation is blocked.`}</p>:null}{referenceImages.length?<><p className="gen-hint">{referenceImages.length} visual conditioning image{referenceImages.length===1?'':'s'} (R2V), not a first-frame anchor.</p><div className="gen-refs">{referenceImages.map((r,i)=><figure key={`${i}:${r.image_id}`}><img src={`/api/film/images/${r.image_id}/media`} alt={r.role}/><figcaption>{r.role}</figcaption></figure>)}</div></>:null}<details><summary>Plan references</summary><p>First reference: {planned.first_frame_id??'None'}<br/>Last reference: {planned.last_frame_id??'None'}</p><p>Generated duration may differ; fitting requires explicit trimming and rejects short takes.</p></details><button disabled={busy} onClick={()=>{setPlanned(null);setFirst('');setLast('')}}>Unbind shot-plan setup</button></fieldset>
    :continuation?<fieldset className="gen-setup"><legend>Continuing a shot</legend><div className="gen-setup-row"><img src={continuation.image.media_url} alt="Continuation first frame from rendered shot"/><div><p>Starts from the last frame of the saved shot (rendered frame {continuation.source.rendered_frame}) and goes right after it, at cut {continuation.destination.insert_index}. The original shot stays unchanged.</p><p className="gen-hint">Skips {continuation.boundary_policy.drop_generated_first_frames} generated frame so the boundary isn’t doubled; a seamless match isn’t guaranteed.</p></div></div>{continuationStale?<p role="alert">The selected sequence or saved revision changed. Return to the original unchanged cut or prepare a fresh continuation. No automatic retargeting.</p>:null}<details><summary>Continuation lineage</summary><p>{continuation.boundary_policy.guarantee} Source frame {continuation.source.last_used_source_frame}; audio starts at frame {continuation.boundary_policy.audio_source_in_frame}.</p><pre>{JSON.stringify(continuation,null,2)}</pre></details><button disabled={busy} onClick={()=>{setContinuation(null);setFirst('');setLast('')}}>Discard continuation setup</button></fieldset>:null}
    {!continuation&&!planned?<fieldset className="generation-where"><legend>Where it goes</legend><label>Place the take<select aria-label="Where the take goes" value={where} disabled={busy} onChange={e=>setWhere(e.target.value as typeof where)}><option value="playhead">At the playhead (frame {frame})</option><option value="after" disabled={!selectedClip}>After the selected clip{selectedClip?`: “${selectedClip.label}”`:' (select a clip first)'}</option><option value="before" disabled={!selectedClip}>Before the selected clip{selectedClip?`: “${selectedClip.label}”`:' (select a clip first)'}</option><option value="end">At the end of the sequence</option><option value="library">Library only (place it yourself later)</option></select></label><p>{where==='library'?'Nothing is marked on the timeline; the take appears in Recent takes and the Browser.':'A marker shows the spot on the timeline. When the take is in the Browser, Place inserts its picture and sound there (or drag it in).'}{needsClip&&!selectedClip?' Click a clip on V1 to choose it.':''}</p></fieldset>:null}{timelineDirty&&destination?<p>Save or discard the timeline draft before requesting a clip for this sequence.</p>:null}
    <div className="film-actions generation-go"><span className="gen-summary">{startSummary}{lengthFrames&&recipe?` · ${(lengthFrames/recipe.fps).toFixed(2)} s`:''} · seed {seed}</span><button className="ed-primary" disabled={busy||!valid} title={valid?'Checks the worker and recipe first, then submits only if the check passes':blockers.join(' ')} onClick={generate}>{awaitingWarningConfirm?'Generate video + sound anyway':'Generate video + sound'}</button>{busy?<span>Working…</span>:null}</div>
    {!valid&&!busy&&blockers.length?<p className="gen-hint gen-blockers">{blockers.join(' ')}</p>:null}
    {check&&(!ready||check.warnings.length)?<div role="status"><p>{ready?'Worker check passed with warnings. Read them, then click Generate again to submit anyway, or change the settings.':'Not ready to generate. Resolve the issues below, then click Generate again.'}</p>{check.errors.map((e,i)=><p key={i}>{e.code}: {e.message}</p>)}{check.warnings.map((w,i)=><p key={i}>{typeof w==='string'?w:w.message}</p>)}</div>:null}
    {notice?<p role="status">{notice}</p>:null}{error?<p role="alert">{error}</p>:null}
    <details className="generation-settings"><summary>Settings · worker, seed, recipe</summary>
      {recipe?<><p><strong>{recipe.name}</strong> · {recipe.width} × {recipe.height} · {recipe.fps} fps · {recipe.steps} steps. Model settings stay fixed; only length, brief, seed and references vary.</p>{rules?.adjustable?<label className="gen-length-limit">Longest clip (coherence limit, seconds)<input type="number" aria-label="Longest clip in seconds" min={rules.min/rules.fps} max={rules.max/rules.fps} step={rules.step/rules.fps} value={Number((lengthLimit/rules.fps).toFixed(2))} disabled={busy} onChange={e=>{const v=Number(e.target.value);if(v>0)setLimitStored(Math.round(v*rules.fps))}}/><small>Clips longer than this cannot be requested. Proven so far: {rules.proven.map(f=>`${(f/rules.fps).toFixed(2)} s`).join(', ')}; the server allows up to {(rules.max/rules.fps).toFixed(1)} s. Saved in this browser.{limitStored!==null?<> <button type="button" onClick={()=>setLimitStored(null)}>Reset to proven</button></>:null}</small></label>:null}<details><summary>Recipe fingerprint</summary><code>{recipe.workflow_sha256}</code></details></>:null}
      <div className="film-imports"><label>H3 worker URL<input value={worker} disabled={busy} onChange={e=>setWorker(e.target.value)}/></label><label>Generation seed<input type="number" min={0} max={2147483647} step={1} value={seed} disabled={busy} onChange={e=>setSeed(e.target.value)}/></label></div>
      <div className="film-actions"><button disabled={busy} onClick={()=>void action(async()=>{await refresh();onJobsChanged()})}>Refresh recipe & jobs</button><button disabled={busy||!valid} title="Optional: check without generating" onClick={()=>void action(async()=>{const key=current.current;const next=await api<Check>('film/generation/preflight',body);if(key===current.current)setCheck(next);setNotice(next.ready?'Worker check passed. No generation was submitted.':'Worker check did not pass. No generation was submitted.')})}>Check worker & recipe</button></div>
      {check&&ready?<p role="status">Worker check passed for these settings; Generate will use it.</p>:null}
    </details>
    <RecentTakes active={active} jobs={(state?.jobs??[]) as TakeJob[]} highlight={lastRequested} mediaFor={mediaFor} assetStatus={assetStatus} onAudition={onAudition} auditionBlocked={auditionBlocked??null} onReview={onReviewVideo} onOpenHistory={onOpenHistory}
      onImport={async id=>{await importTakeJob(id);await onLibraryChanged?.();await refresh();onJobsChanged()}}/>
    <p className="generation-history-link">Every run, with import and placing, is in the <button onClick={()=>onOpenHistory?.()}>History</button> tab.</p>
  </div>
}

/** Recent picture + sound takes, newest first, with an inline player (picture with its production sound).
 *  Filter by how the take started. Playing changes nothing; Import to audition only adds the finished take to the library as a candidate. */
function RecentTakes({ active, jobs, highlight, mediaFor, onAudition, auditionBlocked, onReview, onOpenHistory, onImport }: { active: boolean; jobs: TakeJob[]; highlight: string | null; mediaFor?: (id: string) => string | undefined; assetStatus?: (id: string) => string | undefined; onAudition?: (job: GenerationJob) => void; auditionBlocked: string | null; onReview: (videoId: string) => void; onOpenHistory?: (jobId?: string) => void; onImport: (jobId: string) => Promise<void> }) {
  const [filter, setFilter] = useState<'all' | 'text' | 'reference'>(() => { try { const v = localStorage.getItem('llr.film.generation.takeFilter.v1'); return v === 'text' || v === 'reference' ? v : 'all' } catch { return 'all' } })
  useEffect(() => { try { localStorage.setItem('llr.film.generation.takeFilter.v1', filter) } catch { /* optional preference */ } }, [filter])
  const [pick, setPick] = useState<string | null>(null)
  const [autoplay, setAutoplay] = useState(false)
  const [loop, setLoop] = useState(true)
  const [limit, setLimit] = useState(8)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const player = useRef<HTMLVideoElement>(null)
  // `hidden` does not stop media: pause when the tab is left or the window is hidden, and never start by itself after a filter change.
  useEffect(() => { if (!active) { player.current?.pause(); setAutoplay(false) } }, [active])
  useEffect(() => { const hide = () => { if (document.hidden) player.current?.pause() }; document.addEventListener('visibilitychange', hide); return () => document.removeEventListener('visibilitychange', hide) }, [])
  useEffect(() => { setAutoplay(false) }, [filter])
  // A take you just requested is selected, and the filter opens up so it is visible whatever it started from.
  useEffect(() => { if (highlight) { setPick(highlight); setAutoplay(false); setFilter('all') } }, [highlight])
  const sorted = [...jobs].sort((a, b) => String(b.metadata?.created ?? '').localeCompare(String(a.metadata?.created ?? '')))
  const counts = { all: sorted.length, text: sorted.filter(j => takeKind(j) === 'text').length, reference: sorted.filter(j => takeKind(j) !== 'text').length }
  const listed = sorted.filter(j => filter === 'all' || (filter === 'text') === (takeKind(j) === 'text'))
  const shown = listed.slice(0, limit)
  const selected = listed.find(j => j.id === pick) ?? listed[0] ?? null
  const media = (j: TakeJob) => j.video_asset_id ? mediaFor?.(j.video_asset_id) : undefined
  function status(j: TakeJob) {
    if (ACTIVE.includes(j.status)) return <JobStage job={j} stage={j.status} />
    if (['failed', 'canceled'].includes(j.status)) return <span className="take-status" data-kind="failed">Failed</span>
    if (!j.video_asset_id) return <span className="take-status" data-kind="attention">{j.ready_to_import ? 'Ready to import' : 'Waiting for result'}</span>
    return <span className="take-status" data-kind="done">In the Browser</span>
  }
  function importIt(j: TakeJob) { if (busy) return; setBusy(true); setError(''); void onImport(j.id).then(() => { setPick(j.id); setAutoplay(true) }).catch(e => setError(message(e))).finally(() => setBusy(false)) }
  const sel = selected, selMedia = sel ? media(sel) : undefined, selRefs = sel ? takeRefs(sel) : [], selKind = sel ? takeKind(sel) : 'text'
  return <section className="gen-takes" aria-label="Recent takes" onKeyDown={e => { if (e.key === ' ' || e.key.startsWith('Arrow')) e.stopPropagation() /* keep the editor's transport keys out of the player */ }}>
    <header><h3>Recent takes</h3>
      <div className="take-filter" role="radiogroup" aria-label="Show takes">{(['all', 'text', 'reference'] as const).map(f => <button key={f} type="button" role="radio" aria-checked={filter === f} onClick={() => setFilter(f)}>{f === 'all' ? 'All' : f === 'text' ? 'Text only' : 'From reference'} <small>{counts[f]}</small></button>)}</div>
    </header>
    {!sorted.length ? <p className="gen-hint">No takes yet. Write a brief above and generate one; it will play here.</p> : !listed.length ? <p className="gen-hint">No {filter === 'text' ? 'text-only' : 'reference'} takes yet.</p> : null}
    {sel ? <div className="take-preview">
      <div className="take-preview-stage">{selMedia
        ? <video ref={player} key={sel.video_asset_id} src={selMedia} controls playsInline preload="metadata" loop={loop} autoPlay={autoplay} aria-label={`Preview ${sel.label}`} />
        : <div className="take-preview-empty">{ACTIVE.includes(sel.status) ? <>Generating on the worker… {status(sel)}<small>It plays here once it is finished and imported.</small></> : ['failed', 'canceled'].includes(sel.status) ? <>This take did not finish.{sel.error ? <small>{sel.error.message}</small> : null}</> : sel.ready_to_import ? <>Finished. Import it to play it here.</> : sel.video_asset_id ? <>Its picture is not in the library list yet.</> : <>Waiting for a result.</>}</div>}</div>
      <div className="take-preview-side">
        <p className="take-preview-title"><strong>{sel.label}</strong> <span className="take-kind" data-kind={selKind}>{KIND_LABEL[selKind]}</span> {status(sel)}</p>
        {selRefs.length ? <div className="gen-refs" title="The reference frames this take was conditioned on">{selRefs.map((r, i) => <figure key={i}><img src={r.url} alt={`${r.role} reference: ${r.label}`} /><figcaption>{r.role}</figcaption></figure>)}</div> : null}
        {briefOf(sel) ? <p className="take-brief" title={briefOf(sel)}>{briefOf(sel)}</p> : null}
        <div className="film-actions">
          {!sel.video_asset_id && sel.ready_to_import ? <button className="ed-primary" disabled={busy} title="Adds the finished picture and its production sound to the library as candidates, then plays it here" onClick={() => importIt(sel)}>{busy ? 'Importing…' : 'Import to audition'}</button> : null}
          {selMedia ? <label className="take-loop"><input type="checkbox" checked={loop} onChange={e => setLoop(e.target.checked)} />Loop</label> : null}
          {sel.video_asset_id && onAudition ? <button disabled={!selMedia || !!auditionBlocked} title={auditionBlocked ?? 'Play it between its neighbours at its spot (or the playhead) without placing it'} onClick={() => onAudition(sel)}>Audition in context</button> : null}
          {sel.video_asset_id ? <button title="Open it in the Viewer to mark In / Out" onClick={() => onReview(sel.video_asset_id!)}>Open in Viewer</button> : null}
          <button className="take-history" onClick={() => onOpenHistory?.(sel.id)}>Show in Queue</button>
        </div>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    </div> : null}
    {shown.length ? <ul className="take-list">{shown.map(j => { const m = media(j), refs = takeRefs(j), k = takeKind(j)
      return <li key={j.id}><button type="button" className="take-card" aria-pressed={sel?.id === j.id} title={briefOf(j) || j.label} onClick={() => { setPick(j.id); setAutoplay(true); if (sel?.id === j.id && player.current) { if (player.current.ended) player.current.currentTime = 0; void player.current.play().catch(() => {}) } /* same take already loaded: autoPlay won't fire again */ }}>
        <span className="take-card-pic">{m && j.video_asset_id ? <Thumb src={m} frame={24} cacheKey={`${j.video_asset_id}:24`} className="take-thumb" /> : refs[0] ? <img src={refs[0].url} alt="" /> : <span className="take-card-blank">{ACTIVE.includes(j.status) ? '↻' : '—'}</span>}{m && refs[0] ? <img className="take-card-ref" src={refs[0].url} alt="" /> : null}{m ? <i className="take-card-play" aria-hidden="true">▶</i> : null}</span>
        <span className="take-card-label">{j.label}</span>
        <span className="take-card-meta"><span className="take-kind" data-kind={k}>{KIND_LABEL[k]}</span>{status(j)}</span>
      </button></li> })}</ul> : null}
    {listed.length > limit ? <button className="take-more" onClick={() => setLimit(l => l + 8)}>Show more ({listed.length - limit})</button> : null}
  </section>
}



