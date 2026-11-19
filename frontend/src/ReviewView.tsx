import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import Icon from './Icon'
import type { Candidate, ReviewStatus, StudioState } from './types'

function ClipPlayer({ candidate }: { candidate: Candidate }) {
  const [playing, setPlaying] = useState(true)
  const [replay, setReplay] = useState(0)
  const [mode, setMode] = useState<'loop' | 'holds'>('loop')
  const [phase, setPhase] = useState<'start' | 'motion' | 'end'>('start')
  const video = useRef<HTMLVideoElement>(null)
  const properties = candidate.metadata.outputs[0].properties
  const mp4 = properties.container === 'mp4'
  useEffect(() => { setPlaying(true); setReplay(0) }, [candidate.id])
  useEffect(() => {
    if (!video.current) return
    if (!playing) { video.current.pause(); return }
    if (mode === 'holds' && phase !== 'motion') {
      video.current.pause()
      if (phase === 'start') video.current.currentTime = 0
      const timer = window.setTimeout(() => setPhase(phase === 'start' ? 'motion' : 'start'), 1000)
      return () => window.clearTimeout(timer)
    }
    void video.current.play().catch(() => setPlaying(false))
  }, [playing, mode, phase, replay, candidate.id])
  function chooseMode(next: 'loop' | 'holds') {
    setMode(next); setPhase('start'); setReplay((count) => count + 1); setPlaying(true)
    if (video.current) video.current.currentTime = 0
  }
  return <div className="clip-player">{mp4 ? <div className="hold-preview-controls"><button aria-pressed={mode === 'loop'} onClick={() => chooseMode('loop')}>Loop</button><button aria-pressed={mode === 'holds'} onClick={() => chooseMode('holds')}>With static holds</button><span>{mode === 'holds' ? phase === 'start' ? 'First frame · 1s hold' : phase === 'end' ? 'Last frame · 1s hold' : 'Playing motion' : 'Loop preview'}</span></div> : null}<div className="player-image">{mp4 ? <video ref={video} src={candidate.media_url} poster={candidate.frames.start} loop={mode === 'loop'} onEnded={() => { if (mode === 'holds') setPhase('end') }} muted playsInline preload="auto" aria-label={`${candidate.label} animation`} /> : <img src={playing ? `${candidate.media_url}?play=${replay}` : candidate.frames.start} alt={`${candidate.label} ${playing ? 'animation' : 'paused first frame'}`} />}</div><div className="player-controls"><button className="icon-button" aria-label={playing ? 'Pause animation' : 'Play animation'} onClick={() => setPlaying(!playing)}><Icon name={playing ? 'pause' : 'play'} size={17} /></button><button className="icon-button" aria-label="Replay animation" onClick={() => { if (video.current) video.current.currentTime = 0; setPhase('start'); setReplay((count) => count + 1); setPlaying(true) }}><Icon name="refresh" size={15} /></button><span>{properties.duration_seconds.toFixed(2)}s</span><div className={`playback-line ${playing ? 'playing' : ''}`} /><span>{properties.frame_count} frames</span><span className="loop-label">{mode === 'holds' ? 'ENDPOINT HOLDS' : 'LOOP PREVIEW'}</span></div></div>
}

