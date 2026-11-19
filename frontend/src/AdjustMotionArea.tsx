import { useEffect, useState } from 'react'
import { api } from './api'
import MaskPainter from './MaskPainter'
import type { Candidate, MotionProfile, Scene } from './types'

export default function AdjustMotionArea({ candidate, profile, scene, onCancel, onSaved }: { candidate: Candidate; profile: MotionProfile; scene: Scene; onCancel: () => void; onSaved: (candidate: Candidate) => Promise<void> }) {
  const [part, setPart] = useState<'start' | 'middle' | 'end'>('middle')
  const [mask, setMask] = useState('')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'auto' }) }, [])
  async function apply() {
    if (busy) return
    setBusy(true); setError('')
    try { const result = await api<Candidate>(`candidates/${candidate.id}/area`, { mask_base64: mask }); await onSaved(result) }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not update the motion area.'); setBusy(false) }
  }
  return <section className="page motion-guide">
    <div className="page-heading"><div><p className="eyebrow">ADJUST MOTION AREA</p><h1>Let the whole action through.</h1><p>Reveal clipped hands or props with Include. Use Protect around nearby subjects.</p></div><button className="text-button" disabled={busy} onClick={onCancel}>Back to take</button></div>
    <div className="panel guide-card"><div className="adjust-sample-picker" aria-label="Source frame">{(['start', 'middle', 'end'] as const).map((item) => <button disabled={busy} key={item} aria-pressed={part === item} onClick={() => setPart(item)}>{item === 'start' ? 'Start' : item === 'middle' ? 'Mid-action' : 'End'}</button>)}</div><p className="recipe-help">The picture shows the saved generated motion before the area is applied. Check all three moments as you adjust.</p><fieldset className="paint-fieldset" disabled={busy}><MaskPainter scene={scene} imageUrl={candidate.source_frames?.[part] ?? candidate.frames[part]} initialMaskUrl={profile.mask_url} boundary={profile.crop} onChange={setMask} onDirty={() => setDirty(true)} /></fieldset></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}<div className="guide-footer"><p>Uses the existing motion. Your original take stays available.</p><button className="button dark" disabled={busy || !dirty || !mask} onClick={() => void apply()}>{busy ? 'Updating the preview…' : 'Apply area & preview'}</button></div>
  </section>
}
