import type { AmbienceLayer, GlassDrop } from './types'

const modulo = (value: number, period: number) => ((value % period) + period) % period

// Keep these curves identical to wet_glass.py, including trail history. Their
// source is the pinned recipe, so every seek can evaluate a frame directly.
function state(p: GlassDrop, seconds: number, width: number, height: number) {
  if (!p.roll) {
    const progress = p.y + seconds * p.speed + (p.speed ? 0.002 * Math.sin(seconds * 1.3 + p.phase) : 0)
    const y = (modulo(progress, 1.2) - 0.1) * height, rx = Math.max(0.8, p.radius * width)
    return {x:p.x * width + width * 0.0008 * Math.sin(y / height * 18 + p.phase), y, rx, ry:rx * (p.speed ? 1.5 : 1.18), age:0}
  }
  const roll = p.roll, age = modulo(seconds + roll.offset, roll.duration)
  let progress = 0, velocity = 0
  for (let index = 0; index < roll.keys.length - 1; index++) {
    const [t0, y0] = roll.keys[index], [t1, y1] = roll.keys[index + 1]
    if (age <= t1) {
      const u = (age - t0) / (t1 - t0)
      progress = y0 + (y1 - y0) * u * u * (3 - 2 * u)
      velocity = (y1 - y0) * 6 * u * (1 - u) / (t1 - t0)
      break
    }
  }
  const stretch = Math.min(0.9, velocity * 4), radius = Math.max(0.8, p.radius * width)
  return {x:p.x * width + width * roll.wander * (Math.sin(progress * 9 + p.phase) + 0.35 * Math.sin(progress * 23 + p.phase * 1.7)),
    y:(progress * 1.24 - 0.12) * height, rx:radius / (1 + stretch * 0.22), ry:radius * (1.12 + stretch * 0.85), age}
}

export function drawWetGlass(part: CanvasRenderingContext2D, source: CanvasImageSource, layer: AmbienceLayer, seconds: number, colorAt: (x:number, y:number)=>string) {
  const [left, top, right, bottom] = layer.bounds, width = right - left, height = bottom - top
  const drops = (layer.glass ?? []).map(p => ({p, ...state(p, seconds, width, height)}))
    .filter(d => d.x - d.rx >= 0 && d.x + d.rx < width && d.y - d.ry >= 0 && d.y + d.ry < height)
  drops.forEach(({p, x, y, rx, age}) => {
    if (!p.roll) return
    const opacity = Math.min(1, layer.opacity / 0.22) * p.alpha, color = colorAt(x, y)
    let lastX = x, lastY = y
    part.lineWidth = Math.max(1, Math.round(rx * 0.24))
    for (let index = 1; index <= 24; index++) {
      const lag = index / 24 * p.roll.trail_seconds
      if (lag > age) break
      const past = state(p, seconds - lag, width, height)
      if (Math.hypot(lastX - past.x, lastY - past.y) < 0.65) continue
      const fade = (1 - index / 25) ** 1.5
      part.strokeStyle = `rgba(${color},${42 / 255 * opacity * fade})`; part.beginPath()
      part.moveTo(lastX, lastY); part.lineTo(past.x, past.y); part.stroke()
      lastX = past.x; lastY = past.y
    }
  })
  drops.forEach(({p, x, y, rx, ry}) => {
    const opacity = Math.min(1, layer.opacity / 0.22) * p.alpha, color = colorAt(x, y)
    const bx = Math.floor(x - rx - 1), by = Math.floor(y - ry - 1), bw = Math.ceil(x + rx + 1) - bx, bh = Math.ceil(y + ry + 1) - by
    const shape = () => {
      part.beginPath()
      for (let index = 0; index <= 48; index++) {
        const a = index / 48 * Math.PI * 2, vertical = Math.sin(a)
        const px = x + Math.cos(a) * rx * (0.82 + 0.18 * vertical), py = y + vertical * ry
        if (index === 0) part.moveTo(px, py); else part.lineTo(px, py)
      }
      part.closePath()
    }
    part.save(); shape(); part.clip(); part.globalAlpha = 210 / 255 * opacity
    for (let row = 0; row < bh; row += 2) {
      const band = Math.min(2, bh - row), cy = y - by, v = (row + band / 2 - cy) / ry
      const magnify = 0.58 + 0.13 * Math.min(1, Math.abs(v))
      const sx = x - bw * magnify / 2 - rx * 0.28 * (1 - Math.min(1, v * v)), sy = y + (row - cy) * 0.7 + ry * 0.24
      const sx0 = Math.floor(sx), sy0 = Math.floor(sy)
      part.drawImage(source, left + sx0, top + sy0, Math.ceil(sx + bw * magnify) - sx0, Math.ceil(sy + band * 0.7) - sy0, bx, by + row, bw, band)
    }
    part.restore(); part.lineWidth = 1
    const arc = (start: number, end: number, color: string, inset = 1) => {
      part.beginPath()
      for (let index = 0; index < 18; index++) {
        const a = (start + (end - start) * index / 17) * Math.PI / 180, v = Math.sin(a)
        const px = x + Math.cos(a) * rx * (0.82 + 0.18 * v) * inset, py = y + v * ry * inset
        if (index === 0) part.moveTo(px, py); else part.lineTo(px, py)
      }
      part.strokeStyle = color; part.stroke()
    }
    arc(10, 160, `rgba(8,21,30,${125 / 255 * opacity})`)
    arc(205, 282, `rgba(${color},${180 / 255 * opacity})`, 0.88)
    arc(47, 112, `rgba(${color},${80 / 255 * opacity})`, 0.65)
    if (rx > 3) {
      part.fillStyle = `rgba(230,241,242,${205 / 255 * opacity})`; part.beginPath()
      part.ellipse(x - rx * 0.28, y - ry * 0.58, 0.5, 0.5, 0, 0, Math.PI * 2); part.fill()
    }
  })
}
