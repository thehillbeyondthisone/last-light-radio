import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import { JobMetadata, JobStage, PlacementActions } from './GenerationFlow'
import type { GenerationJob, GenerationPlacement, GenerationTarget } from './GenerationFlow'

/** The Queue tab (was History; reworked 2026-11-19): the worker queue for every generation run (picture + sound takes and music cues).
 *  Its one job is what is still in flight or needs attention: rendering, failed, stuck, import failed, or a requested spot / reserved
 *  placement still waiting. Finished clips import themselves and live in the Browser (drag them onto the timeline); they fold away
 *  here under Finished. Nothing here generates; Check existing job, Import (fallback) and Place are the user's clicks. */
type Kind = 'take' | 'music'
type Row = { kind: Kind; job: GenerationJob }
const ACTIVE = ['pending', 'submitting', 'queued', 'running']
const ROUTE: Record<Kind, string> = { take: 'film/generation', music: 'film/music' }
/** Import a finished picture + sound take into the Browser (fallback when the automatic import failed); returns the video asset id. */
export async function importTakeJob(jobId: string): Promise<string> {
  return (await api<{ video: { id: string } }>(`${ROUTE.take}/jobs/${jobId}/import`, {})).video.id
}
/** Ask the worker about an existing job again (never resubmits). */
export async function resumeJob(kind: Kind, jobId: string): Promise<void> { await api(`${ROUTE[kind]}/jobs/${jobId}/resume`, {}) }

export interface HistoryProps {
  target: GenerationTarget | null
  timelineDirty: boolean
  placements: GenerationPlacement[]
  selectedJob: string
  epoch: number
  onPlaced: () => Promise<void>
  onReviewVideo: (id: string) => void
  onReviewAudio: (id: string, role: 'production' | 'music') => void
  onImported: (kind: Kind, assetId: string) => Promise<void>
  onJobsChanged: () => void
  onGuide?: (jobId: string) => void
  onPlan?: () => void
  /** Place controls for a take without a server reservation (Generate tab takes and older library takes). */
  placer?: (job: GenerationJob) => ReactNode
  /** The take was requested for the open sequence (it has a spot here). */
  isHere?: (job: GenerationJob) => boolean
  /** The take's picture is already used in a saved sequence. */
  isPlaced?: (job: GenerationJob) => boolean
  /** Right-click on a card: the editor shows the shared context menu. */
  onMenu?: (job: GenerationJob, kind: Kind, x: number, y: number) => void
}

