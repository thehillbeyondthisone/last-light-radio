import { useEffect, useRef, useState } from 'react'
import type { GenerationPlacement } from './GenerationFlow'
import { generationStage } from './GenerationFlow'
import type { GenSnapshot, GenWhere } from './FilmGeneration'
import { guideSteps } from './guideSteps'
import type { GuideStep, GuideTarget } from './guideSteps'

export type { GuideTarget } from './guideSteps'
export { guideSteps } from './guideSteps'

/** Step-by-step generation guide. Each step has a button that does it, using the same code as the Generate tab, History card,
 *  Viewer review and Save. Nothing happens on its own except ticking steps off as the take's state changes:
 *  generating, placing and saving are always the creator's clicks. Finished takes import by themselves (2026-11-19). */
export interface GuideActions {
  gen: GenSnapshot | null
  setBrief: (v: string) => void
  setLabel: (v: string) => void
  setWhere: (v: GenWhere) => void
  generate: () => void
  /** Drop a continuation / shot-plan setup so the take is an ordinary one with a spot you choose. */
  clearSetup: () => void
  /** Prepare the continuation again from the same shot (current saved, exported cut). */
  prepareAgain: () => void
  /** Why preparing again is not possible yet (null = it is). */
  prepareBlock: string | null
  /** Job is finished and can be imported. */
  canImport: boolean
  importTake: () => void
  /** Worker job can be asked about again without resubmitting. */
  resume: (() => void) | null
  /** Open the take in the Viewer to watch it. */
  openReview: () => void
  audition: (() => void) | null
  /** Place at the take's flag ("at the playhead (frame 120)"), if it has one in this sequence. */
  spotNote: string | null
  placeAtSpot: () => void
  placeAtPlayhead: () => void
  playheadNote: string
  /** Playhead frame (kept out of the form snapshot so playback does not re-render the editor twice a frame). */
  frame: number
  save: () => void
  saveNote: string
  busy: boolean
  error: string
}

export interface GuideProps {
  placement: GenerationPlacement | null
  client: boolean
  inTimeline: boolean
  savedPlaced: boolean
  act: GuideActions
  onShow: (target: GuideTarget, placement: GenerationPlacement | null) => void
  onClose: () => void
  onPickNew: () => void
}

const WHERE: [GenWhere, string][] = [['playhead', 'At the playhead'], ['after', 'After the selected clip'], ['before', 'Before the selected clip'], ['end', 'At the end of the sequence'], ['library', 'Library only (place it yourself later)']]

