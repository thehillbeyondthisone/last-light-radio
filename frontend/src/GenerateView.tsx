import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import Icon from './Icon'
import AdjustMotionArea from './AdjustMotionArea'
import type { Candidate, Job, MotionProfile, Scene, StudioState } from './types'

const defaultPrompt = 'Add gentle idle motion, then return to the starting pose. Keep the camera, identity, props, lighting and room unchanged.'
const activeStatuses = new Set(['pending', 'submitting', 'queued', 'running', 'unknown'])
const statusNames: Record<string, string> = { pending: 'Waiting to submit', submitting: 'Sending to worker', queued: 'Queued', running: 'Generating', success: 'Ready to review', failed: 'Needs attention', submission_unknown: 'Submission needs checking', unknown: 'Waiting for worker history' }
type Props = { data: StudioState; scene?: Scene; preferredProfileId?: string; onSetup: () => void; onScene: (id: string) => void; refresh: () => Promise<void>; notify: (text: string) => void; onReview: (id: string) => void; onWorker: () => void }

export default function GenerateView(props: Props) {
  return <MotionWorkspace key={`${props.scene?.id ?? 'empty'}:${props.preferredProfileId ?? ''}`} {...props} />
}

function MotionWorkspace({ data, scene, preferredProfileId, onSetup, onScene, refresh, notify, onReview, onWorker }: Props) {
  const sceneProfiles = (data.motion_profiles ?? []).filter((item) => item.scene_id === scene?.id)
  const profiles = sceneProfiles.filter((item) => item.id === preferredProfileId || !sceneProfiles.some((next) => next.parent_id === item.id))
  const initialProfile = profiles.find((item) => item.id === preferredProfileId) ?? profiles.filter((item) => item.origin === 'authored').at(-1) ?? profiles[0]
  const [profileId, setProfileId] = useState(initialProfile?.id ?? '')
  const profile = profiles.find((item) => item.id === profileId)
  const [label, setLabel] = useState(initialProfile?.name ?? 'Gentle idle')
  const [prompt, setPrompt] = useState(initialProfile?.prompt ?? defaultPrompt)
  const [seed, setSeed] = useState(String(initialProfile?.seed ?? 7))
  const [repeatSeed, setRepeatSeed] = useState(false)
  const [areaTake, setAreaTake] = useState<Candidate | null>(null)
  const originalVae = data.production?.original_vae_name ?? 'minimax_h3_video_vae_fp16.safetensors'
  const [vaeName, setVaeName] = useState(initialProfile?.vae_name ?? data.production?.default_vae_name ?? originalVae)
  const [selectedTake, setSelectedTake] = useState('')
  const [comparison, setComparison] = useState<'take' | 'still' | 'region'>('take')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [mediaError, setMediaError] = useState('')
  const request = useRef<{ id: string; fingerprint: string; seed: number } | null>(null)
  const takes = data.candidates.filter((item) => item.scene_id === scene?.id && (profile ? item.metadata.motion?.profile_id === profile.id : !item.metadata.motion))
  const take = takes.find((item) => item.id === selectedTake) ?? takes[0]
  const jobs = data.jobs.filter((item) => item.scene_id === scene?.id && (profile ? item.motion_profile_id === profile.id : !item.motion_profile_id))
  const generating = jobs.some((item) => activeStatuses.has(item.status))
  const vaeOptions = Array.from(new Set([originalVae, 'minimax_h3_video_vae_int8_convrot.safetensors', vaeName]))
  const duration = profile ? profile.frames / profile.fps : Number(data.workflow.parameters.frames) / Number(data.workflow.parameters.fps)
  const showTake = comparison === 'take' && !!take

  function chooseProfile(next?: MotionProfile) {
    setProfileId(next?.id ?? ''); setLabel(next?.name ?? 'Gentle idle')
    setPrompt(next?.prompt ?? defaultPrompt); setSeed(String(next?.seed ?? 7))
    setVaeName(next?.vae_name ?? data.production?.default_vae_name ?? originalVae)
    setSelectedTake(''); setComparison('take'); setError(''); setMediaError(''); setRepeatSeed(false)
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!scene || busy || generating) return
    setBusy(true); setError('')
    try {
      const body = { scene_id: scene.id, label, prompt, ...(profile ? { motion_profile_id: profile.id, motion_vae_name: vaeName } : {}) }
      const fingerprint = JSON.stringify({ ...body, seed, repeatSeed })
      if (request.current?.fingerprint !== fingerprint) request.current = { id: crypto.randomUUID(), fingerprint, seed: takes.length && !repeatSeed ? crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff : Number(seed) }
      await api<Job>('generate', { ...body, seed: request.current.seed, request_id: request.current.id })
      request.current = null
      setSelectedTake(''); setComparison('take')
      await refresh(); notify('Take requested. It will appear here when it is ready.')
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not request this take.') }
    finally { setBusy(false) }
  }
  async function resume(job: Job) {
    try { await api(`jobs/${job.id}/resume`, {}); await refresh(); notify('Checking the existing render.') }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not resume this render.') }
  }
  const areaProfile = sceneProfiles.find((item) => item.id === areaTake?.metadata.motion?.profile_id)
  if (areaTake && areaProfile && scene) return <AdjustMotionArea key={areaTake.id} candidate={areaTake} profile={areaProfile} scene={scene} onCancel={() => setAreaTake(null)} onSaved={async (result) => {
    await refresh(); setProfileId(result.metadata.motion!.profile_id); setSelectedTake(result.id); setComparison('take'); setAreaTake(null); setMediaError(''); window.scrollTo({ top: 0, behavior: 'auto' }); notify('Motion area updated using the saved take. Review the new version here.')
  }} />
  return <section className="page motion-workspace">
    <div className="page-heading"><div><p className="eyebrow">MAKE A MOTION</p><h1>{label || 'A little movement.'}</h1><p>Choose a motion, make a take, then watch it in the scene.</p></div><button className="text-button" onClick={onSetup}><Icon name="plus" size={16} />New motion</button></div>
    <div className="motion-toolbar">
      <label className="field">Scene<select value={scene?.id ?? ''} onChange={(event) => onScene(event.target.value)}>{!scene ? <option value="">Import a scene first</option> : null}{data.scenes.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label className="field">Motion<select value={profile?.id ?? ''} onChange={(event) => chooseProfile(profiles.find((item) => item.id === event.target.value))}>{profiles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}<option value="">Full-scene technical test</option></select></label>
      <span className="motion-duration">{duration.toFixed(2)} seconds</span>
    </div>
    <div className="motion-preview-bar"><span>{showTake ? take.label : comparison === 'region' ? 'Highlighted area may move' : 'Original scene'}</span><div className="motion-compare" aria-label="Preview display"><button aria-pressed={comparison === 'take'} disabled={!take} onClick={() => { setComparison('take'); setMediaError('') }}>Take</button><button aria-pressed={comparison === 'still'} onClick={() => setComparison('still')}>Still</button>{profile ? <button aria-pressed={comparison === 'region'} onClick={() => setComparison('region')}>Motion area</button> : null}</div></div>
    <div className="motion-stage">
      {showTake ? take.metadata.outputs[0].properties.container === 'mp4'
        ? <video key={take.id} src={take.media_url} poster={take.frames.start} controls loop muted playsInline preload="metadata" aria-label={take.label} onError={() => setMediaError('This take could not be played. Open review or check the saved media.')} />
        : <img src={take.media_url} alt={take.label} />
        : scene ? <div className="motion-still"><img src={scene.image_url} alt={scene.title} />{comparison === 'region' && profile ? <div className="motion-region-overlay" style={{ maskImage: `url("${profile.mask_url}")` }} /> : null}</div> : <p>Import a scene to begin.</p>}
    </div>
    {mediaError ? <p className="form-error" role="alert">{mediaError}</p> : null}
    <div className="motion-below-preview"><p>{profile ? <>{profile.start_state.replaceAll('_', ' ')}<Icon name="arrow" size={13} />{profile.name}<Icon name="arrow" size={13} />{profile.end_state.replaceAll('_', ' ')}</> : 'Full-scene technical test'}{take && showTake ? <span className={`badge ${take.status}`}>{take.status === 'candidate' ? 'Needs review' : take.status}</span> : null}</p>{take ? <div className="motion-take-actions">{take.can_adjust_area ? <button className="text-button" onClick={() => setAreaTake(take)}>Adjust motion area</button> : null}<button className="button light compact" onClick={() => onReview(take.id)}>Review this take<Icon name="arrow" size={14} /></button></div> : <span className="muted">Your first take will appear here.</span>}</div>
    <form className="motion-direction panel" onSubmit={(event) => void submit(event)}>
      <div className="motion-request-row"><p>{profile ? 'Ready to try this motion. Each new take stays here for review.' : 'This technical test can change the entire picture.'}</p><button className="button dark" disabled={busy || generating || !scene || !data.workflow.confirmed}><Icon name="spark" size={16} />{busy ? 'Requesting…' : generating ? 'Making your take…' : takes.length ? 'Make another take' : 'Make a take'}</button></div>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <details className="motion-settings"><summary>Take settings</summary>
        <label className="field">Motion direction<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} required maxLength={4000} /></label>
        <div className="recipe-form-row"><label className="field">Motion name<input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={100} required /></label><label className="field">Variation seed<input type="number" value={seed} min="0" max="2147483647" step="1" required onChange={(event) => { setSeed(event.target.value); setRepeatSeed(true) }} /></label></div>
        <label className="check-field"><input type="checkbox" checked={repeatSeed} onChange={(event) => setRepeatSeed(event.target.checked)} /><span>Repeat this seed. Otherwise another take uses a fresh variation.</span></label>
        <button type="button" className="text-button" onClick={() => { setSeed(String(crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff)); setRepeatSeed(true) }}>Choose a different variation</button>
        {profile ? <><label className="field">Video model variant<select value={vaeName} onChange={(event) => setVaeName(event.target.value)}>{vaeOptions.map((name) => <option key={name} value={name}>{name}{data.production && !data.production.available_vae_names.includes(name) ? ' · unavailable' : ''}</option>)}</select></label><p className="field-help">Saved with each take. A missing model blocks generation.</p><div className="motion-pose-grid"><figure><img src={profile.first_url} alt="Starting pose" /><figcaption>Start</figcaption></figure><figure><img src={profile.last_url} alt="Ending pose" /><figcaption>Return</figcaption></figure><figure><img src={profile.mask_url} alt="Saved motion mask" /><figcaption>Motion area</figcaption></figure></div></> : null}
        <p className="field-help">{data.workflow.name} · {profile ? `${profile.frames} frames · ${profile.fps} fps` : 'Small full-scene test'} · New takes need your review.</p>
        <button type="button" className="text-button" onClick={onWorker}>Worker settings<Icon name="settings" size={14} /></button>
      </details>
    </form>
    {jobs.some((job) => job.status !== 'success') ? <div className="motion-job-status" aria-live="polite">{jobs.filter((job) => job.status !== 'success').map((job) => <div className="job-row" key={job.id}><div className="job-description"><strong>{job.label}</strong><span>{statusNames[job.status] ?? job.status}{job.error ? ` · ${job.error.message}` : ''}</span></div>{job.can_resume && !activeStatuses.has(job.status) ? <button className="text-button" onClick={() => void resume(job)}>Check existing render</button> : null}</div>)}</div> : null}
    {takes.length ? <div className="motion-takes"><div className="section-heading"><h2>Takes <span className="subtle-count">{takes.length}</span></h2></div><div className="motion-take-strip">{takes.map((item) => <button key={item.id} className={`motion-take ${take?.id === item.id ? 'selected' : ''}`} aria-pressed={take?.id === item.id} onClick={() => { setSelectedTake(item.id); setComparison('take'); setMediaError('') }}><img src={item.frames.middle} alt="" /><span>{item.label}</span><small>{item.status === 'candidate' ? 'Needs review' : item.status}</small></button>)}</div></div> : null}
  </section>
}
