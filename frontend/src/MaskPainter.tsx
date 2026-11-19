import { useEffect, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import type { ActorCrop, Scene } from './types'

type Point = [number, number]
type Tool = 'box' | 'include' | 'protect'
type Props = { scene: Scene; imageUrl?: string; initialMaskUrl?: string; boundary?: ActorCrop; onChange: (mask: string) => void; onDirty?: () => void }

export default function MaskPainter({ scene, imageUrl, initialMaskUrl, boundary, onChange, onDirty }: Props) {
  const display = useRef<HTMLCanvasElement>(null)
  const layer = useRef<HTMLCanvasElement | null>(null)
  const drag = useRef<{ from: Point; last: Point } | null>(null)
  const history = useRef<string[]>([])
  const [undoCount, setUndoCount] = useState(0)
  const [tool, setTool] = useState<Tool>(initialMaskUrl ? 'include' : 'box')
  const [brush, setBrush] = useState(Math.round(Math.max(scene.width, scene.height) / 25))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [box, setBox] = useState({ x: boundary?.x ?? 0, y: boundary?.y ?? 0, width: Math.round((boundary?.width ?? scene.width) / 3), height: Math.round((boundary?.height ?? scene.height) / 2) })
  const limit = boundary ?? { x: 0, y: 0, width: scene.width, height: scene.height }

  function redraw(preview?: { from: Point; to: Point }) {
    const ctx = display.current?.getContext('2d')
    if (!ctx || !layer.current) return
    ctx.clearRect(0, 0, scene.width, scene.height)
    ctx.drawImage(layer.current, 0, 0)
    ctx.globalCompositeOperation = 'source-in'; ctx.fillStyle = '#e4bb526e'; ctx.fillRect(0, 0, scene.width, scene.height)
    ctx.globalCompositeOperation = 'source-over'
    if (boundary) { ctx.strokeStyle = '#fff4bf'; ctx.lineWidth = Math.max(2, scene.width / 500); ctx.setLineDash([12, 10]); ctx.strokeRect(boundary.x, boundary.y, boundary.width, boundary.height); ctx.setLineDash([]) }
    if (preview) { ctx.fillStyle = '#e4bb526e'; ctx.strokeStyle = '#fff4bf'; ctx.lineWidth = 2; ctx.fillRect(preview.from[0], preview.from[1], preview.to[0] - preview.from[0], preview.to[1] - preview.from[1]); ctx.strokeRect(preview.from[0], preview.from[1], preview.to[0] - preview.from[0], preview.to[1] - preview.from[1]) }
  }
  function exportMask() { if (layer.current) onChange(layer.current.toDataURL('image/png').split(',')[1]) }
  function remember() { if (layer.current) { history.current = [...history.current.slice(-19), layer.current.toDataURL('image/png')]; setUndoCount(history.current.length) } }
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(''); history.current = []; setUndoCount(0)
    const canvas = document.createElement('canvas'); canvas.width = scene.width; canvas.height = scene.height
    const ctx = canvas.getContext('2d')!
    function ready() {
      if (cancelled) return
      layer.current = canvas
      redraw(); onChange(canvas.toDataURL('image/png').split(',')[1]); setLoading(false)
    }
    if (initialMaskUrl) {
      const image = new Image()
      image.onload = () => {
        if (cancelled) return
        if (image.naturalWidth !== scene.width || image.naturalHeight !== scene.height) { setError('This area does not match the scene.'); setLoading(false); return }
        ctx.drawImage(image, 0, 0)
        const pixels = ctx.getImageData(0, 0, scene.width, scene.height)
        for (let i = 0; i < pixels.data.length; i += 4) {
          const x = (i / 4) % scene.width; const y = Math.floor(i / 4 / scene.width)
          const outside = boundary && (x < boundary.x || y < boundary.y || x >= boundary.x + boundary.width || y >= boundary.y + boundary.height)
          const alpha = outside ? 0 : Math.round(pixels.data[i] * pixels.data[i + 3] / 255)
          pixels.data[i] = 255; pixels.data[i + 1] = 255; pixels.data[i + 2] = 255; pixels.data[i + 3] = alpha
        }
        ctx.putImageData(pixels, 0, 0); ready()
      }
      image.onerror = () => { if (!cancelled) { setError('The saved motion area could not be loaded.'); setLoading(false) } }
      image.src = initialMaskUrl
    } else ready()
    return () => { cancelled = true; drag.current = null }
    // Selection is reloaded only when its saved source changes, not on each stroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.id, scene.width, scene.height, initialMaskUrl, boundary?.x, boundary?.y, boundary?.width, boundary?.height, onChange])

  function position(event: PointerEvent<HTMLCanvasElement>): Point {
    const rect = event.currentTarget.getBoundingClientRect()
    return [Math.max(limit.x, Math.min(limit.x + limit.width - 1, (event.clientX - rect.left) / rect.width * scene.width)), Math.max(limit.y, Math.min(limit.y + limit.height - 1, (event.clientY - rect.top) / rect.height * scene.height))]
  }
  function stroke(a: Point, b: Point) {
    const ctx = layer.current?.getContext('2d'); if (!ctx) return
    ctx.save(); ctx.beginPath(); ctx.rect(limit.x, limit.y, limit.width, limit.height); ctx.clip()
    ctx.globalCompositeOperation = tool === 'protect' ? 'destination-out' : 'source-over'
    ctx.shadowColor = 'white'; ctx.shadowBlur = 4
    ctx.fillStyle = 'white'; ctx.strokeStyle = 'white'; ctx.lineWidth = brush; ctx.lineCap = 'round'; ctx.lineJoin = 'round'
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke()
    ctx.beginPath(); ctx.arc(b[0], b[1], brush / 2, 0, Math.PI * 2); ctx.fill(); ctx.restore(); redraw()
  }
  function applyBox(a: Point, b: Point) {
    const ctx = layer.current?.getContext('2d'); if (!ctx) return
    ctx.save(); ctx.beginPath(); ctx.rect(limit.x, limit.y, limit.width, limit.height); ctx.clip(); ctx.fillStyle = 'white'; ctx.shadowColor = 'white'; ctx.shadowBlur = 4; ctx.fillRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])); ctx.restore(); redraw()
  }
  function down(event: PointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0 || loading || error) return
    remember(); const point = position(event); drag.current = { from: point, last: point }; event.currentTarget.setPointerCapture(event.pointerId)
    if (tool !== 'box') stroke(point, point)
  }
  function move(event: PointerEvent<HTMLCanvasElement>) {
    if (!drag.current) return
    const point = position(event)
    if (tool === 'box') redraw({ from: drag.current.from, to: point })
    else stroke(drag.current.last, point)
    drag.current.last = point
  }
  function up(event: PointerEvent<HTMLCanvasElement>) {
    if (!drag.current) return
    if (tool === 'box') applyBox(drag.current.from, position(event))
    drag.current = null; exportMask(); onDirty?.()
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  async function undo() {
    const saved = history.current.pop(); if (!saved || !layer.current) return
    setLoading(true)
    const image = new Image(); image.onload = () => { const ctx = layer.current!.getContext('2d')!; ctx.clearRect(0, 0, scene.width, scene.height); ctx.drawImage(image, 0, 0); redraw(); exportMask(); onDirty?.(); setUndoCount(history.current.length); setLoading(false) }; image.src = saved
  }
  return <div className="mask-painter">
    <div className="paint-tools" aria-label="Motion area tools">{(['box', 'include', 'protect'] as const).map((item) => <button type="button" key={item} aria-pressed={tool === item} onClick={() => setTool(item)}>{item === 'box' ? 'Draw a box' : item === 'include' ? 'Include' : 'Protect'}</button>)}<button type="button" disabled={!undoCount || loading} onClick={() => void undo()}>Undo</button>{tool !== 'box' ? <label>Brush size<input aria-label="Brush size" type="range" min="4" max={Math.max(20, Math.round(scene.width / 5))} value={brush} onChange={(event) => setBrush(Number(event.target.value))} /></label> : null}</div>
    <div className="paint-stage" style={{ aspectRatio: `${scene.width} / ${scene.height}` }}><img src={imageUrl ?? scene.image_url} alt={`${scene.title} motion area`} /><canvas ref={display} width={scene.width} height={scene.height} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} aria-label="Paint motion area. Draw on the picture or use the keyboard area controls below." /></div>
    <p className="paint-legend"><span />Gold can move. Use Protect to keep nearby subjects still.{boundary ? ' Changes stay inside the dashed frame.' : ''}</p>
    {loading ? <p role="status">Loading the motion area…</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}
    <details className="paint-keyboard"><summary>Set an area with the keyboard</summary><div className="coordinate-fields">{(['x', 'y', 'width', 'height'] as const).map((key) => <label className="field" key={key}>{key}<input type="number" aria-label={`Area ${key}`} value={box[key]} onChange={(event) => setBox({ ...box, [key]: Number(event.target.value) })} min="0" max={Math.max(scene.width, scene.height)} /></label>)}</div><button type="button" className="button light compact" disabled={loading || !!error} onClick={() => { const x = Math.max(limit.x, Math.min(limit.x + limit.width - 2, box.x)); const y = Math.max(limit.y, Math.min(limit.y + limit.height - 2, box.y)); remember(); applyBox([x, y], [Math.min(limit.x + limit.width, x + Math.max(2, box.width)), Math.min(limit.y + limit.height, y + Math.max(2, box.height))]); exportMask(); onDirty?.() }}>Include this area</button></details>
  </div>
}