export default function GenerationGuide({ placement, client, inTimeline, savedPlaced, act, onShow, onClose, onPickNew }: GuideProps) {
  const [briefOk, setBriefOk] = useState(false), [whereOk, setWhereOk] = useState(false)
  const jobId = placement?.job_id ?? null
  useEffect(() => { if (!jobId) { setBriefOk(false); setWhereOk(false) } }, [jobId])
  const gen = act.gen
  const steps = guideSteps({ placement, hasBrief: !!gen?.brief.trim(), briefConfirmed: briefOk, whereConfirmed: whereOk, client, inTimeline, savedPlaced })
  const current = steps.find(s => s.status === 'current')
  // The brief box keeps its own text while you type (so the cursor never jumps) and follows the Generate tab otherwise.
  const [brief, setBrief] = useState(gen?.brief ?? '')
  const briefBox = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (gen && document.activeElement !== briefBox.current) setBrief(gen.brief) }, [gen?.brief]) // eslint-disable-line react-hooks/exhaustive-deps
  // When you are working in the guide, focus follows you to the next step. It never takes focus from the editor
  // (a step that ticks itself while you edit must not catch your Space or Enter).
  const body = useRef<HTMLDivElement>(null), root = useRef<HTMLElement>(null)
  useEffect(() => { if (root.current?.contains(document.activeElement)) body.current?.querySelector<HTMLElement>('[data-guide-primary]')?.focus({ preventScroll: true }) }, [current?.id])
  const stage = placement?.stage ?? 'new'
  const failed = ['failed', 'canceled'].includes(stage)

  function stepBody(s: GuideStep) {
    const show = <button className="guide-link" onClick={() => onShow(s.id, placement)}>Show me where</button>
    switch (s.id) {
      case 'brief': return <>
        {gen?.locked ? <p className="guide-note">{gen.locked}</p> : null}
        <label className="guide-field">Shot brief<textarea ref={briefBox} aria-label="Guide shot brief" rows={4} value={brief} disabled={!gen || !!gen.locked || gen.busy} placeholder="What happens, how the camera sees it, what it sounds like." onChange={e => { setBrief(e.target.value); act.setBrief(e.target.value) }} /></label>
        <label className="guide-field">Take label<input aria-label="Guide take label" value={gen?.label ?? ''} disabled={!gen || gen.busy} placeholder="Name this take" maxLength={100} onChange={e => act.setLabel(e.target.value)} /></label>
        <div className="guide-actions"><button data-guide-primary className="ed-primary" disabled={!brief.trim()} onClick={() => setBriefOk(true)}>Next: where it goes</button><button className="guide-link" onClick={() => onShow('brief', placement)}>Add reference frames (Generate tab)</button></div>
      </>
      case 'destination': if (gen?.setup) { const su = gen.setup, cont = su.kind === 'continuation'; return <>
        <p><b>Goes:</b> {su.where}</p>
        {su.stale ? <>
          <p className="guide-note">{su.stale}</p>
          {cont ? <p>Either prepare it again from the same shot (keeps your brief), or drop it and make an ordinary take whose spot you choose.</p> : <p>Open the planned sequence, or drop the plan setup and make an ordinary take whose spot you choose.</p>}
          {cont && act.prepareBlock ? <p className="guide-hint">To prepare again: {act.prepareBlock}</p> : null}
          <div className="guide-actions">
            {cont ? <button data-guide-primary className="ed-primary" disabled={act.busy || !!act.prepareBlock} onClick={act.prepareAgain}>Prepare it again from this shot</button> : null}
            <button data-guide-primary={!cont || undefined} className={cont ? undefined : 'ed-primary'} disabled={gen.busy} onClick={act.clearSetup}>Drop it and choose a spot</button>
            <button className="guide-link" onClick={() => setBriefOk(false)}>Back</button>
          </div>
        </> : <div className="guide-actions"><button data-guide-primary className="ed-primary" onClick={() => setWhereOk(true)}>Next: generate</button><button disabled={gen.busy} onClick={act.clearSetup}>Choose a spot instead</button><button className="guide-link" onClick={() => setBriefOk(false)}>Back</button></div>}
      </> }
        return <>
        {gen && !gen.showsWhere ? <p>This take already has its destination.</p> : <label className="guide-field">Place the take<select aria-label="Guide: where the take goes" value={gen?.where ?? 'playhead'} disabled={!gen || gen.busy} onChange={e => act.setWhere(e.target.value as GenWhere)}>
          {WHERE.map(([v, text]) => <option key={v} value={v} disabled={(v === 'before' || v === 'after') && !gen?.selectedClipLabel}>{text}{v === 'playhead' ? ` (frame ${act.frame})` : (v === 'before' || v === 'after') ? (gen?.selectedClipLabel ? `: “${gen.selectedClipLabel}”` : ' (select a clip first)') : ''}</option>)}
        </select></label>}
        <div className="guide-actions"><button data-guide-primary className="ed-primary" onClick={() => setWhereOk(true)}>Next: generate</button><button className="guide-link" onClick={() => setBriefOk(false)}>Back</button></div>
      </>
      case 'generate': return <>
        <p className="guide-recap">“{(gen?.brief ?? '').slice(0, 140)}{(gen?.brief.length ?? 0) > 140 ? '…' : ''}” · {gen?.setup ? gen.setup.where : WHERE.find(w => w[0] === gen?.where)?.[1]}</p>
        {gen?.blockers.length ? <ul className="guide-problems">{gen.blockers.map(b => <li key={b}>{b}</li>)}</ul> : null}
        {gen?.checkLines.length ? <div className="guide-check" role="status"><p>{gen.awaitingWarningConfirm ? 'The worker check passed with warnings. Read them; click again to send anyway.' : 'The worker check did not pass. Nothing was sent.'}</p><ul>{gen.checkLines.map(l => <li key={l}>{l}</li>)}</ul></div> : null}
        {gen?.error ? <p className="guide-note" role="alert">{gen.error}</p> : null}
        <div className="guide-actions"><button data-guide-primary className="ed-primary" aria-label={gen?.awaitingWarningConfirm ? 'Guide: send to the worker anyway' : 'Guide: send to the worker'} disabled={!gen || gen.busy || !gen.valid} onClick={act.generate}>{gen?.busy ? 'Checking the worker…' : gen?.awaitingWarningConfirm ? 'Send anyway' : 'Check the worker and send'}</button><button className="guide-link" disabled={gen?.busy} onClick={() => setWhereOk(false)}>Back</button></div>
      </>
      case 'job': return <>
        <p>Now: <b>{generationStage(stage)}</b>{placement?.job.error ? ` · ${placement.job.error.message}` : ''}</p>
        <div className="guide-actions">
          {failed ? <button data-guide-primary className="ed-primary" onClick={onPickNew}>Change the brief and try again</button> : null}
          {act.resume ? <button data-guide-primary={!failed || undefined} disabled={act.busy} onClick={act.resume}>Ask the worker again (no resubmit)</button> : null}
          <button className="guide-link" onClick={() => onShow('job', placement)}>Open its card in the Queue</button>
        </div>
      </>
      case 'import': return <>
        {!act.canImport ? <p>Waiting for the result. It copies itself into the Browser when it is ready.</p> : <p>The result is ready. If it does not appear in the Browser by itself, import it now; the Queue card shows why it failed.</p>}
        <div className="guide-actions"><button data-guide-primary className="ed-primary" disabled={act.busy || !act.canImport} onClick={act.importTake}>Import picture and sound</button>{act.resume && !act.canImport ? <button disabled={act.busy} onClick={act.resume}>Ask the worker again (no resubmit)</button> : null}{show}</div>
      </>
      case 'place': return client ? <>
        <div className="guide-actions">
          {act.spotNote ? <button data-guide-primary className="ed-primary" disabled={act.busy} onClick={act.placeAtSpot}>Put it in {act.spotNote}</button> : null}
          <button data-guide-primary={!act.spotNote || undefined} className={act.spotNote ? undefined : 'ed-primary'} disabled={act.busy} onClick={act.placeAtPlayhead}>Put it in at the playhead ({act.playheadNote})</button>
          {act.audition ? <button onClick={act.audition}>Audition first</button> : null}<button onClick={act.openReview}>Watch it in the Viewer</button>
        </div>
      </> : <div className="guide-actions"><button data-guide-primary className="ed-primary" onClick={() => onShow('place', placement)}>Open its card</button></div>
      case 'save': return <>
        {act.saveNote ? <p>Unsaved: {act.saveNote}</p> : null}
        <div className="guide-actions"><button data-guide-primary className="ed-primary" disabled={act.busy} onClick={act.save}>Save the sequence</button></div>
        <p className="guide-hint">Changed your mind? Ctrl+Z on the timeline takes it out again.</p>
      </>
    }
  }

  return <aside ref={root} className="generation-guide" role="dialog" aria-label="Generation guide" onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }}>
    <header><strong>Generation guide</strong><span>{placement ? <>“{placement.job.label}” · {generationStage(placement.stage)}</> : 'A new take'}</span><button aria-label="Close guide" title="Close (Esc)" onClick={onClose}>×</button></header>
    <p className="guide-intro">Work down the steps; each button does that step for you. Sending to the worker, placing and saving only happen when you click.</p>
    <ol>{steps.map((s, n) => <li key={s.id} data-status={s.status} aria-current={s.status === 'current' ? 'step' : undefined}>
      <span className="guide-mark" aria-hidden="true">{s.status === 'done' ? '✓' : n + 1}</span>
      <div><strong>{s.title}</strong>
        {s.status === 'current' ? <div ref={body} className="guide-body"><p>{s.id === 'destination' && gen?.setup ? (gen.setup.kind === 'continuation' ? 'This is a continuation, so its place is fixed: it goes straight after the shot it continues. There is no spot to pick.' : 'This take belongs to a shot plan, so its place is the planned interval.') : s.what}</p>{s.note ? <p className="guide-note">{s.note}</p> : null}{stepBody(s)}</div> : s.note && s.status !== 'done' ? <p className="guide-note">{s.note}</p> : null}
      </div>
    </li>)}</ol>
    {act.error ? <p className="guide-note" role="alert">{act.error}</p> : null}
    <footer>{current ? <span>Step {steps.indexOf(current) + 1} of {steps.length}</span> : <span>All done. The take is in the sequence and saved.</span>}{placement ? <button onClick={onPickNew}>{current ? 'Guide a new take instead' : 'Guide another take'}</button> : null}</footer>
  </aside>
}