export default function FilmHistory({ target, timelineDirty, placements, selectedJob, epoch, onPlaced, onReviewVideo, onReviewAudio, onImported, onJobsChanged, onGuide, onPlan, placer, isHere, onMenu }: HistoryProps) {
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [showAll, setShowAll] = useState(false), [kinds, setKinds] = useState<'all' | Kind>('all')
  const lock = useRef(false)
  async function refresh() {
    const [takes, music] = await Promise.all([api<{ jobs: GenerationJob[] }>(ROUTE.take), api<{ jobs: GenerationJob[] }>(ROUTE.music).catch(() => ({ jobs: [] }))])
    setRows([...takes.jobs.map(job => ({ kind: 'take' as const, job })), ...music.jobs.map(job => ({ kind: 'music' as const, job }))]
      .sort((a, b) => String(b.job.metadata?.created ?? '').localeCompare(String(a.job.metadata?.created ?? ''))))
  }
  useEffect(() => { void refresh().catch(e => setError(e instanceof Error ? e.message : String(e))) }, [epoch])
  useEffect(() => {
    if (!rows.some(r => ACTIVE.includes(r.job.status))) return
    const timer = window.setInterval(() => { void refresh().catch(() => {}) }, 2500)
    return () => clearInterval(timer)
  }, [rows])
  // Tell the editor when a job's status or import changes, so timeline flags and the guide stay current.
  const statusSig = useRef('')
  useEffect(() => { const sig = rows.map(r => r.job.id + ':' + r.job.status + ':' + (r.job.video_asset_id ?? '')).join(); if (statusSig.current && statusSig.current !== sig) onJobsChanged(); statusSig.current = sig }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedJob) document.getElementById(`generation-job-${selectedJob}`)?.scrollIntoView({ block: 'nearest' }) }, [selectedJob])
  async function action(work: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { lock.current = false; setBusy(false) }
  }
  const placementOf = (job: GenerationJob) => placements.find(p => p.job_id === job.id)
  const active = (job: GenerationJob) => ACTIVE.includes(job.status)
  const imported = (r: Row) => r.kind === 'take' ? !!r.job.video_asset_id : !!r.job.audio_asset_id
  // Finished = nothing left to do here: imported into the Browser and not waiting for a requested spot or reserved placement.
  const done = (r: Row) => { const p = placementOf(r.job); if (p) return p.placed_revision !== null; if (r.kind === 'take' && isHere?.(r.job)) return false /* requested for this sequence: open until placed here */; return imported(r) && !r.job.destination }
  // Library-only runs belong to every sequence (finished ones fold under Finished); requested ones to their own sequence.
  const mine = (r: Row) => !!placementOf(r.job) || r.job.destination?.sequence_id === target?.id || !!isHere?.(r.job) || !r.job.destination
  const listed = rows.filter(r => (kinds === 'all' || r.kind === kinds) && (showAll || mine(r)))
  const open = listed.filter(r => !done(r)), finished = listed.filter(done)
  function nextStep(r: Row) {
    const { job } = r, p = placementOf(job), stage = p?.stage ?? job.status
    if (active(job)) return 'Generating on the worker. You can keep editing; this card updates by itself.'
    if (['failed', 'canceled'].includes(job.status)) return 'Did not finish. Check the error, adjust the brief or settings, and generate again.'
    if (!imported(r)) return job.ready_to_import ? (job.import_error ? `Finished, but copying it into the Browser failed: ${job.import_error} Import it now to try again.` : job.import_stage === 'importing' ? 'Finished; copying it into the Browser…' : 'Finished before automatic import existed. Import it to add it to the Browser.') : 'Waiting for a result. Use Check existing job if this looks stuck.'
    if (p) {
      if (p.placed_revision !== null) return `Placed in revision ${p.placed_revision}.`
      if (stage === 'ready_to_place' || stage === 'awaiting_review') return 'In the Browser. Confirm the position below and place it.'
      if (stage === 'conflict') return 'The sequence changed since you asked. Check the destination below.'
    }
    if (job.destination && job.destination.sequence_id !== target?.id) return 'Belongs to another sequence. Open it to see where this take stands.'
    return r.kind === 'take' ? 'In the Browser. Drag it onto the timeline, or Insert it (F9).' : 'In the Browser. Drag it onto A2, or place it from the Audio tab.'
  }
  function card(r: Row) {
    const { job, kind } = r, p = placementOf(job), meta = p?.job ?? job
    return <article id={`generation-job-${job.id}`} key={job.id} className={`generation-card${job.id === selectedJob ? ' generation-selected' : ''}`} data-kind={kind} data-done={done(r) || undefined}
      onContextMenu={onMenu ? e => { if ((e.target as HTMLElement).closest('input, textarea, select')) return; e.preventDefault(); onMenu(job, kind, e.clientX, e.clientY) } : undefined}>
      <header><span className="history-kind">{kind === 'take' ? 'Picture + sound' : 'Music cue'}</span><strong>{job.label}</strong> <JobStage job={meta} stage={p?.stage ?? job.status} />{onGuide && kind === 'take' ? <button className="generation-card-guide" onClick={() => onGuide(job.id)}>Guide me</button> : null}</header>
      {placer && kind === 'take' && !p && imported(r) && placer(job) ? null : <p className="generation-next">{nextStep(r)}{job.error ? ` ${job.error.message}` : ''}</p>}
      <div className="film-actions">
        {job.can_resume && !imported(r) ? <button disabled={busy} onClick={() => void action(async () => { await resumeJob(kind, job.id); await refresh(); onJobsChanged() })}>Check existing job (no resubmit)</button> : null}
        {job.ready_to_import && !imported(r) ? <button className="ed-primary" disabled={busy} onClick={() => void action(async () => {
          if (kind === 'take') { const videoId = await importTakeJob(job.id); await refresh(); await onImported(kind, videoId); setNotice('Imported into the Browser. Drag it onto the timeline, or Insert it.') }
          else { const result = await api<{ audio: { id: string } }>(`${ROUTE.music}/jobs/${job.id}/import`, {}); await refresh(); await onImported(kind, result.audio.id); setNotice('Music imported into the Browser. Drag it onto A2.') }
        })}>{kind === 'take' ? 'Import video & production sound' : 'Import music candidate'}</button> : null}
        {!p && imported(r) ? (kind === 'take' ? (placer ? null : <button onClick={() => onReviewVideo(job.video_asset_id!)}>Open in Viewer</button>) : <button onClick={() => onReviewAudio(job.audio_asset_id!, 'music')}>Listen</button>) : null}
      </div>
      {!p && kind === 'take' && imported(r) && placer ? placer(job) : null}
      {p ? <PlacementActions onPlan={onPlan} placement={p} target={target} dirty={timelineDirty} onPlaced={onPlaced} onVideo={onReviewVideo} onAudio={id => onReviewAudio(id, kind === 'music' ? 'music' : 'production')} /> : null}
      <JobMetadata job={meta} />
    </article>
  }
  return <div className="film-generation film-history">
    <h2>Queue <small>{open.length} need{open.length === 1 ? 's' : ''} attention · {rows.length} runs</small></h2>
    <p className="history-purpose">Generation jobs that are rendering, failed, or still waiting to be placed. Finished clips appear in the Browser by themselves.</p>
    <div className="history-filters">
      <label><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />All sequences</label>
      <label>Show<select value={kinds} onChange={e => setKinds(e.target.value as 'all' | Kind)}><option value="all">Takes and music</option><option value="take">Picture + sound takes</option><option value="music">Music cues</option></select></label>
      <button disabled={busy} onClick={() => void action(async () => { await refresh(); onJobsChanged() })}>Refresh</button>
    </div>
    {notice ? <p role="status">{notice}</p> : null}{error ? <p role="alert">{error}</p> : null}
    {!rows.length ? <p>No generation runs in this library yet. Use the Generate tab.</p> : !listed.length ? <p>Nothing for this sequence. Tick All sequences to see the rest.</p> : !open.length ? <p>Nothing needs attention. Finished clips are in the Browser.</p> : null}
    {open.map(card)}
    {finished.length ? <details className="generation-done"><summary>Finished, in the Browser ({finished.length})</summary>{finished.map(card)}</details> : null}
  </div>
}
