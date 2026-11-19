import { useEffect, useRef, useState } from 'react'
import type { AuditionAudio, AuditionVideo } from './filmEdits'

/** Plays a take in context: the end of the outgoing shot, the take with its sound, the start of the incoming shot.
 *  Its own player (not the Canvas transport). It changes nothing in the sequence. Times are frames at 24 fps. */
export interface AuditionProps {
  title: string
  note: string
  video: AuditionVideo[]
  audio: AuditionAudio[]
  length: number
  takeStart: number
  takeFrames: number
  mediaFor: (assetId: string, kind: 'video' | 'audio') => string | undefined
  volume: number
  onClose: () => void
}
const FPS = 24
const PART_LABEL = { outgoing: 'Outgoing', take: 'Take', incoming: 'Incoming' } as const

export default function AuditionPlayer({ title, note, video, audio, length, takeStart, takeFrames, mediaFor, volume, onClose }: AuditionProps) {
  const [playing, setPlaying] = useState(false)
  const [frame, setFrame] = useState(0)
  const videos = useRef<(HTMLVideoElement | null)[]>([])
  const audios = useRef<(HTMLAudioElement | null)[]>([])
  const clock = useRef<{ wall: number; frame: number } | null>(null)
  const dialog = useRef<HTMLDivElement>(null)
  const active = video.findIndex(v => frame >= v.start && frame < v.start + v.frames)

  /** Put every element where it should be at `f`; play the ones in range if `run`. */
  function sync(f: number, run: boolean, force: boolean) {
    video.forEach((seg, i) => {
      const el = videos.current[i]; if (!el || !seg.assetId) return
      const inside = f >= seg.start && f < seg.start + seg.frames
      const want = (seg.sourceIn + Math.max(0, f - seg.start)) / FPS + 0.001
      if (!inside) { if (!el.paused) el.pause(); if (force || f < seg.start) el.currentTime = seg.sourceIn / FPS + 0.001; return }
      if (force || Math.abs(el.currentTime - want) > 0.12) el.currentTime = want
      if (run && el.paused) void el.play().catch(() => {}); if (!run && !el.paused) el.pause()
    })
    audio.forEach((seg, i) => {
      const el = audios.current[i]; if (!el) return
      el.volume = Math.max(0, Math.min(1, 10 ** (seg.gainDb / 20) * volume))
      const inside = f >= seg.start && f < seg.start + seg.frames
      if (!inside || !run) { if (!el.paused) el.pause(); if (!inside) return }
      const want = (seg.sourceIn + (f - seg.start)) / FPS
      if (force || Math.abs(el.currentTime - want) > 0.12) el.currentTime = want
      if (run && el.paused) void el.play().catch(() => {})
    })
  }
  function play(from = frame >= length - 1 ? 0 : frame) {
    clock.current = { wall: performance.now(), frame: from }
    setFrame(from); sync(from, true, true); setPlaying(true)
  }
  function pause() { setPlaying(false); clock.current = null; sync(frame, false, false) }
  useEffect(() => {
    if (!playing) return
    let id = 0
    const tick = () => {
      const c = clock.current; if (!c) return
      const f = c.frame + (performance.now() - c.wall) * FPS / 1000
      if (f >= length) { setFrame(length - 1); setPlaying(false); clock.current = null; sync(length - 1, false, false); return }
      setFrame(f); sync(f, true, false); id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [playing]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { dialog.current?.focus(); const t = window.setTimeout(() => play(0), 150); return () => clearTimeout(t) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const hide = () => { if (document.hidden) pause() }; document.addEventListener('visibilitychange', hide); return () => document.removeEventListener('visibilitychange', hide) })
  useEffect(() => () => { videos.current.forEach(v => v?.pause()); audios.current.forEach(a => a?.pause()) }, [])
  const pct = (f: number) => `${100 * f / Math.max(1, length)}%`
  const seekTo = (f: number) => { const g = Math.max(0, Math.min(length - 1, f)); if (playing) play(g); else { setFrame(g); sync(g, false, true) } }
  return <div className="audition-backdrop" onMouseDown={onClose}>
    <div ref={dialog} tabIndex={-1} role="dialog" aria-label={`Audition ${title} in context`} className="audition" onMouseDown={e => e.stopPropagation()}
      onKeyDown={e => {
        e.stopPropagation() // keep editor shortcuts out while auditioning
        if (e.key === 'Escape') { e.preventDefault(); onClose() }
        // Move focus off a focused button first, or its own Space activation on key-up would toggle straight back.
        else if (e.key === ' ') { e.preventDefault(); if (document.activeElement !== dialog.current) dialog.current?.focus(); if (playing) pause(); else play() }
      }}>
      <header><strong>Audition in context</strong><span>{title}</span><button aria-label="Close audition" title="Close (Esc)" onClick={onClose}>×</button></header>
      <div className="audition-stage">
        {video.map((seg, i) => seg.assetId
          ? <video key={i} ref={el => { videos.current[i] = el }} src={mediaFor(seg.assetId, 'video')} muted playsInline preload="auto" hidden={i !== (active < 0 ? 0 : active)} />
          : <div key={i} className="audition-black" hidden={i !== active}>Gap (black)</div>)}
        {audio.map((seg, i) => <audio key={i} ref={el => { audios.current[i] = el }} src={mediaFor(seg.assetId, 'audio')} preload="auto" />)}
        <span className="audition-part">{active >= 0 ? PART_LABEL[video[active].part] : ''}</span>
      </div>
      <div className="audition-bar" onMouseDown={e => { const r = e.currentTarget.getBoundingClientRect(); seekTo(Math.round((e.clientX - r.left) / r.width * length)) }}>
        <i className="audition-take" style={{ left: pct(takeStart), width: pct(takeFrames) }} />
        <i className="audition-head" style={{ left: pct(frame) }} />
        <small style={{ left: 0 }}>Outgoing</small><small style={{ left: pct(takeStart) }}>Take</small><small style={{ left: pct(takeStart + takeFrames) }}>Incoming</small>
      </div>
      <div className="film-actions">
        <button className="ed-primary" onClick={() => { if (playing) pause(); else play(); dialog.current?.focus() }}>{playing ? 'Pause' : 'Play'}</button>
        <button onClick={() => { play(0); dialog.current?.focus() }}>Restart</button>
        <span className="audition-time">{(frame / FPS).toFixed(2)} / {(length / FPS).toFixed(2)}s</span>
      </div>
      <p className="audition-note">{note} Nothing is placed until you click Place.</p>
    </div>
  </div>
}