function EarlierTakeComparison({ candidate, reference }: { candidate: Candidate; reference: Candidate }) {
  const currentVideo = useRef<HTMLVideoElement>(null)
  const referenceVideo = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')
  const bothMp4 = [candidate, reference].every((item) => item.metadata.outputs[0].properties.container === 'mp4')
  function pause() {
    currentVideo.current?.pause(); referenceVideo.current?.pause(); setPlaying(false)
  }
  async function play(restart: boolean) {
    const videos = [currentVideo.current, referenceVideo.current].filter((item): item is HTMLVideoElement => item !== null)
    if (videos.length !== 2) return
    setError('')
    try {
      if (restart) videos.forEach((item) => { item.currentTime = 0 })
      await Promise.all(videos.map((item) => item.play()))
      setPlaying(true)
    } catch { pause(); setError('Playback could not start. Wait for the clips to load and try again.') }
  }
  return <div className="earlier-comparison">
    <div className="earlier-comparison-grid">{[candidate, reference].map((item, index) => <div className="earlier-take" key={item.id}><div className="comparison-caption"><strong>{index === 0 ? 'NEW CANDIDATE' : 'EARLIER TAKE'}</strong><span>{item.label}</span></div>{bothMp4 ? <video ref={index === 0 ? currentVideo : referenceVideo} src={item.media_url} poster={item.frames.start} muted playsInline preload="auto" onEnded={pause} aria-label={`${index === 0 ? 'New' : 'Earlier'} take: ${item.label}`} /> : <ClipPlayer candidate={item} />}<p>{item.metadata.outputs[0].properties.frame_count} frames · {item.metadata.outputs[0].properties.duration_seconds.toFixed(2)}s · {index === 1 ? 'Historical approval retained' : 'Awaiting your visual comparison'}</p></div>)}</div>
    {bothMp4 ? <div className="comparison-controls"><button className="button compact" onClick={() => playing ? pause() : void play(false)}><Icon name={playing ? 'pause' : 'play'} size={16} />{playing ? 'Pause both' : 'Play both'}</button><button className="button compact" onClick={() => void play(true)}><Icon name="refresh" size={15} />Replay both from start</button><span>Shared controls · muted playback</span></div> : null}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <p className="comparison-note">Compare the action, silhouette, palette and start/end poses. Shared playback is a visual aid; approval still requires checking the boundary frames.</p>
  </div>
}

