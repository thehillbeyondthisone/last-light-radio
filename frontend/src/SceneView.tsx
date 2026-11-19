import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, encodeFile } from './api'
import Icon from './Icon'
import type { Candidate, MotionProfile, Scene } from './types'

export default function SceneView({ scene, candidates, profiles, onSetup, onImport, onGenerate, onReview }: {
  scene?: Scene; candidates: Candidate[]; profiles: MotionProfile[]; onSetup: (profile?: MotionProfile) => void; onImport: () => void; onGenerate: (id?: string) => void; onReview: (id: string) => void
}) {
  if (!scene) return <section className="empty-state"><div className="empty-icon"><Icon name="scene" size={34} /></div><p className="eyebrow">EVERY PLACE STARTS WITH A STILL</p><h1>Make room for a new world.</h1><p>Import a scene image. We’ll preserve the original<br />while you explore what moves within it.</p><button className="button dark" onClick={onImport}><Icon name="plus" />Import your first scene</button></section>
  const clips = candidates.filter((item) => item.scene_id === scene.id)
  const recipes = profiles.filter((item) => item.scene_id === scene.id)
  const latestRecipes = recipes.filter((item) => !recipes.some((next) => next.parent_id === item.id)).sort((a, b) => Number(b.origin === 'authored') - Number(a.origin === 'authored'))
  return <section className="page scene-overview">
    <div className="page-heading"><div><p className="eyebrow">{scene.fixture ? 'TECHNICAL TEST SCENE' : 'YOUR SCENE'}</p><h1>{scene.title}</h1><p>{clips.filter((clip) => clip.status === 'approved').length} approved motions · {clips.filter((clip) => clip.status === 'candidate').length} takes to review</p></div><button className="button dark" onClick={() => onGenerate()}>Make a motion<Icon name="arrow" size={17} /></button></div>
    <div className="image-stage"><img className="master-image" src={scene.image_url} alt={scene.title} /><span className="stage-footnote"><Icon name="lock" size={12} />Original scene · {scene.width} × {scene.height}</span></div>
    <div className="section-heading"><h2>Recent takes</h2><button className="text-button" onClick={() => onGenerate()}>Open motion workspace<Icon name="arrow" size={15} /></button></div>
    <div className="clip-grid">{clips.slice(0, 4).map((clip) => <button className="clip-card" key={clip.id} onClick={() => onReview(clip.id)}><div className="clip-image"><img src={clip.frames.middle} alt={`${clip.label} preview`} /><span className="clip-play"><Icon name="play" size={14} /></span><span className="duration">{clip.metadata.outputs[0].properties.duration_seconds.toFixed(2)}s</span></div><div className="clip-card-info"><strong>{clip.label}</strong><span className={`badge ${clip.status}`}>{clip.status === 'candidate' ? 'Needs review' : clip.status}</span></div></button>)}</div>
    {clips.length > 4 ? <details className="scene-disclosure"><summary>All {clips.length} takes</summary><div className="scene-take-list">{clips.map((clip) => <button key={clip.id} onClick={() => onReview(clip.id)}><span>{clip.label}</span><span className={`badge ${clip.status}`}>{clip.status === 'candidate' ? 'Needs review' : clip.status}</span><Icon name="arrow" size={14} /></button>)}</div></details> : null}
    <details className="scene-disclosure"><summary>Motion setup & scene details</summary><button className="button light compact" onClick={() => onSetup()}><Icon name="plus" size={15} />Set up a new motion</button><SavedRecipes recipes={latestRecipes} onGenerate={onGenerate} onSetup={onSetup} /><p className="muted description">{scene.description}</p><details className="provenance"><summary>Image provenance</summary><code>{scene.master.sha256}</code></details></details>
  </section>
}


function SavedRecipes({ recipes, onGenerate, onSetup }: { recipes: MotionProfile[]; onGenerate: (id?: string) => void; onSetup: (profile?: MotionProfile) => void }) {
  return <div className="scene-recipes">
    <div className="section-heading"><div><h2>Saved motion recipes <span className="subtle-count">{recipes.length}</span></h2><p>Reuse the same setup, or save a new revision.</p></div></div>
    <div className="saved-recipes">{recipes.length ? recipes.map((item) => <div className="saved-recipe" key={item.id}><img src={item.mask_url} alt="" /><div><strong>{item.name}</strong><span>{item.actor} · {item.start_state} → {item.end_state} · {item.origin === 'authored' ? `revision ${item.revision}` : 'recovered'}</span></div><button className="text-button" onClick={() => onGenerate(item.id)}>Use recipe<Icon name="arrow" size={14} /></button>{item.authoring ? <button className="text-button" onClick={() => onSetup(item)}>Edit revision</button> : null}</div>) : <div className="quiet-empty">Set up a region once to make repeatable H3 takes for this scene.</div>}</div>
  </div>
}

export function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: (scene: Scene) => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { dialog.current?.showModal() }, [])
  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file); setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  function choose(next?: File) {
    if (!next) return
    if (next.size > 20 * 1024 * 1024) { setError('Choose an image smaller than 20 MB.'); return }
    setFile(next); setError('')
    if (!title) setTitle(next.name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' '))
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) { setError('Choose a scene image first.'); return }
    setBusy(true); setError('')
    try { const scene = await api<Scene>('scenes', { title, description, filename: file.name, image_base64: await encodeFile(file) }); await onImported(scene) }
    catch (error) { setError(error instanceof Error ? error.message : 'Import failed.'); setBusy(false) }
  }
  return <dialog ref={dialog} className="import-dialog" onCancel={(event) => { if (busy) event.preventDefault(); else onClose() }} onClose={onClose} aria-labelledby="import-title"><form onSubmit={(event) => void submit(event)}><div className="modal-heading"><div><p className="eyebrow">ADD A NEW PLACE</p><h2 id="import-title">Import a scene</h2></div><button className="icon-button" type="button" aria-label="Close import" onClick={onClose} disabled={busy}><Icon name="close" /></button></div><label className={`upload-zone ${file ? 'has-image' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0]) }}>{preview ? <img src={preview} alt="Selected scene preview" /> : <><Icon name="upload" size={29} /><strong>Drop your scene image here</strong><span>or click to choose a file</span><small>PNG, JPEG or WebP · up to 20 MB</small></>}<input type="file" accept="image/png,image/jpeg,image/webp" aria-label="Scene image file" onChange={(event) => choose(event.target.files?.[0])} disabled={busy} /></label><label className="field">Scene name<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={100} required placeholder="A place with a story" disabled={busy} /></label><label className="field">Description <span className="optional">optional</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={1000} rows={2} placeholder="A few details about this place…" disabled={busy} /></label>{error ? <p className="form-error" role="alert">{error}</p> : null}<p className="import-assurance"><Icon name="lock" size={14} />We’ll preserve an unchanged copy of your original.</p><div className="modal-footer"><button className="button light" type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="button dark" disabled={busy || !file}>{busy ? 'Importing…' : 'Import scene'}<Icon name="arrow" size={16} /></button></div></form></dialog>
}
