import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { Pilot } from './types'
import { drawRain } from './rain'

// Preview the pinned procedural recipe at the same absolute frame as export.
// Canvas and Pillow rasterize strokes differently; the exported MP4 is final.
export default function AmbienceCanvas({ pilot, frame, image, video, source: compositeSource, onError }: {
  pilot: Pilot; frame: number; image: RefObject<HTMLImageElement | null>; video: RefObject<HTMLVideoElement | null>; source?: RefObject<HTMLCanvasElement | null>; onError: (message: string) => void
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const frameRef = useRef(frame)
  useEffect(() => { frameRef.current = frame }, [frame])
  const recipe = pilot.manifest.ambience
  useEffect(() => {
    if (!recipe) return
    if (!['masked-ambience-v1', 'masked-ambience-v2', 'masked-ambience-v3'].includes(recipe.renderer_version)) { onError('The saved ambience renderer is unavailable.'); return }
    if (recipe.renderer_version === 'masked-ambience-v3' && recipe.layers.some(layer => layer.kind === 'rain' && layer.glass_model !== 'adhesion-release-v1')) { onError('The saved glass-motion model is unavailable.'); return }
    let disposed = false, animation = 0, lastFrame = -1
    let lastSource: CanvasImageSource | null = null
    let lastPreparedFrame: string | undefined
    const masks = recipe.layers.map((layer) => {
      const bitmap = new Image()
      const mask = document.createElement('canvas')
      return new Promise<HTMLCanvasElement>((resolve, reject) => {
        bitmap.onload = () => {
          mask.width = bitmap.width; mask.height = bitmap.height
          const context = mask.getContext('2d')!
          context.drawImage(bitmap, 0, 0)
          const pixels = context.getImageData(0, 0, mask.width, mask.height)
          for (let i = 0; i < pixels.data.length; i += 4) pixels.data[i + 3] = pixels.data[i]
          context.putImageData(pixels, 0, 0); resolve(mask)
        }
        bitmap.onerror = () => reject(new Error(`Could not load the saved ${layer.label.toLowerCase()} mask.`))
        bitmap.src = `/api/pilots/${pilot.id}/ambience/${layer.kind}`
      })
    })
    const patch = document.createElement('canvas')
    void Promise.all(masks).then((loaded) => {
      const draw = () => {
        if (disposed) return
        const target = canvas.current, source = compositeSource?.current ?? video.current ?? image.current
        const ready = source instanceof HTMLCanvasElement ? source.width > 0 && source.dataset.frame !== undefined : source instanceof HTMLVideoElement ? source.readyState >= 2 : source?.complete && source.naturalWidth > 0
        // Weather uses episode time even while a character decoder is buffering.
        // The retained source is safe: rain excludes the pinned subject regions,
        // and fixed-plume steam is suppressed during interaction actions.
        const preparedFrame = source instanceof HTMLCanvasElement ? source.dataset.frame : undefined
        if (target && source && ready && (lastFrame !== frameRef.current || lastSource !== source || lastPreparedFrame !== preparedFrame)) {
          const context = target.getContext('2d')!
          context.clearRect(0, 0, target.width, target.height)
          const seconds = frameRef.current / pilot.manifest.fps
          recipe.layers.forEach((layer, index) => {
            if (layer.kind === 'steam' && pilot.manifest.steam_pauses?.some(([start, end]) => start <= frameRef.current && frameRef.current < end)) return
            const [left, top, right, bottom] = layer.bounds
            const width = right - left, height = bottom - top
            patch.width = width; patch.height = height
            const part = patch.getContext('2d', { willReadFrequently: true })!
            if (layer.opacity === 0) return
            if (layer.kind === 'rain' && recipe.renderer_version !== 'masked-ambience-v1') {
              drawRain(part, source, layer, seconds)
            } else if (layer.kind === 'rain') {
              layer.particles.forEach((p) => {
                const x = p.x * width, y = ((p.y + seconds * p.speed) % 1) * height, length = p.length * height
                part.strokeStyle = `rgba(186,207,220,${layer.opacity * p.alpha})`
                part.lineWidth = Math.max(1, Math.round(width / 850)); part.beginPath()
                part.moveTo(x - length * 0.06, y - length); part.lineTo(x, y); part.stroke()
              })
            } else {
              part.imageSmoothingEnabled = false
              const phase = layer.particles[0].phase
              for (let row = 0; row < height; row++) {
                const u = 1 - row / height
                const wave = Math.sin(seconds * 0.85 - u * 5 + phase) + 0.35 * Math.sin(seconds * 0.39 + u * 8 + phase)
                const shift = Math.floor(width * 0.055 * layer.opacity / 0.18 * Math.sin(Math.PI * u) ** 1.2 * wave + 0.5)
                part.drawImage(source, left + shift, top + row, width, 1, 0, row, width, 1)
              }
            }
            part.globalCompositeOperation = 'destination-in'
            part.drawImage(loaded[index], left, top, width, height, 0, 0, width, height)
            context.drawImage(patch, left, top)
          })
          lastFrame = frameRef.current; lastSource = source; lastPreparedFrame = preparedFrame; target.dataset.frame = String(lastFrame)
        }
        animation = requestAnimationFrame(draw)
      }
      draw()
    }).catch((error) => { if (!disposed) onError(error instanceof Error ? error.message : 'Ambience preview failed.') })
    return () => { disposed = true; cancelAnimationFrame(animation) }
    // A pilot ID pins this immutable recipe; progress updates do not reload masks.
  }, [pilot.id, recipe?.renderer_version, image, video, compositeSource, onError])
  return recipe ? <canvas ref={canvas} className="ambience-canvas" width={pilot.manifest.width} height={pilot.manifest.height} aria-label="Continuous rain and steam preview" /> : null
}
