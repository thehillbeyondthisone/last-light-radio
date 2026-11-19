import { useEffect, useRef, useState } from 'react'

/** Poster-frame thumbnails, captured in the browser from a take's own media and cached.
 *  One hidden <video> and one canvas, one capture at a time (browsers limit live media elements). */
const W = 96, H = 54, KEY = 'llr.film.thumbs.v1', CAP = 300
type Entry = { url: string; at: number }
const memory = new Map<string, string>()
let stored: Record<string, Entry> = {}
try { stored = JSON.parse(localStorage.getItem(KEY) ?? '{}') ?? {} } catch { stored = {} }
for (const [k, v] of Object.entries(stored)) if (v && typeof v.url === 'string') memory.set(k, v.url)
/** Keep the stored cache small (it shares localStorage with take flags): at most ~400k characters, oldest dropped first,
 *  written at most once a second. The in-memory cache is unlimited for this session. */
const MAX_CHARS = 400_000
let saveTimer = 0
function persist(key: string, url: string) {
  stored[key] = { url, at: Date.now() }
  if (saveTimer) return
  saveTimer = window.setTimeout(() => {
    saveTimer = 0
    const keys = Object.keys(stored).sort((a, b) => stored[b].at - stored[a].at)
    let size = 0; const keep: Record<string, Entry> = {}
    for (const k of keys.slice(0, CAP)) { size += stored[k].url.length + k.length + 20; if (size > MAX_CHARS) break; keep[k] = stored[k] }
    stored = keep
    try { localStorage.setItem(KEY, JSON.stringify(stored)) } catch { try { localStorage.removeItem(KEY) } catch { /* storage unavailable */ } }
  }, 1000)
}
type Job = { key: string; src: string; frame: number; done: (url: string | null) => void }
const queue: Job[] = []
const waiting = new Map<string, ((url: string | null) => void)[]>()
let busy = false, video: HTMLVideoElement | null = null, canvas: HTMLCanvasElement | null = null
function next() {
  if (busy) return
  const job = queue.shift(); if (!job) return
  busy = true
  video ??= Object.assign(document.createElement('video'), { muted: true, preload: 'auto', playsInline: true })
  canvas ??= Object.assign(document.createElement('canvas'), { width: W, height: H })
  const v = video, c = canvas
  let finished = false
  const finish = (url: string | null) => { if (finished) return; finished = true; v.onseeked = v.onerror = v.onloadedmetadata = null; busy = false; job.done(url); next() }
  const timer = window.setTimeout(() => finish(null), 8000)
  v.onerror = () => { clearTimeout(timer); finish(null) }
  v.onseeked = () => {
    clearTimeout(timer)
    try {
      const ctx = c.getContext('2d')!; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H)
      const s = Math.min(W / (v.videoWidth || W), H / (v.videoHeight || H)), w = (v.videoWidth || W) * s, h = (v.videoHeight || H) * s
      ctx.drawImage(v, (W - w) / 2, (H - h) / 2, w, h)
      finish(c.toDataURL('image/jpeg', 0.7))
    } catch { finish(null) }
  }
  const seek = () => { v.currentTime = Math.max(0, job.frame) / 24 + 0.001 }
  if (v.src.endsWith(job.src) && v.readyState >= 1) seek()
  else { v.onloadedmetadata = seek; v.src = job.src }
}
/** Ask for a thumbnail; resolves from cache at once when it can. */
export function requestThumb(src: string, frame: number, key: string): Promise<string | null> {
  const hit = memory.get(key); if (hit) return Promise.resolve(hit)
  return new Promise(resolve => {
    const list = waiting.get(key)
    if (list) { list.push(resolve); return }
    waiting.set(key, [resolve])
    queue.push({ key, src, frame, done: url => { if (url) { memory.set(key, url); persist(key, url) } (waiting.get(key) ?? []).forEach(r => r(url)); waiting.delete(key) } })
    next()
  })
}
/** Drop captures nobody is waiting for any more (for example after switching sequence). */
export function clearThumbQueue() { queue.length = 0 }
/** Thumbnail for an element: captured only once the element is on screen. */
export function useThumb(src: string | undefined, frame: number, key: string, enabled = true) {
  const ref = useRef<HTMLElement | null>(null)
  const [url, setUrl] = useState<string | undefined>(() => memory.get(key))
  useEffect(() => {
    setUrl(memory.get(key))
    if (!src || !enabled || memory.has(key)) return
    const el = ref.current; if (!el) return
    let live = true
    const io = new IntersectionObserver(entries => {
      if (!entries.some(e => e.isIntersecting)) return
      io.disconnect()
      void requestThumb(src, frame, key).then(u => { if (live && u) setUrl(u) })
    })
    io.observe(el)
    return () => { live = false; io.disconnect() }
  }, [src, frame, key, enabled])
  return { ref, url }
}
