import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import Icon from './Icon'
import type { Candidate, MotionProfile } from './types'

type Props = { candidate: Candidate; options: Candidate[]; profiles: MotionProfile[] }
type Inspection = 'motion' | 'loop' | 'hold' | 'pose'
type Measurements = {
  advisory_only: boolean; same_motion: boolean; warnings: string[]
  checks: { id: string; label: string; pixels: number; changed_pixels: number; mean_absolute_error: number; max_channel_difference: number }[]
}

function takeProfile(take: Candidate, profiles: MotionProfile[]) {
  return profiles.find(p => p.id === (take.metadata.motion?.profile_id ?? take.metadata.motion?.profile?.id))
    ?? profiles.find(p => p.reference_candidate_id === take.id)
}

function matchingMotion(a: Candidate, b: Candidate, profiles: MotionProfile[]) {
  if (a.id === b.id || a.scene_id !== b.scene_id) return false
  const left = takeProfile(a, profiles), right = takeProfile(b, profiles)
  if (!left || !right) return false
  const sameContract = left.actor.toLowerCase() === right.actor.toLowerCase()
    && left.start_state === right.start_state && left.end_state === right.end_state
    && left.first_scene_id === right.first_scene_id && left.last_scene_id === right.last_scene_id
  const sameFamily = (left.family_id ?? left.id) === (right.family_id ?? right.id)
  const references = [left.reference_candidate_id, a.metadata.motion?.reference_candidate_id].filter(Boolean)
  const reverse = [right.reference_candidate_id, b.metadata.motion?.reference_candidate_id].filter(Boolean)
  return sameContract && (sameFamily || left.id === right.id || references.includes(b.id) || reverse.includes(a.id)
    || references.some(id => reverse.includes(id)))
}

function properties(take: Candidate) {
  const output = take.metadata.outputs[0]?.properties
  return { count: Math.max(1, output?.frame_count ?? 1), fps: output?.effective_fps && output.effective_fps > 0 ? output.effective_fps : 24,
    video: output?.container === 'mp4' }
}
function decoded(take: Candidate, frame: number) { return `/api/candidates/${encodeURIComponent(take.id)}/frames/${frame}` }
function reviewLabel(take: Candidate) { return take.status === 'candidate' ? 'Needs review' : take.status }
function takeLabel(take: Candidate, profiles: MotionProfile[]) {
  const profile = takeProfile(take, profiles)
  return `${take.label} · ${take.id.slice(0, 8)} · seed ${String(take.metadata.parameters.seed ?? 'unknown')} · recipe ${profile?.revision ?? 'legacy'} · ${reviewLabel(take)}`
}

export default function TakeComparison({ candidate, options, profiles }: Props) {
  const [otherId, setOtherId] = useState('')
  const choices = options.filter(take => matchingMotion(candidate, take, profiles))
    .sort((a, b) => a.created.localeCompare(b.created) || a.id.localeCompare(b.id))
  const other = choices.find(take => take.id === otherId) ?? choices.at(-1)
  return <section className="ed-take-comparison" aria-label="Take comparison">
    <label className="ed-compare-select">Compare source A with take B<select aria-label="Comparison take" value={other?.id ?? ''} disabled={!choices.length} onChange={e => setOtherId(e.target.value)}>
      {choices.length ? choices.map(take => <option key={take.id} value={take.id}>{takeLabel(take, profiles)}</option>) : <option value="">No compatible second take</option>}
    </select></label>
    {!other ? <p className="ed-help">No other take shares this motion’s scene, subject and state contract. Recipe revisions and earlier reference takes appear here when available. You can still inspect this take’s loop and hold boundaries.</p> : null}
    <ComparisonPlayer key={`${candidate.id}:${other?.id ?? 'single'}`} a={candidate} b={other} profiles={profiles} />
    <p className="ed-compare-note">Comparison is for review. Pending and rejected takes remain ineligible for the sequence; approval uses the source A controls below.</p>
  </section>
}

