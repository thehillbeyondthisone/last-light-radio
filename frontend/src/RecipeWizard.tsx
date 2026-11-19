import { useId, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { api, encodeFile } from './api'
import Icon from './Icon'
import type { MotionProfile, Scene, StudioState } from './types'

type Point = [number, number]
type Preview = { crop: { x: number; y: number; width: number; height: number }; output_size: number[]; images: Record<'overlay' | 'mask' | 'first' | 'last', string> }
type Props = { data: StudioState; scene?: Scene; editing?: MotionProfile; onScene: (id: string) => void; onImport: () => void; onCancel: () => void; refresh: () => Promise<void>; onSaved: (profile: MotionProfile) => void }
const steps = ['Select a region', 'Choose the motion', 'Review & save']

export default function RecipeWizard(props: Props) {
  return <RecipeEditor key={`${props.scene?.id ?? 'empty'}:${props.editing?.id ?? 'new'}`} {...props} />
}

function RecipeEditor({ data, scene, editing, onScene, onImport, onCancel, refresh, onSaved }: Props) {
  const [step, setStep] = useState(0)
  const [actor, setActor] = useState(editing?.actor ?? '')
  const [points, setPoints] = useState<Point[]>(editing?.authoring?.polygon ?? [])
  const [tool, setTool] = useState<'rectangle' | 'outline'>('rectangle')
  const [feather, setFeather] = useState(editing?.authoring?.feather ?? 8)
  const [context, setContext] = useState(editing?.authoring?.context ?? 0.25)
  const [template, setTemplate] = useState(editing?.authoring?.template_id ?? 'idle')
  const [name, setName] = useState(editing?.name ?? '')
  const [firstId, setFirstId] = useState(editing?.first_scene_id ?? scene?.id ?? '')
  const [lastId, setLastId] = useState(editing?.last_scene_id ?? scene?.id ?? '')
  const [start, setStart] = useState(editing?.start_state ?? 'resting')
  const [end, setEnd] = useState(editing?.end_state ?? 'new pose')
  const [prompt, setPrompt] = useState(editing?.prompt ?? '')
  const [seed, setSeed] = useState(String(editing?.seed ?? 7))
  const [frames, setFrames] = useState(editing?.frames ?? 90)
  const [vae, setVae] = useState(editing?.vae_name ?? data.production?.default_vae_name ?? '')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const saveRequest = useRef(false)
  const id = useId()
  const transition = template === 'transition'
  const poseOptions = data.scenes.filter((item) => item.width === scene?.width && item.height === scene?.height)
  const direction = (data.motion_templates ?? []).find((item) => item.id === template)?.direction ?? ''
  const effectivePrompt = prompt || direction.replaceAll('{actor}', actor.trim() || 'the selected subject') + (data.motion_restrictions ?? '')
  const effectiveName = name || `${actor.trim() || 'Region'} · ${(data.motion_templates ?? []).find((item) => item.id === template)?.name ?? 'Motion'}`
  const body = { scene_id: scene?.id, name: effectiveName, actor, polygon: points, feather, context,
    template_id: template, first_scene_id: firstId, last_scene_id: transition ? lastId : firstId,
    start_state: start, end_state: transition ? end : start, prompt: effectivePrompt,
    seed: Number(seed), frames, vae_name: vae, ...(editing ? { parent_id: editing.id } : {}) }

  function moveTo(next: number) {
    setError('')
    if (next > 0 && (!actor.trim() || points.length < 3)) { setError('Name the actor or region, and outline the area that may move.'); return }
    setStep(next); setPreview(null); window.scrollTo({ top: 0, behavior: 'auto' })
  }
  async function makePreview() {
    setBusy(true); setError(''); setPreview(null)
    try { setPreview(await api<Preview>('motion/preview', body)) }
    catch (error) { setError(error instanceof Error ? error.message : 'Could not prepare the recipe.'); }
    finally { setBusy(false) }
  }
  async function save() {
    if (saveRequest.current) return
    saveRequest.current = true; setBusy(true); setError('')
    try {
      const profile = await api<MotionProfile>('motion/recipes', body)
      await refresh(); onSaved(profile)
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not save the recipe.'); saveRequest.current = false; setBusy(false) }
  }
  async function importPose(file?: File) {
    if (!file || !scene) return
    setBusy(true); setError('')
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error('Choose a pose image smaller than 20 MB.')
      const pose = await api<Scene>('scenes', { image_base64: await encodeFile(file), filename: file.name, title: `${scene.title} · pose`.slice(0, 100) })
      await refresh()
      if (pose.width !== scene.width || pose.height !== scene.height) throw new Error('The image was preserved in Scenes. To use it as a pose, it must match the master’s dimensions and framing.')
      setLastId(pose.id)
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not import the pose.') }
    finally { setBusy(false) }
  }
  if (!scene) return <section className="empty-state"><Icon name="scene" size={34} /><h1>Start with a scene.</h1><p>Import a still to set up your first reusable motion recipe.</p><button className="button dark" onClick={onImport}>Import scene</button></section>
  return <section className="page recipe-page">
    <div className="page-heading"><div><p className="eyebrow">SCENE SETUP {editing ? ` / REVISION ${(editing.revision ?? 1) + 1}` : ''}</p><h1>Decide what comes to life.</h1><p>A saved recipe makes the next take a few clicks away.</p></div><button className="button light" onClick={onCancel} disabled={busy}>Back to scene</button></div>
    <ol className="wizard-steps" aria-label="Recipe setup steps">{steps.map((label, index) => <li key={label}><button disabled={busy} aria-current={step === index ? 'step' : undefined} onClick={() => moveTo(index)} className={step === index ? 'selected' : ''}><span>{index + 1}</span>{label}</button></li>)}</ol>
    <div className="recipe-layout"><div className="panel recipe-main">
      {step === 0 ? <>
        <div className="recipe-form-row"><label className="field">Scene<select value={scene.id} onChange={(event) => onScene(event.target.value)} disabled={!!editing}>{data.scenes.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label><label className="field">Actor or region name<input value={actor} onChange={(event) => setActor(event.target.value)} maxLength={100} placeholder="e.g. Reader, cat, curtain" /></label></div>
        <h2>Mark the area that may move</h2><p className="recipe-help">Include the whole moving subject and space for the action. Everything beyond the feathered mask stays on the master.</p>
        <RegionEditor scene={scene} points={points} onChange={setPoints} tool={tool} onTool={setTool} />
        <div className="recipe-form-row"><label className="field">Soft edge · {feather} px<input type="range" min="0" max="64" value={feather} onChange={(event) => setFeather(Number(event.target.value))} /><span className="field-help">Blends motion into the scene. The final mask is shown before saving.</span></label><label className="field">Surrounding context · {Math.round(context * 100)}%<input type="range" min="0" max="1" step="0.05" value={context} onChange={(event) => setContext(Number(event.target.value))} /><span className="field-help">H3 sees this extra space; the mask still controls what is composited.</span></label></div>
      </> : null}
      {step === 1 ? <>
        <h2>One clear motion</h2><div className="template-choices">{(data.motion_templates ?? []).map((item) => <button key={item.id} className={template === item.id ? 'selected' : ''} aria-pressed={template === item.id} onClick={() => { setTemplate(item.id); setPrompt('') }}><strong>{item.name}</strong><span>{item.description}</span></button>)}</div>
        <div className="recipe-form-row"><label className="field">First pose<select value={firstId} onChange={(event) => setFirstId(event.target.value)}>{poseOptions.map((item) => <option value={item.id} key={item.id}>{item.title}{item.id === scene.id ? ' · master' : ''}</option>)}</select></label><label className="field">Start state<input value={start} maxLength={100} onChange={(event) => setStart(event.target.value)} placeholder="e.g. Reading" /></label></div>
        {transition ? <><div className="recipe-form-row"><label className="field">Last pose<select value={lastId} onChange={(event) => setLastId(event.target.value)}>{poseOptions.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label className="field">End state<input value={end} maxLength={100} onChange={(event) => setEnd(event.target.value)} placeholder="e.g. Looking outside" /></label></div><label className="pose-import">Import an ending pose<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(event) => { void importPose(event.target.files?.[0]); event.target.value = '' }} /><span>Use a full scene image with the same dimensions and fixed camera. Imported pose originals are preserved in Scenes.</span></label></> : <p className="recipe-note">Both ends use the same supplied pose and “{start || 'resting'}” state. Review the generated endpoints before treating the take as a loop.</p>}
        <label className="field">Recipe name<input value={effectiveName} onChange={(event) => setName(event.target.value)} maxLength={100} /></label>
        <label className="field">Motion direction<textarea rows={5} value={effectivePrompt} onChange={(event) => setPrompt(event.target.value)} maxLength={4000} /><span className="field-help">For an action, replace the example with exactly what the subject should do.</span></label>
        <div className="recipe-form-row"><label className="field">Test length<select value={frames} onChange={(event) => setFrames(Number(event.target.value))}><option value={39}>Short test · 39 frames / 1.63s</option><option value={90}>Small action · 90 frames / 3.75s</option><option value={124}>Full take · 124 frames / 5.17s</option></select></label><label className="field">Saved seed<input type="number" min="0" max="2147483647" step="1" value={seed} onChange={(event) => setSeed(event.target.value)} /></label></div>
        <label className="field">Video VAE<select value={vae} onChange={(event) => setVae(event.target.value)}>{[data.production?.original_vae_name ?? 'minimax_h3_video_vae_fp16.safetensors', 'minimax_h3_video_vae_int8_convrot.safetensors'].map((item) => <option value={item} key={item}>{item.includes('int8') ? 'INT8 comparison variant' : 'Original FP16'}{data.production?.available_vae_names.includes(item) ? '' : ' · not reported installed'}</option>)}</select><span className="field-help">The model is saved with the recipe. Generation checks the worker before submitting.</span></label>
      </> : null}
      {step === 2 ? <>
        <h2>Check the protected scene</h2><p className="recipe-help">Prepare a preview to inspect the actual feathered mask and the two images H3 will receive. This step uses no GPU.</p>
        {preview ? <>
          <figure className="protected-preview"><img src={preview.images.overlay} alt="Recipe protection preview: original colors mark the moving area, pale areas remain protected" /><figcaption>Original colors may move. Pale areas stay protected.</figcaption></figure>
          <div className="motion-pose-grid">{(['first', 'last', 'mask'] as const).map((part) => <figure key={part}><img src={preview.images[part]} alt={part === 'mask' ? 'Actual feathered grayscale mask' : `${part} H3 conditioning crop`} /><figcaption>{part === 'mask' ? 'Actual feathered mask · white may move' : `${part === 'first' ? 'First' : 'Last'} pose · 768 × 768`}</figcaption></figure>)}</div>
          <p className="crop-summary">Source crop: x {preview.crop.x}, y {preview.crop.y}, {preview.crop.width} × {preview.crop.height}. H3 receives a fitted 768-square image; padding is removed on return. Scene output: {preview.output_size.join(' × ')}{preview.output_size.some((value) => value % 2) ? ' (MP4 adds a pixel at odd right/bottom edges)' : ''}.</p>
        </> : <div className="preview-placeholder"><Icon name="scene" size={32} /><p>See the mask, context crop and conditioning poses together.</p></div>}
        <button className="button light" onClick={() => void makePreview()} disabled={busy}>{busy ? 'Preparing…' : preview ? 'Rebuild preview' : 'Prepare preview'}</button>
        <p className="recipe-note">Static holds use the actual last frame of a take. A supplied pose guides motion; it does not guarantee an exact generated endpoint. Every candidate still needs approval.</p>
      </> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="wizard-footer"><button className="button light" onClick={() => step ? moveTo(step - 1) : onCancel()} disabled={busy}>{step ? 'Previous' : 'Cancel'}</button>{step < 2 ? <button className="button dark" onClick={() => moveTo(step + 1)} disabled={busy}>Continue<Icon name="arrow" size={16} /></button> : <button className="button dark" onClick={() => void save()} disabled={busy || !preview}>{saveRequest.current ? 'Saving…' : editing ? 'Save revision & open generation' : 'Save recipe & open generation'}<Icon name="arrow" size={16} /></button>}</div>
    </div><aside className="inspector recipe-summary" aria-labelledby={`${id}-summary`}><div className="panel-title"><h2 id={`${id}-summary`}>Your motion recipe</h2><Icon name="settings" size={18} /></div><p className="muted description">{scene.title}</p><div className="detail-pair"><span>Region</span><strong>{actor || 'Not selected'}</strong></div><div className="detail-pair"><span>Outline</span><strong>{points.length} points</strong></div><div className="detail-pair"><span>Timing</span><strong>{frames} frames · 24fps</strong></div><div className="detail-pair"><span>Workflow</span><strong>H3 · 8-step turbo</strong></div><div className="detail-pair"><span>Revision</span><strong>{editing ? (editing.revision ?? 1) + 1 : 1}</strong></div><div className="rule" /><div className="callout"><Icon name="lock" /><div><strong>Save once. Try new takes.</strong><p>Each recipe pins the master, crop mapping, mask, poses, prompt, seed and model. Editing saves a revision; existing takes keep their original recipe.</p></div></div><p className="recipe-help">Actor outlines are manual in this version. Use the preview to check silhouettes and allow room for the planned movement.</p></aside></div>
  </section>
}

function RegionEditor({ scene, points, onChange, tool, onTool }: { scene: Scene; points: Point[]; onChange: (points: Point[]) => void; tool: 'rectangle' | 'outline'; onTool: (tool: 'rectangle' | 'outline') => void }) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<Point | null>(null)
  const [rectangle, setRectangle] = useState({ x: 0, y: 0, width: Math.max(4, Math.floor(scene.width / 4)), height: Math.max(4, Math.floor(scene.height / 4)) })
  function position(event: PointerEvent<SVGSVGElement>): Point {
    const matrix = event.currentTarget.getScreenCTM()
    if (!matrix) return [0, 0]
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return [Math.max(0, Math.min(scene.width - 1, Math.round(point.x))), Math.max(0, Math.min(scene.height - 1, Math.round(point.y)))]
  }
  function box(a: Point, b: Point): Point[] { return [[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])], [Math.min(a[0], b[0]), Math.max(a[1], b[1])]] }
  function down(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return
    if (tool === 'outline') { if (points.length < 256) onChange([...points, position(event)]); return }
    drag.current = position(event); event.currentTarget.setPointerCapture(event.pointerId)
  }
  function move(event: PointerEvent<SVGSVGElement>) { if (drag.current) onChange(box(drag.current, position(event))) }
  function up(event: PointerEvent<SVGSVGElement>) {
    if (drag.current) { onChange(box(drag.current, position(event))); drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId) }
  }
  return <>
    <div className="region-toolbar"><div className="view-toggle"><button className={tool === 'rectangle' ? 'selected' : ''} aria-pressed={tool === 'rectangle'} onClick={() => onTool('rectangle')}>Drag a box</button><button className={tool === 'outline' ? 'selected' : ''} aria-pressed={tool === 'outline'} onClick={() => onTool('outline')}>Click an outline</button></div><button className="text-button" disabled={!points.length} onClick={() => onChange(points.slice(0, -1))}>Undo point</button><button className="text-button" disabled={!points.length} onClick={() => onChange([])}>Clear</button></div>
    <svg ref={svg} className="region-canvas" viewBox={`0 0 ${scene.width} ${scene.height}`} style={{ aspectRatio: `${scene.width} / ${scene.height}` }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null }} role="img" aria-label="Actor selection canvas. Drag a box, click outline points, or use the coordinate fields below.">
      <image href={scene.image_url} width={scene.width} height={scene.height} />
      {points.length > 0 ? <><polygon points={points.map((point) => point.join(',')).join(' ')} fill="#d2da8060" stroke="#eaff9b" strokeWidth="2" vectorEffect="non-scaling-stroke" />{points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={Math.max(scene.width, scene.height) / 150} fill="#eaff9b" stroke="#27372b" vectorEffect="non-scaling-stroke" />)}</> : null}
    </svg>
    <p className="field-help">{tool === 'rectangle' ? 'Drag from one corner to the other. Switch to an outline for a closer silhouette.' : 'Click around the silhouette in order. The shape closes automatically; Undo removes the last point.'}</p>
    <details className="region-coordinates"><summary>Set a box with coordinates</summary><div className="coordinate-fields">{(['x', 'y', 'width', 'height'] as const).map((key) => <label className="field" key={key}>{key}<input aria-label={`Region ${key}`} type="number" min={key === 'width' || key === 'height' ? 2 : 0} max={key === 'x' || key === 'width' ? scene.width - 1 : scene.height - 1} value={rectangle[key]} onChange={(event) => setRectangle({ ...rectangle, [key]: Number(event.target.value) })} /></label>)}</div><button className="button light compact" onClick={() => { const x = Math.max(0, Math.min(scene.width - 2, Math.round(rectangle.x))); const y = Math.max(0, Math.min(scene.height - 2, Math.round(rectangle.y))); onChange(box([x, y], [Math.min(scene.width - 1, x + Math.max(2, Math.round(rectangle.width))), Math.min(scene.height - 1, y + Math.max(2, Math.round(rectangle.height)))])) }}>Use this box</button></details>
  </>
}
