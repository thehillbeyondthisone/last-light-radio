import { useEffect, useRef } from 'react'
import AmbienceCanvas from './AmbienceCanvas'
import TextureCanvas from './TextureCanvas'
import type { Scene, Pilot } from './types'
import type { SubjectSequence, SubjectEvent, TextureSettings } from './editorTypes'

function ActorLayer({ sequence, event, frame, playing, rate, onError }: { sequence: SubjectSequence; event: SubjectEvent; frame: number; playing: boolean; rate: number; onError: (message: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const currentFrame = useRef(frame)
  currentFrame.current = frame
  const mask = event.layer_clip_id ? `/api/editor/plans/${sequence.id}/masks/${event.layer_clip_id}` : undefined
  const style = mask ? { maskImage: `url("${mask}")`, WebkitMaskImage: `url("${mask}")` } : undefined
  useEffect(() => {
    const element = video.current
    if (!element || event.kind !== 'clip') return
    let active = true
    const wanted = (frame - event.start_frame) / sequence.manifest.fps
    // Forward shuttle plays natively at 1×–8×; reverse shuttle is paused and seeks every frame.
    if (playing && element.playbackRate !== rate) element.playbackRate = rate
    if (element.readyState > 0 && (!playing || Math.abs(element.currentTime - wanted) > .15 * rate)) element.currentTime = wanted
    if (playing && element.paused) void element.play().catch(problem => {
      // Seeking, pausing and replaced takes can cancel an outstanding play().
      // An obsolete promise must not stop the new take or the ambience clock.
      if (active && element.isConnected && problem?.name !== 'AbortError') {
        onError(`Canvas playback could not start: ${problem instanceof Error ? problem.message : String(problem)}`)
      }
    })
    else if (!playing) element.pause()
    return () => { active = false }
  }, [frame, playing, rate, event.kind, event.start_frame, sequence.manifest.fps, onError])
  if (!mask) return null // Canonical holds already exist in the locked base layer.
  return event.kind === 'clip' ? <video data-layer-id={event.layer_clip_id} className="ed-actor-layer" style={style} ref={video} src={`/api/candidates/${event.variant_id}/media`} muted playsInline preload="auto" aria-label={`${event.actor}: ${event.label}`} onError={() => onError(`Could not load ${event.label}.`)} onLoadedMetadata={e => { e.currentTarget.currentTime = (currentFrame.current - event.start_frame) / sequence.manifest.fps }} /> : <img data-layer-id={event.layer_clip_id} className="ed-actor-layer" style={style} src={`/api/pilots/${sequence.id}/frames/${event.index}/hold`} alt={`${event.actor}: held exit frame`} onError={() => onError(`Could not load the held frame for ${event.actor}.`)} />
}

export default function EditorCanvas({ scene, sequence, frame, playing, rate = 1, maskUrl, texture, onError }: { scene: Scene; sequence: SubjectSequence | null; frame: number; playing: boolean; rate?: number; maskUrl?: string; texture?: TextureSettings; onError: (message: string) => void }) {
  const image = useRef<HTMLImageElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const source = useRef<HTMLCanvasElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const frameRef = useRef(frame)
  frameRef.current = frame
  useEffect(() => {
    if (source.current) delete source.current.dataset.frame
    if (!sequence?.manifest.ambience) return
    let disposed = false, animation = 0
    const masks = new Map<string, HTMLImageElement>()
    const patch = document.createElement('canvas')
    patch.width = scene.width; patch.height = scene.height
    void Promise.all(sequence.manifest.clips.map(clip => new Promise<void>((resolve, reject) => {
      const bitmap = new Image()
      bitmap.onload = () => { masks.set(clip.id, bitmap); resolve() }
      bitmap.onerror = () => reject(new Error(`Could not load the compositing mask for ${clip.label}.`))
      bitmap.src = `/api/editor/plans/${sequence.id}/masks/${clip.id}`
    }))).then(() => {
      const draw = () => {
        if (disposed) return
        const target = source.current, base = image.current
        const layers = Array.from(stage.current?.querySelectorAll<HTMLImageElement | HTMLVideoElement>('[data-layer-id]') ?? [])
        const ready = base?.complete && base.naturalWidth && layers.every(layer => layer instanceof HTMLVideoElement ? layer.readyState >= 2 && !layer.seeking : layer.complete && layer.naturalWidth > 0)
        if (target && base && ready && target.dataset.frame !== String(frameRef.current)) {
          const context = target.getContext('2d', { willReadFrequently: true })!, part = patch.getContext('2d', { willReadFrequently: true })!
          context.drawImage(base, 0, 0, target.width, target.height)
          for (const layer of layers) {
            const mask = masks.get(layer.dataset.layerId ?? '')
            if (!mask) continue
            part.clearRect(0, 0, patch.width, patch.height)
            part.globalCompositeOperation = 'source-over'; part.drawImage(layer, 0, 0, patch.width, patch.height)
            part.globalCompositeOperation = 'destination-in'; part.drawImage(mask, 0, 0, patch.width, patch.height)
            context.drawImage(patch, 0, 0)
          }
          target.dataset.frame = String(frameRef.current)
        } // Retain the last valid source while the next take loads or seeks.
        animation = requestAnimationFrame(draw)
      }
      draw()
    }).catch(problem => { if (!disposed) onError(problem instanceof Error ? problem.message : 'Compositing preview failed.') })
    return () => { disposed = true; cancelAnimationFrame(animation) }
  }, [sequence?.id, scene.width, scene.height, onError])
  return <div className="ed-canvas-stage" ref={stage}>
    <img ref={image} className="ed-canonical" src={scene.image_url} alt={`${scene.title} · locked canonical scene`} />
    {sequence?.manifest.tracks.map(track => {
      const event = track.events.find(e => e.start_frame <= frame && frame < e.end_frame)
      return event ? <ActorLayer key={`${sequence.id}:${track.actor}:${event.index}`} sequence={sequence} event={event} frame={frame} playing={playing} rate={Math.max(1, rate)} onError={onError} /> : null
    })}
    <canvas ref={source} width={scene.width} height={scene.height} hidden aria-hidden="true" />
    {sequence ? <AmbienceCanvas pilot={sequence as unknown as Pilot} frame={frame} image={image} video={video} source={source} onError={onError} /> : null}
    <TextureCanvas settings={texture} frame={frame} width={scene.width} height={scene.height} />
    {maskUrl ? <div className="ed-mask-overlay" style={{ maskImage: `url("${maskUrl}")`, WebkitMaskImage: `url("${maskUrl}")` }} aria-label="Motion area overlay; highlighted pixels may animate" /> : null}
  </div>
}
