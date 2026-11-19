import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { rulerStep } from './workspaceLayout'
import { ZOOM_LEVELS } from './shortcuts'
import type { TrackDensity } from './workspaceLayout'
import type { CSSProperties, DragEvent, PointerEvent } from 'react'
import type { EditorConfig, SubjectEvent, SubjectSequence } from './editorTypes'
import type { IdleBed } from './nestedSequences'
import { idleBeds } from './nestedSequences'
import { timecode } from './editorTypes'

export type SequenceEffect = 'rain' | 'steam' | 'texture'
interface Props {
  config: EditorConfig | null; sequence: SubjectSequence | null; frame: number; scale: number; busy: boolean; dirty: boolean
  selection: string; sceneTitle: string; effects: string[]; nested: IdleBed | null
  layout: 'standard' | 'all-tracks'; trackReset: number; density: TrackDensity; onDensity: (density: TrackDensity) => void
  onScale: (scale: number) => void; onSeek: (frame: number) => void; onNested: (bed: IdleBed | null) => void
  onAudio: () => void; onSubject: (actor: string) => void; onEffect: (effect: SequenceEffect) => void; onEvent: (event: SubjectEvent) => void
  onDrop: (event: DragEvent<HTMLDivElement>, actor: string) => void
  /** Keyboard state: fit-to-window, playback, a pending (unsaved) nudge, In/Out and workspace markers, all in episode frames. */
  fit: boolean; onFit: (fit: boolean) => void; playing: boolean
  nudge: { placement: string; delta: number } | null
  marks: { in?: number; out?: number }; markers: number[]; hints: string
}

