import { useEffect, useRef, useState } from 'react'
import AudioWaveform from './AudioWaveform'
import { api } from './api'
import AudioImport from './AudioImport'
import { JobMetadata } from './GenerationFlow'
import type { GenerationJob } from './GenerationFlow'
import type { AudioAsset, AudioPlacement, EditorConfig } from './editorTypes'

type Props = { initialRole?: 'production' | 'music'; initialAssetId?: string; mixedPreview?: boolean; /** Film: no approve/reject (2026-11-19); any imported sound can be placed. */ noReview?: boolean; config?: EditorConfig; busy: boolean; frame: number; onChange: (config: EditorConfig) => void; onApply: () => void }
export default function AudioWorkspace({ config, busy, frame, onChange, onApply, mixedPreview, initialAssetId, initialRole, noReview }: Props) {
  const audition=useRef<HTMLAudioElement>(null)
  const [assets, setAssets] = useState<AudioAsset[]>([])
  const [selected, setSelected] = useState(initialAssetId??'')
  useEffect(() => { if(initialAssetId) { setSelected(initialAssetId); setRole(initialRole??'production') } }, [initialAssetId])
  const [working, setWorking] = useState(false)
  const operationLock = useRef(false)
  const [error, setError] = useState('')
  const [reviewed, setReviewed] = useState(false)
  const [notes, setNotes] = useState('')
  const [provenance, setProvenance] = useState('')
  const [role, setRole] = useState<'production' | 'music'>(initialRole??'production')
  const locked = busy || working
  const asset = assets.find(item => item.id === selected)
  const tracks = config?.audio_tracks ?? []
  const libraryOnly = !config || config.duration_frames < 1
  const fps = config?.fps ?? 24
  async function reload() {
    const result = await api<{ assets: AudioAsset[] }>('audio')
    setAssets(result.assets)
  }
  useEffect(() => { let active = true; api<{ assets: AudioAsset[] }>('audio').then(result => { if (active) setAssets(result.assets) }).catch(e => { if (active) setError(String(e.message ?? e)) }); return () => { active = false } }, [initialAssetId])
  useEffect(() => { setReviewed(false); setNotes('') }, [selected])
  async function review(decision: 'approved' | 'rejected') {
    if (!asset || locked || operationLock.current || (decision === 'approved' && !reviewed)) return
    operationLock.current = true; setWorking(true); setError('')
    try { await api(`audio/${asset.id}/review`, { decision, notes, expected_version: asset.version }); await reload(); setReviewed(false) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { operationLock.current = false; setWorking(false) }
  }
  function change(items: AudioPlacement[]) {
    if (!config || libraryOnly) return
    const next = { ...config }
    if (items.length) next.audio_tracks = items
    else delete next.audio_tracks
    onChange(next)
  }
  function patch(id: string, value: Partial<AudioPlacement>) { change(tracks.map(track => track.id === id ? { ...track, ...value } : track)) }
  function add() {
    if (!config || libraryOnly || !asset || (!noReview && asset.status !== 'approved')) return
    const start = Math.min(frame, config.duration_frames - 1)
    const duration = Math.min(Math.floor(asset.duration_seconds * config.fps), config.duration_frames - start)
    if (duration < 1) { setError('The source is shorter than one sequence frame.'); return }
    change([...tracks, { id: crypto.randomUUID(), role, asset_id: asset.id, start_frame: start, source_in_frame: 0, duration_frames: duration, gain_db: 0, fade_in_frames: 0, fade_out_frames: 0, enabled: true }])
  }
  const framesInput = (track: AudioPlacement, key: 'start_frame' | 'source_in_frame' | 'duration_frames' | 'fade_in_frames' | 'fade_out_frames', title: string, min = 0) =>
    <label key={key}>{title} (seconds)<input type="number" min={min / fps} step={1 / fps} value={Number((track[key] / fps).toFixed(4))} disabled={locked} onChange={e => { if (e.target.value !== '') patch(track.id, { [key]: Math.max(min, Math.round(Number(e.target.value) * fps)) }) }} /></label>
  return <div className="ed-setup ed-audio-workspace">
    <h3>Sound & music</h3>
    <p className="ed-help">{noReview ? 'Import a PCM WAV without changing its original. Listen, then place it. Picture scheduling stays unchanged.' : 'Import a PCM WAV without changing its original. Listen and approve before placing it. Picture scheduling stays unchanged.'}</p>
    <AudioImport onBusy={setWorking} disabled={locked} provenance={provenance} onImported={async result=>{await reload();setSelected(result.id)}}/>
    <button disabled={locked} onClick={()=>void reload().catch(e=>setError(String(e.message??e)))}>Refresh audio library</button>
    <details><summary>Generation recipe / provenance (optional)</summary><textarea aria-label="Audio provenance JSON" placeholder='{"generator":"ACE-Step","seed":123}' value={provenance} onChange={e => setProvenance(e.target.value)} disabled={locked} /><p className="ed-help">Saved with the imported take, not modified by timeline edits. Include model, prompt, seed and source receipt as available.</p></details>
    <label className="ed-field">Audio library<select aria-label="Audio library" value={selected} disabled={locked} onChange={e => setSelected(e.target.value)}><option value="">Choose an imported take</option>{assets.map(item => <option value={item.id} key={item.id}>{item.label}{noReview ? '' : ` · ${item.status}`}</option>)}</select></label>
    {asset ? <div className="ed-audio-review">
      <strong>{asset.label}</strong><p>{asset.duration_seconds.toFixed(2)}s{noReview ? '' : ` · ${asset.status}`}</p>
      <AudioWaveform assetId={asset.id} onSeek={seconds=>{if(audition.current)audition.current.currentTime=seconds}}/><audio ref={audition} key={asset.id} controls preload="metadata" src={asset.media_url} aria-label="Audition audio take" onError={() => setError('This audio take could not be played.')} />
      {asset.provenance?.generation_metadata?<JobMetadata job={{metadata:asset.provenance.generation_metadata as GenerationJob['metadata']}}/>:null}<details><summary>Saved source & recipe</summary><pre>{JSON.stringify({ id: asset.id, sha256: asset.source?.sha256, provenance: asset.provenance }, null, 2)}</pre></details>
      {noReview ? null : <><label className="ed-check"><input type="checkbox" checked={reviewed} disabled={locked} onChange={e => setReviewed(e.target.checked)} />I listened and approve this source for use</label>
      <label>Review notes<input value={notes} disabled={locked} onChange={e => setNotes(e.target.value)} /></label>
      <div className="ed-audio-buttons"><button disabled={locked || !reviewed} onClick={() => void review('approved')}>Approve take</button><button disabled={locked} onClick={() => void review('rejected')}>Reject take</button></div></>}
      {!libraryOnly ? <><label>Destination<select value={role} disabled={locked} onChange={e => setRole(e.target.value as typeof role)}><option value="production">A1 · Production sound</option><option value="music">A2 · Music</option></select></label>
      {noReview ? <button disabled={locked} onClick={add}>Place at playhead</button> : <button disabled={locked || asset.status !== 'approved'} onClick={add}>Place approved take at playhead</button>}</> : <p>{noReview ? 'Set an explicit sequence duration when you are ready to place this audio; listening works now.' : 'Library review only. Set an explicit sequence duration when you are ready to place this audio; audition and approval work now.'}</p>}
    </div> : null}
    {!libraryOnly ? <><h3>Sequence audio clips</h3>
    {!tracks.length ? <p className="ed-help">No audio placed. Existing exports remain silent.</p> : null}
    {tracks.map((track, index) => <fieldset className="ed-audio-clip" key={track.id}>
      <legend>{index + 1}. {assets.find(a => a.id === track.asset_id)?.label ?? track.asset_id}</legend>
      <label className="ed-check"><input type="checkbox" checked={track.enabled} disabled={locked} onChange={e => patch(track.id, { enabled: e.target.checked })} />Enabled</label>
      <label>Track<select value={track.role} disabled={locked} onChange={e => patch(track.id, { role: e.target.value as AudioPlacement['role'] })}><option value="production">Production sound</option><option value="music">Music</option></select></label>
      <div className="ed-audio-grid">
        {framesInput(track, 'start_frame', 'Timeline start')}
        {framesInput(track, 'source_in_frame', 'Source in')}
        {framesInput(track, 'duration_frames', 'Duration', 1)}
        <label>Gain (dB)<input type="number" min={-60} max={12} step={0.5} value={track.gain_db} disabled={locked} onChange={e => patch(track.id, { gain_db: Number(e.target.value) })} /></label>
        {framesInput(track, 'fade_in_frames', 'Fade in')}
        {framesInput(track, 'fade_out_frames', 'Fade out')}
      </div>
      <button disabled={locked} onClick={() => change(tracks.filter(item => item.id !== track.id))}>Remove placement (keep source)</button>
    </fieldset>)}
    <button className="ed-primary" disabled={locked} onClick={onApply}>Apply audio to sequence</button></> : <p>Audio library: no timeline is required to import, listen, approve or reject a source.</p>}
    <p className="ed-help">{mixedPreview ? 'Audition original takes here; return to Picture & shots for synchronized browser mix preview. Export for frame-exact timing. Overlaps sum, so leave headroom.' : 'This milestone auditions source takes here. Canvas playback is still picture-only. Export the saved sequence to hear the trimmed, faded mix with picture; overlaps are summed, so leave headroom.'}</p>
    {error ? <p role="alert">{error}</p> : null}
  </div>
}








