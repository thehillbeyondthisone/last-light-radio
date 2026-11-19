import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import Icon from './Icon'
import AmbienceCanvas from './AmbienceCanvas'
import type { Pilot, StudioState } from './types'

function clock(frame: number, fps = 24) {
  const seconds = Math.floor(frame / fps)
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}

export default function PilotView({ data, refresh, notify }: { data: StudioState; refresh: () => Promise<void>; notify: (text: string) => void }) {
  const initialScene = data.pilot_catalog?.find((item) => item.approved_count > 0)?.scene_id ?? data.scenes[0]?.id ?? ''
  const [sceneId, setSceneId] = useState(initialScene)
  const scene = data.scenes.find((item) => item.id === sceneId)
  const library = data.pilot_catalog?.find((item) => item.scene_id === sceneId)
  const [title, setTitle] = useState(`${data.scenes.find((item) => item.id === initialScene)?.title ?? 'Scene'} · 10-minute pilot`)
  const [density, setDensity] = useState('quiet')
  const [seed, setSeed] = useState('7')
  const [selectedClips, setSelectedClips] = useState<string[]>(data.pilot_catalog?.find((item) => item.scene_id === initialScene)?.clips.map((item) => item.id) ?? [])
  const [ambience, setAmbience] = useState<Record<string, number>>({})
  const ambientLayers = data.ambience_catalog?.find((item) => item.scene_id === sceneId)?.layers ?? []
  const [selectedId, setSelectedId] = useState(data.pilots?.[0]?.id ?? '')
  const [pilot, setPilot] = useState<Pilot | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const summary = data.pilots?.find((item) => item.id === selectedId)
  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    void api<Pilot>(`pilots/${selectedId}`, undefined, controller.signal).then(setPilot).catch((error) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setError(error instanceof Error ? error.message : 'Could not load the pilot.')
    })
    return () => controller.abort()
  }, [selectedId, summary?.status, summary?.progress])
  function chooseScene(id: string) {
    setAmbience({})
    setSceneId(id); setTitle(`${data.scenes.find((item) => item.id === id)?.title ?? 'Scene'} · 10-minute pilot`)
    setSelectedClips(data.pilot_catalog?.find((item) => item.scene_id === id)?.clips.map((item) => item.id) ?? [])
  }
  async function plan(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await api<Pilot>('pilots', { scene_id: sceneId, title, seed: Number(seed), density, candidate_ids: selectedClips, ambience: Object.entries(ambience).map(([kind, opacity]) => ({ kind, opacity })) })
      setPilot(result); setSelectedId(result.id); await refresh(); notify('Timeline saved. Preview the clips and holds, then export the pilot.')
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not build the pilot.') }
    finally { setBusy(false) }
  }
  async function exportPilot() {
    if (!pilot) return
    setBusy(true); setError('')
    try {
      setPilot(await api<Pilot>(`pilots/${pilot.id}/export`, {})); await refresh()
      notify('Export queued. The studio will encode and validate the MP4 in the background.')
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not queue the export.') }
    finally { setBusy(false) }
  }
  const exporting = pilot && ['queued', 'exporting'].includes(pilot.status)
  return <section className="page pilot-page">
    <div className="page-heading"><div><p className="eyebrow">PILOT BUILDER</p><h1>Let the scene settle in.</h1><p>Ten minutes from approved motion and quiet, continuous holds.</p></div><span className="workflow-label">10:00 · 24fps · silent</span></div>
    <div className="pilot-builder-grid"><form className="panel" onSubmit={(event) => void plan(event)}>
      <h2>Plan a visual pilot</h2><label className="field">Pilot scene<select value={sceneId} onChange={(event) => chooseScene(event.target.value)}>{data.scenes.map((item) => <option key={item.id} value={item.id}>{item.title} · {data.pilot_catalog?.find((entry) => entry.scene_id === item.id)?.approved_count ?? 0} approved clips</option>)}</select></label>
      <label className="field">Pilot title<input required maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="recipe-form-row"><label className="field">Motion density<select value={density} onChange={(event) => setDensity(event.target.value)}><option value="quiet">Quiet · at least 18s between motions</option><option value="balanced">Balanced · at least 10s between motions</option><option value="active">Active · at least 5s between motions</option></select></label><label className="field">Episode seed<input required type="number" min="0" max="2147483647" step="1" value={seed} onChange={(event) => setSeed(event.target.value)} /></label></div>
      <fieldset className="pilot-library"><legend>Approved motion library · {library?.approved_count ?? 0}</legend>{library?.clips.length ? library.clips.map((item) => <label key={item.id}><input type="checkbox" checked={selectedClips.includes(item.id)} onChange={(event) => setSelectedClips((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span><strong>{item.label}</strong><small>{item.actor} · {item.start_state.replaceAll('_', ' ')} → {item.end_state.replaceAll('_', ' ')}</small></span></label>) : <p>Approve a compatible motion take for this scene before planning a pilot.</p>}</fieldset>
      {library?.excluded.length ? <details className="provenance"><summary>Clips needing setup ({library.excluded.length})</summary>{library.excluded.map((item) => <p key={item.id}>{item.label}: {item.reason}</p>)}</details> : null}
      {ambientLayers.length ? <fieldset className="pilot-ambience"><legend>Continuous ambience</legend><p className="recipe-help">Recovered scene masks. Rain keeps falling across cuts; steam gently moves the painted plume already above the mug.</p>{ambientLayers.map((layer) => <div className="ambience-control" key={layer.kind}><label className="check-field"><input type="checkbox" checked={layer.kind in ambience} onChange={(event) => setAmbience((current) => { const next = { ...current }; if (event.target.checked) next[layer.kind] = layer.opacity; else delete next[layer.kind]; return next })} /><span>{layer.label}</span></label>{layer.kind in ambience ? <label className="field">{layer.label} strength · {Math.round(ambience[layer.kind] * 100)}%<input type="range" aria-label={`${layer.label} strength`} min="0" max="0.4" step="0.01" value={ambience[layer.kind]} onChange={(event) => setAmbience((current) => ({ ...current, [layer.kind]: Number(event.target.value) }))} /></label> : null}</div>)}<p className="recipe-note">Effects stay separate from character motion. Review a short section before exporting; the original pilot is preserved.</p></fieldset> : null}
      <p className="recipe-note">Clips play one at a time. Every hold retains the actual current frame. The seed fixes the selection and timing; no new AI generation is used.</p>
      <button className="button dark" disabled={busy || !scene || !selectedClips.length}><Icon name="scene" size={17} />{busy ? 'Preparing…' : 'Build timeline preview'}</button>
    </form><aside className="panel pilot-saved"><h2>Saved pilots</h2><p className="recipe-help">Plans and exports stay in your local working store.</p>{data.pilots?.length ? data.pilots.map((item) => <button key={item.id} className={`saved-pilot ${selectedId === item.id ? 'selected' : ''}`} onClick={() => { setSelectedId(item.id); setError('') }}><strong>{item.title}</strong><span>{item.status === 'complete' ? 'MP4 ready' : item.status === 'exporting' ? `Encoding · ${Math.round(item.progress * 100)}%` : item.status}{!item.approval_current ? ' · approval changed' : ''}</span></button>) : <p className="quiet-empty">Your first pilot will appear here.</p>}<div className="callout"><Icon name="lock" /><div><strong>Approved media, preserved</strong><p>Each plan pins the selected clips, review versions, seed and timecodes. Export never changes the originals or their approvals.</p></div></div></aside></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {pilot ? <div className="pilot-result"><div className="section-heading"><div><h2>{pilot.title}</h2><p>Saved seed {pilot.manifest.seed} · {pilot.manifest.clips.length} selected clips · {pilot.manifest.duration_frames.toLocaleString()} frames · {pilot.manifest.width} × {pilot.manifest.height}</p></div><span className="badge neutral">Draft pilot</span></div>
      {!pilot.approval_current ? <p className="form-error" role="alert">A clip approval changed. Rebuild this timeline before exporting. Existing exports remain in the history.</p> : null}
      <PilotTimeline key={pilot.id} pilot={pilot} />
      <div className="panel pilot-export"><div><h2>MP4 export</h2><p className="recipe-help">Silent H.264 video at 24fps. Base holds preserve decoded frames; enabled ambience keeps moving.</p></div><button className="button dark" disabled={busy || !!exporting || !pilot.approval_current || pilot.status === 'complete'} onClick={() => void exportPilot()}><Icon name="upload" size={17} />{exporting ? 'Exporting…' : pilot.status === 'complete' ? 'MP4 ready' : ['failed', 'interrupted'].includes(pilot.status) ? 'Retry export' : 'Export 10-minute MP4'}</button>
        {exporting ? <div className="export-progress"><progress max="1" value={pilot.progress} /><span>{pilot.progress >= 0.9 ? 'Validating full video and frame timing…' : `${Math.round(pilot.progress * 100)}% · encoding the saved timeline`}</span></div> : null}
        {pilot.error ? <p className="form-error" role="alert">{pilot.error.message}</p> : null}
        <div className="pilot-downloads">{pilot.media_url ? <a className="button light" href={pilot.media_url} download="pilot.mp4">Download MP4</a> : null}<a href={pilot.manifest_url} download="episode_manifest.json">Timeline manifest</a><a href={pilot.log_url} download="event_log.md">Event log</a></div>
        {pilot.media_url ? <video className="pilot-export-video" src={pilot.media_url} controls playsInline preload="metadata" aria-label="Exported ten-minute pilot" /> : null}
        <p className="recipe-help">The exported pilot is a draft for review. Approved poses can still differ slightly at clip entry; no fades or forced pose resets are added. Enabled rain and steam continue through holds. Music and sound ambience can be added in a later pass.</p>
      </div>
    </div> : null}
  </section>
}

function PilotTimeline({ pilot }: { pilot: Pilot }) {
  const { manifest } = pilot
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [seek, setSeek] = useState(0)
  const [error, setError] = useState('')
  const video = useRef<HTMLVideoElement>(null)
  const image = useRef<HTMLImageElement>(null)
  const current = manifest.events.find((item) => item.start_frame <= frame && frame < item.end_frame) ?? manifest.events[0]
  function go(next: number) { setFrame(Math.min(manifest.duration_frames - 1, Math.max(0, next))); setSeek((value) => value + 1) }
  function advance() {
    if (current.end_frame >= manifest.duration_frames) { setPlaying(false); go(manifest.duration_frames - 1) }
    else go(current.end_frame)
  }
  useEffect(() => {
    const element = video.current
    if (current.kind !== 'clip' || !element) return
    if (element.readyState) element.currentTime = (frame - current.start_frame) / manifest.fps
  }, [current.index, seek, manifest.fps])
  useEffect(() => {
    const element = video.current
    if (current.kind !== 'clip' || !element) return
    if (playing) void element.play().catch(() => { setPlaying(false); setError('Playback could not start. Try Play again after the clip loads.') })
    else element.pause()
  }, [playing, current.index, seek])
  useEffect(() => {
    if (!playing) return
    const started = performance.now()
    const from = frame
    let timer = 0
    const tick = () => {
      const next = current.kind === 'clip' && video.current ? current.start_frame + Math.floor(video.current.currentTime * manifest.fps) : from + Math.floor((performance.now() - started) * manifest.fps / 1000)
      if (next >= current.end_frame) {
        if (current.end_frame >= manifest.duration_frames) { setPlaying(false); setFrame(manifest.duration_frames - 1) }
        else setFrame(current.end_frame)
      } else setFrame(next)
      timer = requestAnimationFrame(tick)
    }
    timer = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(timer)
  }, [playing, current.index, seek, manifest.fps, manifest.duration_frames])
  const holdUrl = `/api/pilots/${pilot.id}/frames/${current.index}/hold`
  return <div className="panel pilot-timeline"><div className="timeline-heading"><div><h2>Timeline preview</h2><p>{clock(frame)} / {clock(manifest.duration_frames)} · {current.kind === 'hold' ? 'Holding the current frame' : current.label}</p></div><button className="button light compact" onClick={() => { setError(''); setPlaying(!playing) }}><Icon name={playing ? 'pause' : 'play'} size={16} />{playing ? 'Pause timeline' : 'Play timeline'}</button></div>
    <div className="pilot-preview-stage">{current.kind === 'hold' ? <img key={current.index} ref={image} src={holdUrl} alt="Actual current frame held on the timeline" /> : <video key={current.index} ref={video} src={`/api/candidates/${current.variant_id}/media`} muted playsInline preload="auto" aria-label={`Timeline clip: ${current.label}`} onLoadedMetadata={(event) => { event.currentTarget.currentTime = (frame - current.start_frame) / manifest.fps }} onEnded={advance} />}<AmbienceCanvas pilot={pilot} frame={frame} image={image} video={video} onError={setError} /></div>
    {manifest.ambience ? <p className="recipe-help">Continuous ambience · {manifest.ambience.layers.map((layer) => layer.label).join(' + ')} · stays on the episode clock through clips and holds. Preview rasterization may differ slightly from the final MP4.</p> : null}
    <label className="field timeline-seek">Pilot position<input aria-label="Pilot timeline position" type="range" min="0" max={manifest.duration_frames - 1} step="1" value={frame} onChange={(event) => go(Number(event.target.value))} /></label>
    <div className="timeline-ruler"><span>00:00</span><span>02:00</span><span>04:00</span><span>06:00</span><span>08:00</span><span>10:00</span></div><div className="timeline-track" aria-label="Pilot segments">{manifest.events.map((event) => <button key={event.index} className={`${event.kind} ${event.index === current.index ? 'selected' : ''}`} style={{ width: `${(event.end_frame - event.start_frame) / manifest.duration_frames * 100}%` }} title={`${clock(event.start_frame)} · ${event.label} · ${((event.end_frame - event.start_frame) / manifest.fps).toFixed(2)}s`} aria-label={`${clock(event.start_frame)} ${event.label}`} onClick={() => go(event.start_frame)} />)}</div><div className="timeline-legend"><span>● Approved motion</span><span>● Static hold</span><span>{manifest.events.filter((item) => item.kind === 'clip').length} motion events</span></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <div className="timeline-events"><table><thead><tr><th>Start</th><th>Duration</th><th>Segment</th><th>State</th></tr></thead><tbody>{manifest.events.map((event) => <tr key={event.index} className={current.index === event.index ? 'selected' : ''}><td><button className="text-button" onClick={() => go(event.start_frame)}>{clock(event.start_frame)}</button></td><td>{((event.end_frame - event.start_frame) / manifest.fps).toFixed(2)}s</td><td>{event.label}</td><td>{event.kind === 'clip' ? `${event.start_state?.replaceAll('_', ' ')} → ${event.end_state?.replaceAll('_', ' ')}` : 'Current exit frame'}</td></tr>)}</tbody></table></div>
    <details className="provenance"><summary>Join diagnostics and provenance</summary><p>Base hold frames are exact before ambience and encoding. Clip-entry differences below are measured on decoded source frames and remain a visual review item.</p>{manifest.joins.map((join, index) => <p key={index}>{clock(join.at_frame)} · {manifest.clips.find((clip) => clip.id === join.candidate_id)?.label} · mean RGB difference {join.whole_frame_mean_absolute_rgb_0_255.toFixed(3)}/255</p>)}<p>Manifest SHA-256: <code>{manifest.manifest_hash}</code></p></details>
  </div>
}