export default function ReviewView({ data, preferredId, refresh, notify, onBack }: { data: StudioState; preferredId: string; refresh: () => Promise<void>; notify: (text: string) => void; onBack?: () => void }) {
  const focused = !!preferredId && !!onBack
  const [filter, setFilter] = useState<ReviewStatus | 'all'>('all')
  const [selected, setSelected] = useState(preferredId)
  const [compare, setCompare] = useState<'preview' | 'master' | 'earlier'>('preview')
  const [notes, setNotes] = useState('')
  const [entry, setEntry] = useState('Start of take')
  const [exit, setExit] = useState('End of take')
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const visible = data.candidates.filter((candidate) => filter === 'all' || candidate.status === filter)
  const candidate = visible.find((item) => item.id === selected) ?? visible[0]
  const scene = data.scenes.find((item) => item.id === candidate?.scene_id)
  const motion = candidate?.metadata.motion
  const vaeName = motion?.vae_name ?? String(candidate?.metadata.parameters.vae_name ?? '')
  const reference = data.candidates.find((item) => item.id === motion?.reference_candidate_id)
  const pendingComparisons = data.candidates.filter((item) => item.status === 'candidate' && data.candidates.some((earlier) => earlier.id === item.metadata.motion?.reference_candidate_id && earlier.status === 'approved')).length
  const profile = data.motion_profiles?.find((item) => item.id === motion?.profile_id)
  useEffect(() => { setSelected(preferredId); setFilter('all') }, [preferredId])
  useEffect(() => {
    const previous = candidate?.reviews.at(-1)
    setNotes(previous?.notes ?? ''); setEntry(previous?.entry_anchor || motion?.start_state || 'Start of take'); setExit(previous?.exit_anchor || motion?.end_state || 'End of take')
    setChecked(false); setError('')
  }, [candidate?.id, candidate?.version, motion?.start_state, motion?.end_state])
  useEffect(() => { setCompare(reference ? 'earlier' : 'preview') }, [candidate?.id, reference?.id])
  async function decide(decision: 'approved' | 'rejected') {
    if (!candidate) return
    if (decision === 'rejected' && !notes.trim()) { setError('Add a short reason for rejecting this take.'); return }
    setBusy(true); setError('')
    try {
      await api(`candidates/${candidate.id}/review`, { decision, notes, entry_anchor: entry, exit_anchor: exit, visual_checked: checked, expected_version: candidate.version, request_id: crypto.randomUUID() })
      await refresh(); notify(decision === 'approved' ? 'Clip approved. A verified copy is saved in your motion library.' : 'Clip rejected. Your take and review notes are preserved.')
    } catch (error) { setError(error instanceof Error ? error.message : 'The review could not be saved.') }
    finally { setBusy(false) }
  }
  return <section className={`page ${focused ? 'focused-review' : ''}`}>
    <div className="page-heading"><div><p className="eyebrow">REVIEW A TAKE</p><h1>{focused ? candidate?.label ?? 'Review take' : 'Keep what feels alive.'}</h1><p>{focused ? 'Watch the motion and compare the still before keeping this take.' : 'A careful look now makes a believable world later.'}</p></div>{focused ? <button className="text-button" onClick={onBack}>Back to motion</button> : <span className="review-total">{data.candidates.filter((item) => item.status === 'candidate').length} awaiting review</span>}</div>
    {!focused ? <><div className="filter-tabs" aria-label="Filter candidates">{(['all', 'candidate', 'approved', 'rejected'] as const).map((item) => <button key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)} aria-pressed={filter === item}>{item === 'all' ? 'All takes' : item === 'candidate' ? 'Needs review' : item === 'approved' ? 'Approved' : 'Rejected'}<span>{data.candidates.filter((candidate) => item === 'all' || candidate.status === item).length}</span></button>)}</div>
    {pendingComparisons ? <p className="comparison-note">{pendingComparisons} pending takes have earlier approved versions. They remain separate for comparison; pending takes are excluded from pilots.</p> : null}</> : null}
    {!candidate ? <div className="empty-state small"><Icon name="review" size={35} /><h2>No takes in this view.</h2><p>Generate a motion clip, or choose another filter.</p></div> : <>
      {!focused ? <div className="take-strip">{visible.map((item) => <button className={`take-option ${candidate.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setSelected(item.id)}><img src={item.frames.start} alt="" /><span>{item.label}<small>{data.scenes.find((scene) => scene.id === item.scene_id)?.title}</small></span><span className={`mini-status ${item.status}`} /></button>)}</div> : null}
      <div className="studio-grid"><div className="review-workspace">
        <div className="review-title"><div><h2>{candidate.label}</h2><span>{scene?.title}</span></div><span className={`badge ${candidate.status}`}>{candidate.status === 'candidate' ? 'Needs review' : candidate.status}</span></div>
        {reference?.status === 'approved' ? <p className="comparison-note">Alternate take of <strong>{reference.label}</strong>. The earlier version is already approved and available to the pilot builder.</p> : null}
        <div className="view-toggle"><button className={compare === 'preview' ? 'selected' : ''} onClick={() => setCompare('preview')}>Motion preview</button><button className={compare === 'master' ? 'selected' : ''} onClick={() => setCompare('master')}>Compare with master</button>{reference ? <button className={compare === 'earlier' ? 'selected' : ''} onClick={() => setCompare('earlier')}>Compare with earlier take</button> : null}</div>
        {compare === 'earlier' && reference ? <EarlierTakeComparison key={`${candidate.id}-${reference.id}`} candidate={candidate} reference={reference} /> : <div className={compare === 'master' ? 'compare-grid' : ''}>{compare === 'master' && scene ? <div className="compare-source"><span>MASTER STILL</span><img src={scene.image_url} alt={`${scene.title} unchanged master`} /></div> : null}<ClipPlayer key={candidate.id} candidate={candidate} /></div>}
        {motion ? <div className="review-motion-context"><span>{motion.actor}</span><strong>{motion.start_state.replaceAll('_', ' ')} → {motion.end_state.replaceAll('_', ' ')}</strong><span>{motion.crop.width} × {motion.crop.height} crop · masked composite</span>{vaeName ? <span>{vaeName.toLowerCase().includes('int8') ? 'INT8 VAE variant' : 'FP16 VAE'}</span> : null}</div> : null}
        <div className="frame-samples">{(['start', 'middle', 'end'] as const).map((key) => <figure key={key}><img src={candidate.frames[key]} alt={`${key} frame of ${candidate.label}`} /><figcaption>{key === 'start' ? 'First frame' : key === 'middle' ? 'Midpoint' : 'Last frame'}</figcaption></figure>)}</div>
        {motion ? <p className="comparison-note">Lossless assembled frames; MP4 playback uses lossy H.264 encoding.</p> : null}
        {profile ? <details className="motion-reference-details"><summary>Conditioning poses and compositing mask</summary><div className="motion-pose-grid"><figure><img src={profile.first_url} alt="First conditioning pose" /><figcaption>First pose</figcaption></figure><figure><img src={profile.last_url} alt="Last conditioning pose" /><figcaption>Last pose</figcaption></figure><figure className="motion-mask"><img src={profile.mask_url} alt="Protected actor compositing mask" /><figcaption>Feathered mask</figcaption></figure></div>{candidate.crop_url ? <a className="text-button" href={candidate.crop_url} target="_blank" rel="noreferrer">Open raw actor crop<Icon name="arrow" size={14} /></a> : null}</details> : null}
        <details className="provenance"><summary>Generation & review history</summary><div className="provenance-details"><p>Seed: {String(candidate.metadata.parameters.seed)} · {candidate.metadata.outputs[0].properties.width} × {candidate.metadata.outputs[0].properties.height} · {candidate.metadata.outputs[0].properties.effective_fps.toFixed(2)} encoded fps</p><p>Prompt: {String(candidate.metadata.parameters.motion_prompt)}</p><p>Workflow SHA-256: <code>{candidate.metadata.workflow_sha256}</code></p>{motion ? <><p>Motion profile: {motion.profile_id} · actor: {motion.actor} · crop: x {motion.crop.x}, y {motion.crop.y}, {motion.crop.width} × {motion.crop.height}</p><p>State: {motion.start_state} → {motion.end_state}</p><p>Mask SHA-256: <code>{motion.mask_sha256 ?? motion.mask?.sha256}</code></p>{vaeName ? <p>Video VAE: {vaeName}</p> : null}{motion.compositing_policy ? <p>Compositing policy: {motion.compositing_policy}</p> : null}{motion.composite_policy ? <p>Compositing: mask assembly restored from saved assets; historical color handling inferred from the reference clip.</p> : null}</> : null}{candidate.metadata.legacy ? <p>Imported history from the earlier library. Previous decisions are retained as recorded.</p> : null}{candidate.reviews.map((review) => <div className="review-history" key={review.version}><strong>{review.decision} · revision {review.version}</strong><span>{new Date(review.created).toLocaleString()}</span><p>{review.notes || 'No additional notes.'}</p></div>)}</div></details>
      </div><aside className="inspector review-inspector">
        <div className="panel-title"><h2>Your review</h2><Icon name="review" size={18} /></div><p className="muted description">Look for identity drift, moving architecture, prop changes, and jumps at the ends.</p><label className="field">Review notes<textarea rows={4} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What works? What needs another take?" /></label><div className="rule" /><h3>Continuity anchors</h3><p className="field-help">Name the starting and ending poses. They can differ for an action or transition.</p><label className="field">Start anchor<input value={entry} onChange={(event) => setEntry(event.target.value)} maxLength={200} /></label><label className="field">End anchor<input value={exit} onChange={(event) => setExit(event.target.value)} maxLength={200} /></label><label className="check-field"><input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} /><span>I checked this take against the master and reviewed its start and end.</span></label>{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="button approve full" disabled={busy || !checked || !entry.trim() || !exit.trim() || candidate.status === 'approved'} onClick={() => void decide('approved')}><Icon name="check" size={17} />{busy ? 'Saving review…' : candidate.status === 'approved' ? 'Approved' : 'Approve clip'}</button><button className="button reject full" disabled={busy || candidate.status === 'rejected'} onClick={() => void decide('rejected')}><Icon name="close" size={16} />Reject clip</button><p className="review-assurance">Review decisions are saved with their history. Original takes are always retained.</p>
      </aside></div>
    </>}
  </section>
}