function ComparisonPlayer({ a, b, profiles }: { a: Candidate; b?: Candidate; profiles: MotionProfile[] }) {
  const [frame, setFrame] = useState(0)
  const [decodedFrame, setDecodedFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [inspection, setInspection] = useState<Inspection>('motion')
  const [error, setError] = useState('')
  const [measuring, setMeasuring] = useState(false)
  const [measurements, setMeasurements] = useState<Measurements | null>(null)
  const [loaded, setLoaded] = useState<Record<string, boolean>>({})
  const videos = useRef<(HTMLVideoElement | null)[]>([])
  const currentFrame = useRef(frame)
  currentFrame.current = frame
  const clock = properties(a).fps
  const takes = b ? [a, b] : [a]
  const end = Math.max(...takes.map(take => properties(take).count / properties(take).fps))
  const maximum = Math.max(0, Math.ceil(end * clock - 0.000001) - 1)
  const videoAvailable = takes.every(take => properties(take).video)
  const sameRate = !b || Math.abs(properties(b).fps - clock) < 0.001
  const measureAbort = useRef<AbortController | null>(null)
  const scrubTimer = useRef<number | null>(null)

  useEffect(() => () => { measureAbort.current?.abort(); if (scrubTimer.current !== null) window.clearTimeout(scrubTimer.current) }, [])
  useEffect(() => {
    if (!playing && scrubTimer.current === null) setDecodedFrame(currentFrame.current)
  }, [playing])

  useEffect(() => {
    const elements = [...videos.current]
    if (!playing) { elements.forEach(element => element?.pause()); return }
    let started = performance.now()
    const from = currentFrame.current / clock
    let animation = 0, disposed = false
    const start = async () => {
      try {
        await Promise.all(elements.map(async (element, index) => {
          if (!element) return
          const item = index === 0 ? a : b!
          const timing = properties(item)
          element.currentTime = Math.min(from, (timing.count - 1) / timing.fps)
          if (from < timing.count / timing.fps) await element.play()
        }))
        if (disposed) { elements.forEach(element => element?.pause()); return }
        started = performance.now()
        animation = requestAnimationFrame(tick)
      } catch {
        if (!disposed) { setPlaying(false); setError('The paired videos could not play. Wait for loading, or inspect decoded frames with the slider.') }
      }
    }
    void start()
    function tick() {
      const seconds = from + (performance.now() - started) / 1000
      if (seconds >= end) { setFrame(maximum); setDecodedFrame(maximum); setPlaying(false); return }
      setFrame(Math.min(maximum, Math.floor(seconds * clock)))
      elements.forEach((element, index) => {
        if (!element) return
        const timing = properties(index === 0 ? a : b!)
        if (seconds >= timing.count / timing.fps) { element.pause(); return }
        if (!element.seeking && element.readyState >= 2 && Math.abs(element.currentTime - seconds) > 0.12) element.currentTime = seconds
      })
      animation = requestAnimationFrame(tick)
    }
    return () => { disposed = true; cancelAnimationFrame(animation); elements.forEach(element => element?.pause()) }
    // The playback segment captures its initial frame; seeking pauses and starts a new segment.
  }, [playing, a.id, b?.id, clock, end, maximum])

  function cancelScrub() { if (scrubTimer.current !== null) window.clearTimeout(scrubTimer.current); scrubTimer.current = null }
  function seek(next: number) { cancelScrub(); const at = Math.max(0, Math.min(maximum, next)); setPlaying(false); setError(''); setFrame(at); setDecodedFrame(at) }
  function scrub(next: number) {
    cancelScrub()
    const at = Math.max(0, Math.min(maximum, next))
    setPlaying(false); setError(''); setFrame(at)
    // Intermediate slider positions update the clock immediately without spawning a decoder request.
    scrubTimer.current = window.setTimeout(() => { scrubTimer.current = null; setDecodedFrame(at) }, 150)
  }
  function chooseInspection(next: Inspection) { cancelScrub(); setDecodedFrame(frame); setPlaying(false); setInspection(next); setError('') }
  function togglePlayback() {
    cancelScrub(); setError('')
    const at = !playing && frame === maximum ? 0 : frame
    setFrame(at); setDecodedFrame(at); setPlaying(value => !value)
  }
  async function measure() {
    if (!b || measuring) return
    const controller = new AbortController()
    measureAbort.current?.abort(); measureAbort.current = controller
    cancelScrub(); setDecodedFrame(frame); setPlaying(false); setMeasuring(true); setError('')
    try { setMeasurements(await api<Measurements>(`candidates/${a.id}/compare/${b.id}`, undefined, controller.signal)) }
    catch (problem) { if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : 'Seam measurements could not be read.') }
    finally { if (!controller.signal.aborted) setMeasuring(false) }
  }
  function image(url: string, alt: string, pending = false) {
    return <div className="ed-exact-picture" aria-busy={pending || !loaded[url]}><img key={url} src={url} alt={alt} style={pending ? { visibility: 'hidden' } : undefined} onLoad={() => setLoaded(previous => previous[url] ? previous : { ...previous, [url]: true })} onError={() => { setPlaying(false); setError(`Could not decode ${alt}.`); setLoaded(previous => ({ ...previous, [url]: true })) }} />{pending || !loaded[url] ? <span>{pending ? 'Seeking decoded frame…' : 'Loading decoded frame…'}</span> : null}</div>
  }

  return <>
    <div className="ed-compare-modes" aria-label="Comparison inspection">{([['motion', 'Shared playback'], ['loop', 'Last → first'], ['hold', 'Last → held frame'], ['pose', 'Last → pose plate']] as const).map(([value, label]) => <button key={value} aria-pressed={inspection === value} onClick={() => chooseInspection(value)}>{label}</button>)}</div>
    <div className={`ed-compare-grid ${inspection === 'motion' ? '' : 'ed-seam-grid'}`}>
      {takes.map((take, index) => {
        const timing = properties(take), profile = takeProfile(take, profiles)
        const absolute = Math.floor(frame / clock * timing.fps + 0.000001)
        const at = Math.min(timing.count - 1, absolute), held = absolute >= timing.count
        const decodedAt = Math.min(timing.count - 1, Math.floor(decodedFrame / clock * timing.fps + 0.000001))
        const imageAt = playing && held ? timing.count - 1 : decodedAt
        const pending = !playing && frame !== decodedFrame
        const exactUrl = decoded(take, imageAt), tail = decoded(take, timing.count - 1)
        return <article key={take.id} className="ed-compare-take">
          <header><strong>{index === 0 ? 'A · Source take' : 'B · Comparison'}</strong><span className={`ed-take-status ${take.status}`}>{reviewLabel(take)}</span></header>
          <p className="ed-compare-identity">{take.label}<small>Seed {String(take.metadata.parameters.seed ?? 'unknown')} · recipe {profile?.revision ?? 'legacy'} · review {take.version} · {take.id.slice(0, 8)}</small><small>{profile?.actor} · {profile?.start_state} → {profile?.end_state}</small></p>
          {inspection === 'motion' ? <><div className="ed-compare-picture">{timing.video ? <video ref={element => { videos.current[index] = element }} src={take.media_url} poster={take.frames.start} muted playsInline preload="metadata" aria-label={`Comparison ${index === 0 ? 'A' : 'B'} ${take.label}`} style={{ visibility: playing && !held ? 'visible' : 'hidden' }} onError={() => { setPlaying(false); setError(`Could not play ${take.label}.`) }} /> : null}{!playing || held ? image(exactUrl, `${index === 0 ? 'A' : 'B'} ${take.label}, decoded frame ${imageAt + 1}`, pending) : null}</div><p className="ed-compare-frame">Frame {at + 1} / {timing.count} · {timing.fps.toFixed(3)} fps{held ? ' · Ended — holding final decoded frame' : ''}</p></> : <div className="ed-seam-pair"><figure>{image(tail, `${index === 0 ? 'A' : 'B'} last decoded frame`)}<figcaption>Last decoded frame · {timing.count}</figcaption></figure><figure>{inspection === 'pose' && !profile ? <p className="ed-help">Pinned ending pose is unavailable.</p> : image(inspection === 'loop' ? decoded(take, 0) : inspection === 'pose' ? profile!.last_url : tail, `${index === 0 ? 'A' : 'B'} ${inspection === 'loop' ? 'first decoded frame' : inspection === 'pose' ? 'pinned ending pose plate' : 'actual exit-frame hold'}`)}<figcaption>{inspection === 'loop' ? 'First decoded frame · 1' : inspection === 'pose' ? 'Pinned ending pose plate' : 'Hold repeats this exact exit frame'}</figcaption></figure></div>}
        </article>
      })}
    </div>
    {inspection === 'motion' ? <><div className="ed-compare-transport"><button aria-label="Comparison first frame" disabled={frame === 0} onClick={() => seek(0)}>◀|</button><button aria-label="Comparison previous frame" disabled={frame === 0} onClick={() => seek(frame - 1)}>◀</button><button disabled={!videoAvailable} aria-label={playing ? 'Pause comparison' : 'Play comparison'} onClick={togglePlayback}><Icon name={playing ? 'pause' : 'play'} size={13} />{playing ? 'Pause both' : 'Play both'}</button><button aria-label="Comparison next frame" disabled={frame === maximum} onClick={() => seek(frame + 1)}>▶</button><button aria-label="Comparison final frame" disabled={frame === maximum} onClick={() => seek(maximum)}>|▶</button><span>{(frame / clock).toFixed(3)}s · clock frame {frame + 1}/{maximum + 1}</span></div><label className="ed-compare-scrub"><span className="sr-only">Comparison position</span><input type="range" min={0} max={maximum} step={1} value={frame} onChange={e => scrub(Number(e.target.value))} /></label><p className="ed-compare-note">{videoAvailable ? 'Shared video clock during playback. Pause, step or scrub for exact decoded frames. Shorter takes hold their final frame.' : 'Exact frame inspection is available. Continuous playback requires MP4 takes.'}{!sameRate ? ` Frame rates differ; each take samples the shared ${clock.toFixed(3)} fps clock at its own rate.` : ''}</p></> : <p className="ed-compare-note">{inspection === 'loop' ? 'Inspect the last → first cut before accepting a loop.' : inspection === 'hold' ? 'The sequence holds the actual decoded exit frame. It does not reset to a generated pose plate.' : 'Inspect the potential reset from the video’s actual exit to its supplied ending pose. This plate is not substituted into the clip.'}</p>}
    <div className="ed-compare-measure"><button disabled={!b || measuring} onClick={() => void measure()}>{measuring ? 'Measuring…' : 'Measure seams'}</button><span>Pixel differences are advisory; approval stays manual.</span></div>
    {measurements ? <details className="ed-compare-metrics" open><summary>Decoded boundary measurements</summary>{measurements.warnings.map((warning, index) => <p key={index}>{warning}</p>)}<table><thead><tr><th>Boundary</th><th>Mean RGB Δ</th><th>Max Δ</th><th>Changed pixels</th></tr></thead><tbody>{measurements.checks.map(check => <tr key={check.id}><th scope="row">{check.label}</th><td>{check.mean_absolute_error.toFixed(3)}</td><td>{check.max_channel_difference}</td><td>{check.changed_pixels.toLocaleString()} / {check.pixels.toLocaleString()}</td></tr>)}</tbody></table><p>No numeric difference threshold approves a motion or its joins.</p></details> : null}
    {error ? <p className="ed-compare-error" role="alert">{error}</p> : null}
  </>
}
