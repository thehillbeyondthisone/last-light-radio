import { useEffect, useRef } from 'react'
import { api } from './api'
import type { AudioAsset, AudioPlacement } from './editorTypes'

type Voice = { media: HTMLAudioElement; node: MediaElementAudioSourceNode; gain: GainNode; pending: boolean }
/** Bounded streaming preview. Video is the clock; offline export remains frame exact. */
export function useProgramAudio(tracks: AudioPlacement[], clock: () => number | null, onError: (message: string) => void) {
  const context = useRef<AudioContext | null>(null)
  const voices = useRef(new Map<string, Voice>())
  const frame = useRef(0)
  const latest = useRef({ tracks, clock, onError })
  latest.current = { tracks, clock, onError }
  const generation = useRef(0)
  /** Monitor volume (0..1): a master gain after every placement's own gain, so the saved mix is untouched. */
  const master = useRef<GainNode | null>(null)
  const masterLevel = useRef(1)
  function setVolume(level: number) { masterLevel.current = level; if (master.current) master.current.gain.value = level }
  function stop() {
    generation.current++
    clearTimeout(frame.current)
    voices.current.forEach(v => { v.media.pause(); v.gain.gain.value = 0 })
  }
  function clear() {
    voices.current.forEach(v => { v.media.pause(); v.media.removeAttribute('src'); v.media.load(); v.media.remove(); v.node.disconnect(); v.gain.disconnect() })
    voices.current.clear()
  }
  async function start() {
    stop()
    const token = generation.current
    // Resume inside the Play button's gesture, before any network await.
    const ctx = context.current ?? (context.current = new AudioContext())
    await ctx.resume()
    if (ctx.state !== 'running') throw new Error('Browser audio is suspended. Click Play sequence again to enable sound.')
    if (!master.current) { master.current = ctx.createGain(); master.current.connect(ctx.destination) }
    master.current.gain.value = masterLevel.current
    const enabled = latest.current.tracks.filter(t => t.enabled)
    if (enabled.length > 32) throw new Error('Browser preview supports up to 32 enabled audio placements. Export can render the full mix.')
    const catalog = enabled.length ? await api<{ assets: AudioAsset[] }>('audio') : { assets: [] }
    if (generation.current !== token) return false
    clear()
    for (const t of enabled) {
      const a = catalog.assets.find(a => a.id === t.asset_id && a.status === 'approved')
      if (!a) throw new Error('An audio placement is missing or not approved. Review it in Sound & music.')
      const media = new Audio(a.media_url)
      media.preload = 'auto'
      media.hidden = true; media.dataset.timelinePreview = t.id; media.setAttribute('aria-label', 'Timeline audio preview'); document.body.appendChild(media)
      const node = ctx.createMediaElementSource(media), gain = ctx.createGain()
      gain.gain.value = 0; node.connect(gain); gain.connect(master.current)
      const v = { media, node, gain, pending: false }
      media.onerror = () => { if (generation.current === token) { stop(); latest.current.onError('A timeline audio source could not load. Check Sound & music and try again.') } }
      voices.current.set(t.id, v)
    }
    function tick() {
      if (generation.current !== token) return
      const at = latest.current.clock()
      for (const t of enabled) {
        const v = voices.current.get(t.id)!
        const elapsed = at === null ? -1 : at - t.start_frame
        if (elapsed < 0 || elapsed >= t.duration_frames) { v.media.pause(); v.gain.gain.value = 0; continue }
        const target = (t.source_in_frame + elapsed) / 24
        if (v.media.readyState < 1) continue
        if (v.media.paused || Math.abs(v.media.currentTime - target) > 0.10) v.media.currentTime = target
        const fadeIn = t.fade_in_frames ? Math.min(1, elapsed / t.fade_in_frames) : 1
        const fadeOut = t.fade_out_frames ? Math.min(1, (t.duration_frames - elapsed) / t.fade_out_frames) : 1
        const level = 10 ** (t.gain_db / 20) * Math.min(fadeIn, fadeOut)
        v.media.dataset.previewGain = String(level)
        v.gain.gain.setTargetAtTime(level, ctx.currentTime, 0.008)
        if (v.media.paused && !v.pending) {
          v.pending = true
          void v.media.play().then(() => { if (generation.current !== token) v.media.pause() }).catch(e => {
            if (generation.current === token && e.name !== 'AbortError') { stop(); latest.current.onError(`Audio preview could not start: ${e.message}`) }
          }).finally(() => { v.pending = false })
        }
      }
      frame.current = window.setTimeout(tick, 25)
    }
    frame.current = window.setTimeout(tick, 25)
    return true
  }
  useEffect(() => () => { stop(); clear(); void context.current?.close() }, [])
  return { start, stop, setVolume }
}


