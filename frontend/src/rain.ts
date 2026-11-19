import type { AmbienceLayer } from './types'
import { drawWetGlass } from './wetGlass'

// Analytic geometry and optics match last_light_radio/rain.py. Saved particles
// are the only source of variation; seeking and cuts never reseed the weather.
const modulo = (value: number, period: number) => ((value % period) + period) % period
const glint = (r: number, g: number, b: number) => r > g * 1.18 && r > b * 0.95 ? '242,210,162' : '167,202,224'

export function drawRain(part: CanvasRenderingContext2D, source: CanvasImageSource, layer: AmbienceLayer, seconds: number) {
  const [left, top, right, bottom] = layer.bounds
  const width = right - left, height = bottom - top, strength = layer.opacity
  if (!strength) return
  part.drawImage(source, left, top, width, height, 0, 0, width, height)
  const pixels = part.getImageData(0, 0, width, height).data
  const colorAt = (x: number, y: number) => {
    const offset = (Math.min(height - 1, Math.max(0, Math.floor(y))) * width + Math.min(width - 1, Math.max(0, Math.floor(x)))) * 4
    return glint(pixels[offset], pixels[offset + 1], pixels[offset + 2])
  }
  const wind = 0.055 * seconds + 0.045 * Math.sin(seconds * 0.43) + 0.018 * Math.sin(seconds * 0.91)
  const slant = 0.07 + 0.05 * Math.sin(seconds * 0.43) + 0.03 * Math.sin(seconds * 0.91)
  part.lineCap = 'butt'
  const fades = [0.10, 0.28, 0.58, 1]
  layer.particles.forEach((p) => {
    const depth = p.depth ?? 0
    const x = (modulo(p.x + wind * p.speed + 0.003 * Math.sin(seconds * 0.7 + p.phase), 1.16) - 0.08) * width
    const y = (modulo(p.y + seconds * p.speed, 1.2) - 0.1) * height
    const length = Math.max(2, p.length * height), dx = length * slant
    if (x < -8 || x > width + 8 || y < 0 || y - length > height) return
    const alpha = strength * p.alpha * (0.78 + 0.22 * Math.sin(seconds * 0.8 + p.phase)), color = colorAt(x, y)
    part.lineWidth = Math.max(0.65, width / 1027 * [0.7, 1.05, 1.65][depth])
    fades.forEach((fade, segment) => {
      const a = segment / 4, b = (segment + 1) / 4
      part.strokeStyle = `rgba(${color},${alpha * fade})`; part.beginPath()
      part.moveTo(x - dx * (1 - a), y - length * (1 - a)); part.lineTo(x - dx * (1 - b), y - length * (1 - b)); part.stroke()
    })
  })
  if (layer.glass_model === 'adhesion-release-v1') {
    drawWetGlass(part, source, layer, seconds, colorAt)
    return
  }
  layer.glass?.forEach((p) => {
    const progress = p.y + seconds * p.speed + (p.speed ? 0.002 * Math.sin(seconds * 1.3 + p.phase) : 0)
    const y = (modulo(progress, 1.2) - 0.1) * height
    const x = p.x * width + width * 0.0008 * Math.sin(y / height * 18 + p.phase)
    const rx = Math.max(0.8, p.radius * width), ry = rx * (p.speed ? 1.5 : 1.18)
    if (x - rx < 0 || x + rx >= width || y - ry < 0 || y + ry >= height) return
    const color = colorAt(x, y), opacity = Math.min(1, strength / 0.22) * p.alpha
    if (p.trail) {
      const length = p.trail * height
      part.lineWidth = Math.max(1, Math.round(rx * 0.45))
      for (let segment = 0; segment < 8; segment++) {
        const a = segment / 8, b = (segment + 1) / 8, ya = y - length * (1 - a), yb = y - length * (1 - b)
        const xa = x + width * 0.0008 * (Math.sin(ya / height * 18 + p.phase) - Math.sin(y / height * 18 + p.phase))
        const xb = x + width * 0.0008 * (Math.sin(yb / height * 18 + p.phase) - Math.sin(y / height * 18 + p.phase))
        part.strokeStyle = `rgba(${color},${20 / 255 * opacity * b})`; part.beginPath(); part.moveTo(xa, ya); part.lineTo(xb, yb); part.stroke()
      }
    }
    const bx = Math.floor(x - rx), by = Math.floor(y - ry), bw = Math.ceil(x + rx) - bx, bh = Math.ceil(y + ry) - by
    part.save(); part.beginPath(); part.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); part.clip()
    part.globalAlpha = 160 / 255 * opacity
    part.drawImage(source, left + x - rx * 1.15, top + y - ry * 0.35, rx * 1.3, ry * 1.3, bx, by, bw, bh)
    part.restore(); part.lineWidth = 1
    part.strokeStyle = `rgba(9,25,36,${95 / 255 * opacity})`; part.beginPath()
    part.ellipse(x, y, rx, ry, 0, 20 * Math.PI / 180, 155 * Math.PI / 180); part.stroke()
    part.strokeStyle = `rgba(${color},${150 / 255 * opacity})`; part.beginPath()
    part.ellipse(x, y - ry * 0.125, rx * 0.75, ry * 0.725, 0, 205 * Math.PI / 180, 285 * Math.PI / 180); part.stroke()
    if (rx > 2) { part.fillStyle = `rgba(225,237,237,${190 / 255 * opacity})`; part.fillRect(Math.round(x - rx * 0.3), Math.round(y - ry * 0.5), 1, 1) }
  })
}
