import { useEffect, useRef } from 'react'
import type { TextureSettings } from './editorTypes'
import { TEXTURE_TILE, textureOffset, textureTile } from './videoTexture'

export const DEFAULT_TEXTURE: TextureSettings = { enabled: false, strength: 0.2, size: 1, seed: 7 }

export default function TextureCanvas({ settings, frame, width, height }: { settings?: TextureSettings; frame: number; width: number; height: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const pattern = useRef<HTMLCanvasElement | null>(null)
  const value = settings ?? DEFAULT_TEXTURE
  useEffect(() => {
    const tile = document.createElement('canvas')
    tile.width = tile.height = TEXTURE_TILE
    tile.getContext('2d')!.putImageData(new ImageData(textureTile(value.seed), TEXTURE_TILE, TEXTURE_TILE), 0, 0)
    pattern.current = tile
  }, [value.seed])
  useEffect(() => {
    const target = canvas.current, tile = pattern.current
    if (!target || !tile) return
    const context = target.getContext('2d')!
    context.clearRect(0, 0, width, height)
    if (!value.enabled || value.strength === 0) return
    const [x, y] = textureOffset(value.seed, frame)
    const grain = context.createPattern(tile, 'repeat')!
    grain.setTransform(new DOMMatrix().translate(-x * value.size, -y * value.size).scale(value.size))
    context.imageSmoothingEnabled = false
    context.fillStyle = grain
    context.fillRect(0, 0, width, height)
    target.dataset.frame = String(frame)
  }, [frame, width, height, value.enabled, value.strength, value.size, value.seed])
  return <canvas ref={canvas} className="ed-texture-canvas" width={width} height={height} style={{ opacity: value.enabled ? value.strength : 0 }} aria-label="Video texture preview" />
}