export default function SequenceTimeline(p: Props) {
  const start = p.nested?.start_frame ?? 0
  const end = p.nested?.end_frame ?? p.config?.duration_frames ?? 14400
  const scroll = useRef<HTMLDivElement>(null)
  const fitWidth = p.fit
  const [viewportWidth, setViewportWidth] = useState(1000)
  const [visibleTracks, setVisibleTracks] = useState(0)
  const [trackHeights, setTrackHeights] = useState<Record<string, number>>({})
  useEffect(() => { setTrackHeights({}) }, [p.layout, p.trackReset])
  const sizes: TrackDensity[] = ['reduced', 'small', 'standard', 'large']
  const sizeIndex = p.density === 'default' ? 2 : sizes.indexOf(p.density)
  function changeDensity(density: TrackDensity) { setTrackHeights({}); p.onDensity(density) }
  const count = p.nested ? 1 : (p.config?.subjects.length ?? 0) * 2 + p.effects.length + 4
  useEffect(() => {
    const element = scroll.current
    if (!element) return
    function measure() {
      if (!element) return
      const label = element.querySelector('.ed-track-name')?.getBoundingClientRect().width ?? 190
      setViewportWidth(Math.max(1, element.clientWidth - label - 2))
      const bounds = element.getBoundingClientRect()
      const rulerBottom = element.querySelector('.ed-ruler')?.getBoundingClientRect().bottom ?? bounds.top
      setVisibleTracks([...element.querySelectorAll('.ed-track-row:not(.ed-ruler)')].filter(row => {
        const rect = row.getBoundingClientRect()
        return rect.top >= rulerBottom && rect.bottom <= bounds.top + element.clientHeight + 1
      }).length)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    const stack = element.querySelector('.ed-track-stack')
    if (stack) observer.observe(stack)
    element.addEventListener('scroll', measure, { passive: true })
    measure()
    return () => { observer.disconnect(); element.removeEventListener('scroll', measure) }
  }, [count, p.nested, p.density, trackHeights])
  useEffect(() => {
    if (fitWidth) p.onScale(viewportWidth / ((end - start) / 24))
  }, [fitWidth, viewportWidth, end, start, p.onScale])
  const tick = rulerStep(p.scale)
  const width = (end - start) / 24 * p.scale
  const left = (frame: number) => (frame - start) / 24 * p.scale
  const playhead = <i className="ed-playhead" style={{ left: left(p.frame) }} />
  // Zooming keeps the playhead at the same screen position.
  const shownScale = useRef(p.scale)
  useLayoutEffect(() => {
    const element = scroll.current, previous = shownScale.current
    shownScale.current = p.scale
    if (!element || previous === p.scale || fitWidth) return
    const offset = (p.frame - start) / 24 * previous - element.scrollLeft
    element.scrollLeft = Math.max(0, (p.frame - start) / 24 * p.scale - offset)
    // Only a zoom change re-anchors; frame changes are handled by the follow effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.scale])
  // Keyboard navigation and playback keep the playhead in view (page-style while playing).
  useLayoutEffect(() => {
    const element = scroll.current
    if (!element || fitWidth) return
    const x = (p.frame - start) / 24 * p.scale
    if (x < element.scrollLeft || x > element.scrollLeft + viewportWidth - 6) element.scrollLeft = Math.max(0, x - viewportWidth * (p.playing ? 0.04 : 0.5))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.frame, start])
  const markIn = p.marks.in, markOut = p.marks.out
  const inOut = markIn !== undefined || markOut !== undefined ? (() => {
    const a = Math.max(start, markIn ?? start), b = Math.min(end, (markOut ?? end - 1) + 1)
    return b > a ? <i className="ed-inout" style={{ left: left(a), width: Math.max(1, left(b) - left(a)) }} data-in={markIn !== undefined} data-out={markOut !== undefined} /> : null
  })() : null
  const defaultHeight = p.density === 'reduced' ? 12 : p.density === 'small' ? 22 : p.density === 'large' ? 52 : 32
  function heightFor(id: string) {
    if (trackHeights[id]) return trackHeights[id]
    if (p.density !== 'default') return defaultHeight
    return id.startsWith('motion:') ? 42 : id.startsWith('idle:') || id === 'nested' ? 30 : id.startsWith('audio:') ? 38 : id === 'base' ? 33 : 31
  }
  function rowStyle(id: string): CSSProperties { return { '--ed-row-height': `${heightFor(id)}px` } as CSSProperties }
  function resizeTrack(event: PointerEvent<HTMLDivElement>, id: string) {
    event.stopPropagation(); event.preventDefault()
    const element = event.currentTarget, initial = event.clientY, height = heightFor(id)
    element.setPointerCapture(event.pointerId)
    element.onpointermove = e => setTrackHeights(current => ({ ...current, [id]: Math.max(12, Math.min(100, height + e.clientY - initial)) }))
    const release = () => { element.onpointermove = null; element.onpointerup = null; element.onpointercancel = null }
    element.onpointerup = release; element.onpointercancel = release
  }
  function trackEdge(id: string, label: string) {
    return <div className="ed-track-edge" role="separator" aria-label={`Resize ${label} track`} aria-orientation="horizontal" aria-valuenow={heightFor(id)} aria-valuemin={12} aria-valuemax={100} tabIndex={0}
      onPointerDown={event => resizeTrack(event, id)} onDoubleClick={() => setTrackHeights(current => ({ ...current, [id]: heightFor(id) <= 12 ? 32 : 12 }))}
      onKeyDown={event => { if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); event.stopPropagation(); setTrackHeights(current => ({ ...current, [id]: Math.max(12, Math.min(100, heightFor(id) + (event.key === 'ArrowUp' ? -4 : 4))) })) } }} />
  }
  function effect(kind: SequenceEffect, title: string, channel: string, note: string) {
    const active = kind === 'texture' ? p.config?.texture?.enabled : p.config?.ambience.some(a => a.kind === kind)
    return <div className="ed-track-row ed-fx-row" key={kind} style={rowStyle(kind)}>
      <button className="ed-track-name" onClick={() => p.onEffect(kind)}><b>{channel}</b><span>{title}<small>{note}</small></span></button>
      <button className="ed-track-body ed-fx-clip" style={{ width }} onClick={() => p.onEffect(kind)}>{title} · {active ? kind === 'texture' ? `${Math.round((p.config?.texture?.strength ?? 0) * 100)}%` : 'on' : 'off'}{playhead}</button>{trackEdge(kind, title)}
    </div>
  }
  function sourceEvent(event: SubjectEvent, canDrag: boolean) {
    const shift = p.nudge && event.placement_id === p.nudge.placement ? p.nudge.delta : 0
    return <button key={event.index} className={`ed-segment ${event.origin} ${p.selection && p.selection === event.placement_id ? 'selected' : ''} ${shift ? 'nudging' : ''}`}
      style={{ left: left(event.start_frame + shift), width: Math.max(2, (event.end_frame - event.start_frame) / 24 * p.scale) }}
      title={`${event.label} · ${timecode(event.start_frame)}–${timecode(event.end_frame)}`}
      aria-label={`${event.actor}, ${event.origin === 'motion' ? 'placed action' : event.origin === 'idle' ? 'automatic idle' : 'hold'}: ${event.label}, ${timecode(event.start_frame)}`}
      draggable={canDrag && !p.busy && !p.dirty}
      onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('application/x-llr-action', JSON.stringify({ candidate: event.variant_id, placement: event.placement_id, offset: Math.round((e.clientX - e.currentTarget.getBoundingClientRect().left) / p.scale * 24) })) }}
      onClick={e => { e.stopPropagation(); p.onSeek(event.start_frame); p.onEvent(event) }}>{event.origin === 'hold' ? 'Hold' : event.label}</button>
  }
  return <section className="ed-timeline ed-pane" data-density={p.density} aria-label="Timeline" tabIndex={-1}>
    <h2 className="ed-pane-title">Timeline: {p.nested?.name ?? p.config?.title ?? 'Sequence'} <span>24 fps · {(end - start) / 24}s{p.nested ? ` · episode ${timecode(start)}` : ''}</span></h2>
    <div className="ed-timeline-toolbar">
      <button className="ed-sequence-tab" aria-pressed={!p.nested} onClick={() => p.onNested(null)}>Episode sequence</button>
      {p.nested ? <button className="ed-sequence-tab" aria-pressed="true" onClick={() => p.onSubject(p.nested!.actor)}>{p.nested.name} · contents</button> : null}
      <span className="ed-timecode">{timecode(p.frame - start)}</span><span className="ed-menu-spacer" />
      <span className="ed-track-visibility" aria-live="polite">{visibleTracks} / {count} tracks visible</span>
      <div className="ed-track-size-buttons" role="group" aria-label="Track size">
        <button className="ed-track-size" aria-label="Make tracks smaller" title="Make tracks smaller" disabled={sizeIndex === 0} onClick={() => changeDensity(sizes[Math.max(0, sizeIndex - 1)])}>−</button>
        <button className="ed-track-size" aria-label="Make tracks larger" title="Make tracks larger" disabled={sizeIndex === sizes.length - 1} onClick={() => changeDensity(sizes[Math.min(sizes.length - 1, sizeIndex + 1)])}>+</button>
      </div>
      <label>Tracks<select aria-label="Track height" value={p.density} onChange={e => changeDensity(e.target.value as TrackDensity)}><option value="default">Original</option><option value="reduced">Reduced</option><option value="small">Small</option><option value="standard">Medium</option><option value="large">Large</option></select></label>
      <button aria-pressed={fitWidth} onClick={() => { p.onFit(!fitWidth); if (fitWidth) p.onScale(8); if (scroll.current) scroll.current.scrollLeft = 0 }}>Fit sequence</button>
      <label>Zoom<select aria-label="Timeline zoom" value={fitWidth ? 'fit' : p.scale} onChange={e => { if (e.target.value === 'fit') p.onFit(true); else { p.onFit(false); p.onScale(Number(e.target.value)) } }}><option value="fit">Fit</option>{ZOOM_LEVELS.map(value => <option value={value} key={value}>{value} px/s</option>)}</select></label>
    </div>
    <div ref={scroll} className="ed-timeline-scroll">
      <div className="ed-track-stack" style={{ width: `calc(${width}px + var(--ed-track-label, 190px))` }}>
        <div className="ed-track-row ed-ruler"><div className="ed-track-name">{p.nested ? 'NESTED CONTENTS' : 'TRACK / DESIGNATION'}</div><div className="ed-ruler-body" style={{ width }} onClick={e => p.onSeek(start + Math.round((e.clientX - e.currentTarget.getBoundingClientRect().left) / p.scale * 24))}>
          {Array.from({ length: Math.floor((end - start) / (tick * 24)) + 1 }, (_, index) => <span key={index} style={{ left: index * tick * p.scale, transform: index > 0 && index * tick * 24 === end - start ? 'translateX(-100%)' : undefined }}>{timecode(index * tick * 24).slice(0, 8)}</span>)}
          {inOut}{p.markers.filter(m => m >= start && m < end).map(m => <i key={m} className="ed-marker" style={{ left: left(m) }} title={`Marker ${timecode(m - start)}`} />)}{playhead}</div></div>
        {p.nested ? <div className="ed-track-row ed-idle-row" style={rowStyle("nested")}><button className="ed-track-name" onClick={() => p.onSubject(p.nested!.actor)}><b>V1</b><span>{p.nested.name}<small>{p.nested.events.length} source segments</small></span></button><div className="ed-track-body" style={{ width }} onClick={e => p.onSeek(start + Math.round((e.clientX - e.currentTarget.getBoundingClientRect().left) / p.scale * 24))}>{p.nested.events.map(event => sourceEvent(event, false))}{playhead}</div>{trackEdge("nested", "nested contents")}</div> : <>
          {effect('texture', 'Video texture', 'FX3', 'Finishing · whole picture')}
          {p.effects.includes('steam') ? effect('steam', 'Mug steam', 'FX2', 'Foreground · fixed plume') : null}
          {p.config?.subjects.map((subject, index) => {
            const events = p.sequence?.manifest.tracks.find(t => t.actor === subject.actor)?.events ?? []
            const beds = idleBeds(subject.actor, events)
            return <div className="ed-subject-group" key={subject.actor}>
              <div className="ed-track-row ed-motion-row" style={rowStyle(`motion:${subject.actor}`)}><button className="ed-track-name" onClick={() => p.onSubject(subject.actor)}><b>V{p.config!.subjects.length - index}</b><span>{subject.actor}<small>Motions · creator placed</small></span></button>
                <div className="ed-track-body" style={{ width }} onDragOver={e => { if (!p.busy) e.preventDefault() }} onDrop={e => p.onDrop(e, subject.actor)} onClick={e => p.onSeek(Math.round((e.clientX - e.currentTarget.getBoundingClientRect().left) / p.scale * 24))}>
                  {events.filter(e => e.origin === 'motion').map(e => sourceEvent(e, true))}{!p.sequence ? <span className="ed-unscheduled">Place approved actions here</span> : null}{playhead}
                </div>{trackEdge(`motion:${subject.actor}`, `${subject.actor} motions`)}</div>
              <div className="ed-track-row ed-idle-row" style={rowStyle(`idle:${subject.actor}`)}><button className="ed-track-name" onClick={() => p.onSubject(subject.actor)}><b>↳</b><span>{subject.actor}<small>Automatic idles · nested sequence</small></span></button><div className="ed-track-body" style={{ width }}>
                {beds.map(bed => <button key={bed.start_frame} className="ed-segment idle ed-nested-bed" style={{ left: left(bed.start_frame), width: Math.max(2, (bed.end_frame - bed.start_frame) / 24 * p.scale) }} aria-label={`Open ${bed.name} nested sequence`} title={`${bed.name} · ${bed.events.length} source segments · click to open`} onClick={() => p.onNested(bed)}><span className="ed-nest-mark">▣</span><span>{bed.name}</span><small>{bed.events.length} segments</small></button>)}
                {!p.sequence ? <span className="ed-unscheduled">{subject.pool.length ? 'Build sequence to fill the idle bed' : 'Current pose hold · no idle pool'}</span> : null}{playhead}
              </div>{trackEdge(`idle:${subject.actor}`, `${subject.actor} idles`)}</div>
            </div>
          })}
          {p.effects.includes('rain') ? effect('rain', 'Window rain', 'FX1', 'Background · continuous') : null}
          <div className="ed-track-row ed-base-row" style={rowStyle("base")}><div className="ed-track-name"><b>BG</b><span>{p.sceneTitle}<small>Canonical still · locked</small></span></div><div className="ed-track-body ed-base-clip" style={{ width }}>{p.sceneTitle} · immutable master{playhead}</div>{trackEdge("base", "canonical still")}</div>
          {(['production', 'music'] as const).map((role, index) => <div className="ed-track-row ed-audio-row" key={role} style={rowStyle(`audio:${role}`)}>
            <button className="ed-track-name" onClick={p.onAudio}><b>A{index + 1}</b><span>{role === 'production' ? 'Production sound' : 'Music'}<small>Click to import, review & edit</small></span></button>
            <div className="ed-track-body" style={{ width }}>
              {(p.config?.audio_tracks ?? []).filter(track => track.role === role).map(track => <button key={track.id} className="ed-segment ed-audio-segment" data-enabled={track.enabled} style={{ left: left(track.start_frame), width: Math.max(2, track.duration_frames / 24 * p.scale) }} title={`${role} · ${timecode(track.start_frame)} · ${track.gain_db} dB`} onClick={() => { p.onSeek(track.start_frame); p.onAudio() }}>{track.enabled ? '' : 'Muted · '}{role === 'music' ? 'Music' : 'Sound'} · {track.gain_db} dB</button>)}
              {!p.config?.audio_tracks?.some(track => track.role === role) ? <button className="ed-unscheduled" onClick={p.onAudio}>Add approved {role === 'music' ? 'music' : 'production sound'}</button> : null}{playhead}
            </div>{trackEdge(`audio:${role}`, role)}
          </div>)}
        </>}
      </div>
    </div>
    <div className="ed-timeline-footer"><span>{p.nested ? 'Source cuts · click a take to audition · Episode sequence returns to the main timeline' : 'Click an idle bed to open its nested sequence. Place deliberate actions on Motions.'}</span><span>{p.hints}</span></div>
  </section>
}

