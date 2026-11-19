import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import Icon from './Icon'
import MaskPainter from './MaskPainter'
import RecipeWizard from './RecipeWizard'
import type { Job, MotionProfile, Scene, StudioState } from './types'

type Props = { data: StudioState; scene?: Scene; editing?: MotionProfile; actionOnly?: boolean; idleOnly?: boolean; initialActor?: string; onScene: (id: string) => void; onImport: () => void; onCancel: () => void; refresh: () => Promise<void>; onSaved: (profile: MotionProfile, generating?: boolean) => void }
type Preview = { images: { overlay: string }; crop: { width: number; height: number } }

export default function MotionGuide(props: Props) {
  return <Guide key={`${props.scene?.id}:${props.editing?.id ?? 'new'}:${props.actionOnly ? 'action' : props.idleOnly ? 'idle' : 'motion'}:${props.initialActor ?? ''}`} {...props} />
}

function Guide(props: Props) {
  const { data, scene, editing, onCancel, onSaved, refresh, actionOnly, idleOnly } = props
  const [advanced, setAdvanced] = useState(false)
  const sceneProfiles = (data.motion_profiles ?? []).filter((item) => item.scene_id === scene?.id)
  const actorNames = Array.from(new Set(sceneProfiles.map(item => item.actor.trim()).filter(Boolean))).sort().filter((name, index, names) => names.findIndex(item => item.toLowerCase() === name.toLowerCase()) === index)
  const [step, setStep] = useState(0)
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'auto' }) }, [step])
  const [actor, setActor] = useState(editing?.actor ?? props.initialActor ?? sceneProfiles.filter((item) => item.origin === 'authored').at(-1)?.actor ?? sceneProfiles[0]?.actor ?? '')
  const [starterId, setStarterId] = useState(idleOnly ? 'idle' : actionOnly && editing?.creative_direction?.starter_id === 'idle' ? 'custom' : editing?.creative_direction?.starter_id ?? 'custom')
  const [description, setDescription] = useState(editing?.creative_direction?.description ?? (idleOnly ? data.motion_starters?.find((item) => item.id === 'idle')?.direction ?? '' : ''))
  const [name, setName] = useState(editing?.name ?? '')
  const [mask, setMask] = useState('')
  const [areaId, setAreaId] = useState(editing?.id ?? sceneProfiles.filter((item) => item.actor.toLowerCase() === actor.trim().toLowerCase()).at(-1)?.id ?? '')
  const [frames, setFrames] = useState(editing?.frames ?? (idleOnly ? 90 : 124))
  const [seed, setSeed] = useState(String(editing?.seed ?? (crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff)))
  const [vae, setVae] = useState(editing?.vae_name ?? data.production?.default_vae_name ?? '')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [requestingTake, setRequestingTake] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<{ fingerprint: string; id: string } | null>(null)
  const saving = useRef(false)
  const starter = data.motion_starters?.find((item) => item.id === starterId)
  const matching = sceneProfiles.filter((item) => !sceneProfiles.some((next) => next.parent_id === item.id))
  const sourceArea = sceneProfiles.find((item) => item.id === areaId)
  const state = editing?.start_state ?? sceneProfiles.find((item) => item.actor.toLowerCase() === actor.trim().toLowerCase() && item.first_scene_id === scene?.id)?.start_state ?? 'resting'
  const title = name.trim() || (starterId === 'custom' ? `${actor.trim() || 'Subject'} · new motion` : starter?.name ?? 'New motion')
  const canonicalActor = editing?.actor ?? actorNames.find(name => name.toLowerCase() === actor.trim().toLowerCase()) ?? actor.trim()
  const body = { scene_id: scene?.id, actor: canonicalActor, name: title, template_id: actionOnly ? 'action' : idleOnly ? 'idle' : starter?.template_id ?? 'action',
    first_scene_id: scene?.id, last_scene_id: scene?.id, start_state: state, end_state: state,
    creative_direction: { starter_id: starterId, description }, mask_base64: mask, feather: 4, context: 0.12,
    frames, seed: Number(seed), vae_name: vae, ...(editing ? { parent_id: editing.id } : {}) }

  function chooseStarter(id: string) {
    const next = data.motion_starters?.find((item) => item.id === id)
    setStarterId(id); setDescription(next?.direction ?? ''); setFrames(next?.frames ?? 124); setPreview(null); setError('')
  }
  async function next() {
    setError('')
    if (!actor.trim() || !description.trim()) { setError('Name the subject and describe what happens.'); return }
    if (step === 0) { setStep(1); return }
    setBusy(true)
    try { const result = await api<Preview>('motion/preview', body); setPreview(result); setStep(2) }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'The motion area could not be prepared.') }
    finally { setBusy(false) }
  }
  async function save(generate: boolean) {
    if (saving.current) return
    saving.current = true; setBusy(true); setRequestingTake(generate); setError('')
    try {
      const fingerprint = JSON.stringify(body)
      if (request.current?.fingerprint !== fingerprint) request.current = { fingerprint, id: crypto.randomUUID() }
      const profile = await api<MotionProfile>('motion/recipes', body)
      if (generate) await api<Job>('generate', { scene_id: profile.scene_id, motion_profile_id: profile.id,
        motion_vae_name: profile.vae_name, label: profile.name, prompt: profile.prompt, seed: profile.seed, request_id: request.current.id })
      await refresh(); onSaved(profile, generate)
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not save this motion.'); saving.current = false; setBusy(false) }
  }
  if (!actionOnly && !idleOnly && (advanced || (editing && !editing.creative_direction && !editing.mask_edit))) return <RecipeWizard {...props} />
  if (!scene) return <section className="empty-state"><h1>Choose a scene first.</h1><button className="button dark" onClick={props.onImport}>Import a scene</button></section>
  return <section className="page motion-guide">
    <div className="page-heading"><div><p className="eyebrow">{actionOnly ? 'CREATE ACTION' : idleOnly ? 'SUBJECT IDLE' : 'NEW MOTION'}</p><h1>{['What should happen?', 'Give the motion room.', 'Ready for a first take.'][step]}</h1><p>{['Start with an idea. We’ll take care of the rendering instructions.', 'Include the subject, handled objects and the path they travel.', 'The action returns to its starting pose. You’ll review the result before keeping it.'][step]}</p></div><button className="text-button" disabled={busy} onClick={onCancel}>{actionOnly || idleOnly ? 'Back to Viewer' : 'Back to scene'}</button></div>
    <ol className="guide-progress" aria-label="Motion creation steps">{['Describe', 'Mark area', 'Make a take'].map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}><span>{index + 1}</span>{label}</li>)}</ol>
    {step === 0 ? <div className="panel guide-card">
      <div className="motion-starters" aria-label="Motion starting points">{(data.motion_starters ?? []).filter((item) => actionOnly ? item.template_id !== 'idle' : idleOnly ? item.template_id === 'idle' : true).map((item) => <button key={item.id} type="button" aria-pressed={starterId === item.id} onClick={() => chooseStarter(item.id)}>{item.name}</button>)}</div>
      <label className="field">Who moves?<input value={actor} onChange={(event) => { const next = event.target.value; setActor(next); setAreaId(sceneProfiles.filter((item) => item.actor.toLowerCase() === next.trim().toLowerCase()).at(-1)?.id ?? ''); setMask('') }} maxLength={100} placeholder="e.g. Reader, sleeping cat, curtain" list="scene-actors" /><datalist id="scene-actors">{actorNames.map((item) => <option key={item} value={item} />)}</datalist></label>
      <label className="field">What happens?<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={4} placeholder="She takes a sip from the mug and returns to reading." /></label>
      <p className="field-help">{starter?.hint || 'One complete action works best. Describe what moves and how it finishes.'}</p>
      <details className="guide-advanced"><summary>More options</summary><label className="field">Motion name<input value={name} onChange={(event) => setName(event.target.value)} placeholder={title} maxLength={100} /></label><label className="field">Take length<select value={frames} onChange={(event) => setFrames(Number(event.target.value))}><option value={39}>Brief · 1.6 seconds</option><option value={90}>Small movement · 3.75 seconds</option><option value={124}>Complete action · 5.17 seconds</option></select></label><div className="recipe-form-row"><label className="field">Variation seed<input value={seed} onChange={(event) => setSeed(event.target.value)} type="number" min="0" max="2147483647" /></label><label className="field">Model variant<select value={vae} onChange={(event) => setVae(event.target.value)}>{Array.from(new Set([vae, data.production?.original_vae_name ?? '', 'minimax_h3_video_vae_int8_convrot.safetensors'])).filter(Boolean).map((item) => <option key={item} value={item}>{item}{data.production?.available_vae_names.includes(item) ? '' : ' · unavailable'}</option>)}</select></label></div>{!actionOnly && !idleOnly ? <button className="text-button" onClick={() => setAdvanced(true)}>Set up a different ending pose</button> : null}</details>
    </div> : null}
    {step === 1 ? <div className="panel guide-card"><div className="guide-area-heading"><p>{starter?.hint || 'Mark all the space needed for this action.'}</p><label className="field">Start from<select value={areaId} onChange={(event) => { setAreaId(event.target.value); setMask('') }}><option value="">An empty area</option>{matching.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></div><MaskPainter key={areaId} scene={scene} initialMaskUrl={sourceArea?.mask_url} onChange={setMask} /></div> : null}
    {step === 2 && preview ? <div className="panel guide-card"><figure className="guide-preview"><img src={preview.images.overlay} alt="Motion preview: original colors may move; pale areas remain protected" /><figcaption>Original colors may move. Pale areas stay protected.</figcaption></figure><div className="guide-recap"><div><h2>{title}</h2><p>{description}</p></div><span>{(frames / 24).toFixed(2)} seconds</span></div></div> : null}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <div className="guide-footer"><button className="button light" disabled={busy} onClick={() => step ? setStep(step - 1) : onCancel()}>{step ? 'Back' : 'Cancel'}</button><div>{step === 2 ? <><button className="text-button" disabled={busy} onClick={() => void save(false)}>{busy && !requestingTake ? 'Saving motion…' : 'Save for later'}</button><button className="button dark" disabled={busy || !data.workflow.confirmed} onClick={() => void save(true)}><Icon name="spark" size={16} />{busy && requestingTake ? 'Preparing your take…' : 'Make first take'}</button></> : <button className="button dark" disabled={busy || (step === 1 && !mask)} onClick={() => void next()}>{busy ? 'Preparing preview…' : step === 0 ? 'Mark the motion area' : 'Preview motion setup'}<Icon name="arrow" size={16} /></button>}</div></div>
  </section>
}
