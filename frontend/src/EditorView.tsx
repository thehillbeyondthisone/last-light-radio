import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, DragEvent, PointerEvent, SyntheticEvent } from 'react'
import { api } from './api'
import Icon from './Icon'
import MotionGuide from './MotionGuide'
import AdjustMotionArea from './AdjustMotionArea'
import EditorCanvas from './EditorCanvas'
import TakeComparison from './TakeComparison'
import type { Candidate, MotionProfile, Scene, StudioState } from './types'
import type { EditorConfig, EditorState, EditorSave, SubjectEvent, SubjectSequence, SubjectSettings } from './editorTypes'
import { timecode } from './editorTypes'
import KeyboardLayout from './KeyboardLayout'
import type { Keymap } from './shortcuts'
import { COMMAND_BY_ID, chordFromEvent, chordIndex, editPoints, formatChord, loadStoredKeymap, parseTimecodeEntry, serializeKeymap, shuttleRate, stepPoint, zoomStep } from './shortcuts'
import TextureControls from './TextureControls'
import AudioWorkspace from './AudioWorkspace'
import SequenceTimeline from './SequenceTimeline'
import type { SequenceEffect } from './SequenceTimeline'
import type { IdleBed } from './nestedSequences'
import { monitorHeight, timelineHeight } from './workspaceLayout'
import type { TrackDensity } from './workspaceLayout'
import './editor.css'

type Props = { data: StudioState; scene?: Scene; onScene: (id: string) => void; refresh: () => Promise<void>; notify: (text: string) => void; onImport: () => void; onWorker: () => void; onLegacy: () => void }
type BrowserTab = 'actions' | 'subjects' | 'effects' | 'jobs'
type ViewerTab = 'audition' | 'create' | 'subjects' | 'effects' | 'mask' | 'audio'
type Pane = 'browser' | 'viewer' | 'canvas' | 'timeline'
const KEYMAP_STORAGE = 'llr.editor.keymap.v1'
const markerStorage = (sceneId: string) => `llr.editor.markers.${sceneId}`
const TYPING_INPUTS = new Set(['text', 'search', 'number', 'email', 'password', 'url', 'tel', 'date', 'time', 'datetime-local', 'month', 'week'])

function storedKeymap() {
  let storage: Storage | undefined
  try { storage = window.localStorage } catch { storage = undefined }
  return loadStoredKeymap(storage, KEYMAP_STORAGE)
}
function storedMarkers(sceneId: string): number[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(markerStorage(sceneId)) ?? '[]')
    return Array.isArray(value) ? [...new Set(value.filter((m): m is number => Number.isInteger(m) && m >= 0))].sort((a, b) => a - b) : []
  } catch { return [] }
}
/** Text fields keep their own keys; only commands marked inText (save, windows, keyboard layout) reach the editor. */
function isTyping(target: HTMLElement) {
  if (target.isContentEditable || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true
  return target instanceof HTMLInputElement && TYPING_INPUTS.has(target.type)
}
/** Keyboard users keep native Space/Enter on focused controls and arrows on sliders. Mouse-focused buttons don't swallow Space. */
function nativeKey(target: HTMLElement, chord: string) {
  if (target.closest('audio')) return true
  if (target instanceof HTMLInputElement && target.type === 'range' && ['Left', 'Right', 'Up', 'Down', 'Home', 'End', 'PageUp', 'PageDown'].includes(chord)) return true
  return (chord === 'Space' || chord === 'Enter') && target.matches('button,summary,a[href],input,[role=button],[role=separator]') && target.matches(':focus-visible')
}
function paneOf(target: EventTarget | null): Pane | null {
  const element = target instanceof Element ? target.closest('.ed-browser,.ed-viewer,.ed-program,.ed-timeline') : null
  if (!element) return null
  return element.classList.contains('ed-browser') ? 'browser' : element.classList.contains('ed-viewer') ? 'viewer' : element.classList.contains('ed-program') ? 'canvas' : 'timeline'
}

function profileFor(candidate: Candidate, profiles: MotionProfile[]) {
  return profiles.find(p => p.id === (candidate.metadata.motion?.profile_id ?? candidate.metadata.motion?.profile?.id)) ?? profiles.find(p => p.reference_candidate_id === candidate.id)
}
function returning(profile: MotionProfile, sceneId: string) {
  return profile.first_scene_id === sceneId && profile.last_scene_id === sceneId && profile.start_state === profile.end_state
}
function readable(value: string) { return value.replaceAll('_', ' ') }
function takeOrder(a: Candidate, b: Candidate) { return a.created.localeCompare(b.created) || a.id.localeCompare(b.id) }
function message(problem: unknown, fallback: string) { return problem instanceof Error ? problem.message : fallback }

export default function EditorView(props: Props) {
  const { data, scene, onScene, refresh, notify } = props
  const [saved, setSaved] = useState<EditorState | null>(null)
  const [config, setConfig] = useState<EditorConfig | null>(null)
  const [sequence, setSequence] = useState<SubjectSequence | null>(null)
  const [browser, setBrowser] = useState<BrowserTab>('actions')
  const [viewer, setViewer] = useState<ViewerTab>('audition')
  const [authoringIdle, setAuthoringIdle] = useState(false)
  const [selectedProfile, setSelectedProfile] = useState('')
  const [selectedTake, setSelectedTake] = useState('')
  const [subject, setSubject] = useState('')
  const [effect, setEffect] = useState<SequenceEffect>('rain')
  const [selection, setSelection] = useState('')
  const [placeAt, setPlaceAt] = useState('0')
  const [frame, setFrame] = useState(0)
  // Canvas shuttle speed: 0 stopped, 1 play, ±2/4/8 J/L shuttle, negative plays in reverse.
  const [rate, setRate] = useState(0)
  const playing = rate !== 0
  const setPlaying = useCallback((value: boolean) => setRate(value ? 1 : 0), [])
  const [loop, setLoop] = useState(false)
  // A bounded play (In to Out, or play around) stops at end and may return the playhead.
  const [segment, setSegment] = useState<{ start: number; end: number; returnTo?: number } | null>(null)
  const [marks, setMarks] = useState<{ in?: number; out?: number }>({})
  const [markers, setMarkers] = useState<number[]>([])
  const [activePane, setActivePane] = useState<Pane>('timeline')
  const [keymap, setKeymap] = useState<Keymap>(() => storedKeymap().keymap)
  const [layoutOpen, setLayoutOpen] = useState(false)
  const [timecodeEntry, setTimecodeEntry] = useState<{ target: 'source' | 'program'; text: string } | null>(null)
  const [nudge, setNudge] = useState<{ placement: string; delta: number } | null>(null)
  const nudgeRef = useRef<{ placement: string; delta: number } | null>(null)
  const nudgeTimer = useRef(0)
  const kHeld = useRef(false)
  const kCode = useRef('')
  const pendingSourceSeek = useRef<{ id: string; frame: number } | null>(null)
  const search = useRef<HTMLInputElement>(null)
  const [fit, setFit] = useState(false)
  const [seekVersion, setSeekVersion] = useState(0)
  const [scale, setScale] = useState(8)
  const [requestedHeight, setRequestedHeight] = useState(410)
  const [layout, setLayout] = useState<'standard' | 'all-tracks'>('standard')
  const [fitTracks, setFitTracks] = useState(false)
  const [trackReset, setTrackReset] = useState(0)
  const [density, setDensity] = useState<TrackDensity>('default')
  const [hideTools, setHideTools] = useState(false)
  const standardView = useRef({ height: 410, density: 'default' as TrackDensity })
  const viewMenu = useRef<HTMLDetailsElement>(null)
  const shell = useRef<HTMLElement>(null)
  const [availableHeight, setAvailableHeight] = useState(window.innerHeight - 107)

  const [mobileMonitor, setMobileMonitor] = useState<'viewer' | 'canvas'>('viewer')
  const [showMask, setShowMask] = useState(false)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('Choose an action to audition, or create a new action.')
  const [history, setHistory] = useState<EditorConfig[]>([])
  const [future, setFuture] = useState<EditorConfig[]>([])
  const [notes, setNotes] = useState('')
  const [checked, setChecked] = useState(false)
  const [entry, setEntry] = useState('')
  const [exit, setExit] = useState('')
  const [sourceFrame, setSourceFrame] = useState(0)
  const [sourceRate, setSourceRate] = useState(0)
  const sourcePlaying = sourceRate !== 0
  const setSourcePlaying = useCallback((value: boolean) => setSourceRate(value ? 1 : 0), [])
  const [compareTakes, setCompareTakes] = useState(false)
  const sourceVideo = useRef<HTMLVideoElement>(null)
  const [nestedBed, setNestedBed] = useState<IdleBed | null>(null)
  const viewStart = nestedBed?.start_frame ?? 0
  const viewEnd = nestedBed?.end_frame ?? sequence?.manifest.duration_frames ?? config?.duration_frames ?? 1
  const saveLock = useRef(false)
  const generationLock = useRef(false)
  const takeRequest = useRef<{ profile: string; seed: number; id: string } | null>(null)
  const sceneRef = useRef(scene?.id)
  sceneRef.current = scene?.id
  const profiles = (data.motion_profiles ?? []).filter(p => p.scene_id === scene?.id)
  const actionProfiles = profiles.filter(p => !p.role.toLowerCase().includes('idle') && returning(p, scene?.id ?? ''))
  const profile = profiles.find(p => p.id === selectedProfile) ?? actionProfiles[0]
  const takes = data.candidates.filter(c => c.scene_id === scene?.id && profileFor(c, profiles)?.id === profile?.id).sort(takeOrder)
  const candidate = takes.find(c => c.id === selectedTake) ?? takes.at(-1)
  const activeSubject = config?.subjects.find(s => s.actor === subject) ?? config?.subjects[0]
  const placement = config?.placements.find(p => p.id === selection)
  const sourceFrames = candidate?.metadata.outputs[0]?.properties.frame_count ?? 1
  const ambientLayers = data.ambience_catalog?.find(a => a.scene_id === scene?.id)?.layers ?? []
  const desiredTimeline = timelineHeight(config?.subjects.length ?? 0, 1 + ambientLayers.length, density, !!nestedBed)
  const upperHeight = monitorHeight(availableHeight, requestedHeight, desiredTimeline, fitTracks)
  const summary = data.sequences?.find(p => p.id === sequence?.id)
  const setPlaybackError = useCallback((text: string) => { setPlaying(false); setError(text) }, [])

  useEffect(() => {
    const element = shell.current
    if (!element) return
    function measure() {
      if (!element) return
      const fixed = [...element.children].filter(child => !child.matches('.ed-upper,.ed-timeline'))
        .reduce((height, child) => height + (child.matches('.ed-divider') ? 9 : child.getBoundingClientRect().height), 0)
      const css = getComputedStyle(element)
      const gaps = Math.max(0, [...element.children].filter(child => getComputedStyle(child).display !== 'none').length - 1) * parseFloat(css.rowGap)
      setAvailableHeight(element.clientHeight - parseFloat(css.paddingTop) - parseFloat(css.paddingBottom) - fixed - gaps)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    for (const child of element.children) if (!child.matches('.ed-upper,.ed-timeline')) observer.observe(child)
    measure()
    return () => observer.disconnect()
  }, [hideTools, error])

  useEffect(() => {
    if (!scene) return
    const controller = new AbortController()
    setLoading(true); setError(''); setPlaying(false); setSourcePlaying(false); setSequence(null); setSaved(null); setConfig(null); setFrame(0); setSelection(''); setHistory([]); setFuture([]); setNestedBed(null)
    setSegment(null); setMarks({}); setMarkers(storedMarkers(scene.id)); window.clearTimeout(nudgeTimer.current); nudgeRef.current = null; setNudge(null)
    void api<EditorState>(`editor/${scene.id}`, undefined, controller.signal).then(async result => {
      if (controller.signal.aborted) return
      setSaved(result); setConfig(result.config); setSubject(result.actors[0] ?? '')
      if (result.sequence_id) {
        const plan = await api<SubjectSequence>(`pilots/${result.sequence_id}`, undefined, controller.signal)
        if (!controller.signal.aborted) setSequence(plan)
      }
    }).catch(problem => { if (!controller.signal.aborted) setError(message(problem, 'Could not open this scene’s sequence.')) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [scene?.id])

  useEffect(() => {
    if (!sequence || !summary || (sequence.status === summary.status && sequence.progress === summary.progress)) return
    const controller = new AbortController()
    void api<SubjectSequence>(`pilots/${sequence.id}`, undefined, controller.signal).then(setSequence).catch(problem => { if (!controller.signal.aborted) setError(message(problem, 'Could not update export progress.')) })
    return () => controller.abort()
  }, [sequence?.id, summary?.status, summary?.progress, summary?.error])

  useEffect(() => {
    setSourcePlaying(false); setSourceFrame(0); setChecked(false)
    setNotes(candidate?.reviews.at(-1)?.notes ?? '')
    setEntry(profile?.start_state ?? ''); setExit(profile?.end_state ?? '')
  }, [candidate?.id, candidate?.version, profile?.start_state, profile?.end_state])

  useEffect(() => {
    const element = sourceVideo.current
    if (!element) return
    if (sourceRate > 0) {
      element.playbackRate = sourceRate
      void element.play().catch(() => { setSourcePlaying(false); setError('The take could not play. Try again after it loads.') })
      return
    }
    element.pause()
    if (sourceRate >= 0) return
    // Browsers cannot play video backwards, so reverse shuttle seeks on each animation frame.
    const startedAt = element.currentTime, started = performance.now()
    let animation = 0
    function tick(now: number) {
      const at = startedAt + (now - started) / 1000 * sourceRate
      if (at <= 0) { element!.currentTime = 0; setSourceFrame(0); setSourceRate(0); return }
      if (!element!.seeking) element!.currentTime = at
      setSourceFrame(Math.floor(at * 24)); animation = requestAnimationFrame(tick)
    }
    animation = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animation)
  }, [sourceRate, candidate?.id, viewer, setSourcePlaying])

  useEffect(() => {
    if (!rate || !sequence) return
    const started = performance.now(), from = frame
    const looping = loop && !segment
    const ranged = looping && marks.in !== undefined && marks.out !== undefined && marks.out >= marks.in
    const begin = segment?.start ?? (ranged ? marks.in! : viewStart)
    const stop = segment?.end ?? (ranged ? marks.out! + 1 : viewEnd)
    let animation = 0
    function tick() {
      const next = from + Math.trunc((performance.now() - started) * sequence!.manifest.fps * rate / 1000)
      if (next >= stop || next < begin) {
        if (looping) { setFrame(rate > 0 ? begin : stop - 1); setSeekVersion(v => v + 1); return }
        setFrame(segment?.returnTo ?? (rate > 0 ? stop - 1 : begin)); setRate(0); setSegment(null); return
      }
      setFrame(next); animation = requestAnimationFrame(tick)
    }
    animation = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animation)
    // Seeking or changing speed starts a new absolute-time playback segment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rate, sequence?.id, seekVersion, viewStart, viewEnd, loop, segment, marks.in, marks.out])

  async function commit(next: EditorConfig, record = true) {
    if (!saved || saveLock.current) return false
    const openedScene = next.scene_id
    saveLock.current = true; setBusy(true); setError(''); setPlaying(false)
    try {
      const result = await api<EditorSave>('editor/plan', { ...next, expected_revision: saved.revision })
      if (sceneRef.current !== openedScene) return false
      if (record) { setHistory(items => [...items.slice(-24), saved.config]); setFuture([]) }
      setSaved({ ...saved, revision: result.revision, config: result.config, sequence_id: result.sequence_id }); setConfig(result.config); setSequence(result.sequence); setNestedBed(null)
      setStatus(`Sequence saved · revision ${result.revision} · ${result.sequence.manifest.events.length} scheduled segments`)
      await refresh(); return true
    } catch (problem) { if (sceneRef.current === openedScene) setError(message(problem, 'The sequence could not be saved.')); return false }
    finally { saveLock.current = false; setBusy(false) }
  }

  function chooseAction(p: MotionProfile, take?: Candidate) {
    setSelectedProfile(p.id); setSelectedTake(take?.id ?? ''); setViewer('audition'); setBrowser('actions'); setMobileMonitor('viewer'); setError('')
  }
  function startCreate(idle = false) { setAuthoringIdle(idle); setViewer('create'); setMobileMonitor('viewer') }
  async function requestTake() {
    if (!profile || busy || generationLock.current) return
    generationLock.current = true
    if (takeRequest.current?.profile !== profile.id) takeRequest.current = { profile: profile.id, seed: crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff, id: crypto.randomUUID() }
    const request = takeRequest.current
    setBusy(true); setError('')
    try {
      await api('generate', { scene_id: profile.scene_id, motion_profile_id: profile.id, motion_vae_name: profile.vae_name,
        label: profile.name, prompt: profile.prompt, seed: request.seed, request_id: request.id })
      takeRequest.current = null
      await refresh(); setStatus('New take requested. Its progress is in Jobs.'); notify('Action take requested. Review it before placing it.')
    } catch (problem) { setError(message(problem, 'Could not request another take.')) }
    finally { generationLock.current = false; setBusy(false) }
  }
  async function review(decision: 'approved' | 'rejected') {
    if (!candidate || busy) return
    if (decision === 'rejected' && !notes.trim()) { setError('Add a short reason before rejecting this take.'); return }
    setBusy(true); setError('')
    try {
      await api(`candidates/${candidate.id}/review`, { decision, notes, entry_anchor: entry, exit_anchor: exit, visual_checked: checked, expected_version: candidate.version, request_id: crypto.randomUUID() })
      await refresh()
      const result = await api<EditorState>(`editor/${scene!.id}`); setSaved(result)
      setStatus(decision === 'approved' ? 'Take approved. Place it on the subject’s Motions track.' : 'Take rejected. The original and your notes are preserved.')
    } catch (problem) { setError(message(problem, 'Could not save this review.')) }
    finally { setBusy(false) }
  }
  async function place(id: string, start: number, moving?: string, seekTo = true) {
    if (!config || !saved) return false
    const clip = saved.clips.find(c => c.id === id)
    if (!clip || clip.role.toLowerCase().includes('idle')) { setError('Choose an approved returning action. Idle takes belong in Subject setup.'); return false }
    if (!Number.isInteger(start) || start < 0 || start + clip.frames > config.duration_frames) { setError('The complete action must fit inside the sequence.'); return false }
    const identity = moving ?? crypto.randomUUID()
    const next = { ...config, placements: [...config.placements.filter(p => p.id !== moving), { id: identity, candidate_id: id, start_frame: start }] }
    if (!await commit(next)) return false
    setSelection(identity); setPlaceAt(String(start / 24)); setMobileMonitor('canvas')
    if (seekTo) { setFrame(start); setSeekVersion(v => v + 1) }
    return true
  }
  async function removePlacement() {
    if (!config || !placement) return
    if (await commit({ ...config, placements: config.placements.filter(p => p.id !== placement.id) })) setSelection('')
  }
  async function undo(redo = false) {
    const stack = redo ? future : history, previous = stack.at(-1)
    if (!previous || !config) return
    if (await commit(previous, false)) {
      if (redo) { setFuture(stack.slice(0, -1)); setHistory(items => [...items, config]) }
      else { setHistory(stack.slice(0, -1)); setFuture(items => [...items, config]) }
      setSelection('')
    }
  }
  function seek(next: number) { setFrame(Math.max(viewStart, Math.min(viewEnd - 1, next))); setSeekVersion(v => v + 1) }
  function togglePlayback() {
    setSegment(null)
    if (rate) { setRate(0); return }
    if (frame >= viewEnd - 1) seek(viewStart)
    setRate(1)
  }
  function updateSubject(patch: Partial<SubjectSettings>) {
    if (!config || !activeSubject) return
    setConfig({ ...config, subjects: config.subjects.map(s => s.actor === activeSubject.actor ? { ...s, ...patch } : s) })
  }
  function updateEffect(opacity: number) {
    if (!config || effect === 'texture') return
    setConfig({ ...config, ambience: [...config.ambience.filter(a => a.kind !== effect), ...(opacity > 0 ? [{ kind: effect, opacity }] : [])] })
  }
  function drop(event: DragEvent<HTMLDivElement>, actor: string) {
    event.preventDefault()
    if (dirty) { setError('Apply the changed settings before placing or moving an action.'); return }
    try {
      const drag = JSON.parse(event.dataTransfer.getData('application/x-llr-action')) as { candidate: string; placement?: string; offset?: number }
      const clip = saved?.clips.find(c => c.id === drag.candidate)
      if (!clip || clip.actor !== actor) { setError('Drop this action on its own subject’s Motions track.'); return }
      const bounds = event.currentTarget.getBoundingClientRect()
      const start = Math.round((event.clientX - bounds.left) / scale * 24) - (drag.offset ?? 0)
      void place(drag.candidate, Math.max(0, start), drag.placement)
    } catch { setError('Drag an approved action take from the Browser or Viewer.') }
  }
  function chooseLayout(next: 'standard' | 'all-tracks') {
    setTrackReset(value => value + 1)
    if (next === 'all-tracks') {
      if (layout === 'standard') standardView.current = { height: upperHeight, density }
      setDensity('reduced'); setFitTracks(true)
    } else if (layout !== 'standard') {
      setRequestedHeight(standardView.current.height); setDensity(standardView.current.density); setFitTracks(false)
    }
    setLayout(next)
    if (viewMenu.current) viewMenu.current.open = false
  }
  function resize(event: PointerEvent<HTMLDivElement>) {
    const element = event.currentTarget, initial = event.clientY, initialHeight = upperHeight
    setFitTracks(false); setRequestedHeight(upperHeight)
    element.setPointerCapture(event.pointerId)
    element.onpointermove = e => setRequestedHeight(monitorHeight(availableHeight, initialHeight + e.clientY - initial, desiredTimeline, false))
    const release = () => { element.onpointermove = null; element.onpointerup = null; element.onpointercancel = null }
    element.onpointerup = release; element.onpointercancel = release
  }
  // ---- Keyboard: Final Cut Pro 7 commands (registry and defaults in shortcuts.ts) ----
  const index = useMemo(() => chordIndex(keymap), [keymap])
  const key = (id: string) => { const chord = keymap[id]?.[0]; return chord ? formatChord(chord) : '' }
  const titled = (label: string, id: string) => key(id) ? `${label} (${key(id)})` : label
  // Transport keys follow the active window, as in FCP7. A Browser selection previews in the Viewer.
  const viewerTransport = (activePane === 'viewer' || activePane === 'browser') && viewer === 'audition' && !!candidate && !compareTakes
  function changeKeymap(next: Keymap) {
    setKeymap(next)
    try { window.localStorage.setItem(KEYMAP_STORAGE, serializeKeymap(next)) } catch { setError('Keyboard changes apply now, but this browser could not save them for next time.') }
  }
  useEffect(() => { const { warnings } = storedKeymap(); if (warnings.length) setStatus(warnings.join(' ')) }, [])
  function stopProgram() { setRate(0); setSegment(null) }
  function goto(next: number) { stopProgram(); seek(next) }
  function seekSource(next: number) {
    const at = Math.max(0, Math.min(sourceFrames - 1, Math.round(next)))
    setSourceRate(0); setSourceFrame(at)
    if (sourceVideo.current) sourceVideo.current.currentTime = (at + .5) / 24
  }
  function step(frames: number) { if (viewerTransport) seekSource(sourceFrame + frames); else goto(frame + frames) }
  function shuttle(direction: 1 | -1) {
    if (viewerTransport) { setSourceRate(r => shuttleRate(r, direction)); return }
    if (!sequence) return
    setSegment(null)
    if (direction > 0 && rate <= 0 && frame >= viewEnd - 1) seek(viewStart)
    setRate(r => shuttleRate(r, direction))
  }
  function playSegment(start: number, end: number, returnTo?: number) {
    if (!sequence) return
    if (end <= start) { setError('Set an Out point after the In point.'); return }
    setSegment({ start, end, returnTo }); setFrame(start); setSeekVersion(v => v + 1); setRate(1)
  }
  function editStep(direction: 1 | -1) {
    if (viewerTransport) { const at = stepPoint([0, sourceFrames - 1], sourceFrame, direction); if (at !== undefined) seekSource(at); return }
    const events = nestedBed ? nestedBed.events : sequence?.manifest.tracks.flatMap(t => t.events) ?? []
    const at = stepPoint(editPoints(events, viewStart, viewEnd), frame, direction)
    if (at === undefined) setStatus(direction > 0 ? 'No later edit.' : 'No earlier edit.'); else goto(at)
  }
  function markerStep(direction: 1 | -1) {
    const at = stepPoint(markers.filter(m => m >= viewStart && m < viewEnd), frame, direction)
    if (at === undefined) setStatus(markers.length ? `No ${direction > 0 ? 'later' : 'earlier'} marker.` : 'No markers yet. Press M to add one.'); else goto(at)
  }
  function takeStep(direction: 1 | -1) {
    if (!candidate) { setStatus('Choose an action in the Browser first.'); return }
    const next = takes[takes.indexOf(candidate) + direction]
    if (!next) { setStatus(direction > 0 ? 'This is the last take.' : 'This is the first take.'); return }
    setSelectedTake(next.id); setViewer('audition'); setStatus(`Take ${takes.indexOf(next) + 1} of ${takes.length}`)
  }
  function eventAtPlayhead(): SubjectEvent | undefined {
    const tracks = nestedBed ? [nestedBed.events] : sequence?.manifest.tracks.map(t => t.events) ?? []
    const hits = tracks.map(events => events.find(e => e.start_frame <= frame && frame < e.end_frame)).filter((e): e is SubjectEvent => !!e)
    return hits.find(e => !!selection && e.placement_id === selection) ?? hits.find(e => e.origin === 'motion') ?? hits.find(e => e.kind === 'clip') ?? hits[0]
  }
  function matchFrame() {
    if (viewerTransport) { focusPane('canvas'); return }
    const hit = eventAtPlayhead()
    if (!hit || hit.kind !== 'clip' || !hit.variant_id) { setStatus('Nothing to match: the playhead is on a held frame.'); return }
    const take = data.candidates.find(c => c.id === hit.variant_id), action = take && profileFor(take, profiles)
    if (!take || !action) { setError('The take under the playhead is not available in the Browser.'); return }
    const offset = frame - hit.start_frame
    pendingSourceSeek.current = { id: take.id, frame: offset }
    stopProgram(); chooseAction(action, take); setCompareTakes(false); focusPane('viewer')
    if (take.id === candidate?.id && (sourceVideo.current?.readyState ?? 0) > 0) { pendingSourceSeek.current = null; seekSource(offset) }
    setStatus(`Match frame · ${take.label} at ${timecode(offset)}`)
  }
  function applyPendingSourceSeek(event: SyntheticEvent<HTMLVideoElement>) {
    const pending = pendingSourceSeek.current
    if (!pending || pending.id !== candidate?.id) return
    pendingSourceSeek.current = null
    event.currentTarget.currentTime = (pending.frame + .5) / 24; setSourceFrame(pending.frame)
  }
  function setMark(which: 'in' | 'out', value?: number) {
    setMarks(current => {
      const next = { ...current, [which]: value }
      // FCP7: marking In after Out (or Out before In) clears the other point.
      if (value !== undefined && next.in !== undefined && next.out !== undefined && next.out < next.in) delete next[which === 'in' ? 'out' : 'in']
      return next
    })
    setStatus(value === undefined ? `${which === 'in' ? 'In' : 'Out'} cleared` : `${which === 'in' ? 'In' : 'Out'} ${timecode(value - viewStart)}`)
  }
  function markClip() {
    const hit = eventAtPlayhead()
    if (!hit) { setStatus('No segment under the playhead.'); return }
    setMarks({ in: hit.start_frame, out: hit.end_frame - 1 })
    if (hit.origin === 'motion' && hit.placement_id) { setSelection(hit.placement_id); setPlaceAt(String(hit.start_frame / 24)) }
    setStatus(`Marked ${hit.origin === 'hold' ? 'hold' : hit.label} · ${timecode(hit.start_frame - viewStart)}–${timecode(hit.end_frame - viewStart)}`)
  }
  function changeMarkers(next: number[]) {
    setMarkers(next)
    if (!scene) return
    try { window.localStorage.setItem(markerStorage(scene.id), JSON.stringify(next)) } catch { setStatus('Markers changed, but this browser could not save them.') }
  }
  // Nudges accumulate on screen and save once you pause, so holding , or . makes one revision, not dozens.
  function nudgeBy(delta: number) {
    if (!placement || !config || !saved || nestedBed) { setStatus('Select a placed action (click it, or press X over it) to nudge it.'); return }
    if (dirty) { setError('Apply the changed settings before moving an action.'); return }
    if (saveLock.current) return
    const clip = saved.clips.find(c => c.id === placement.candidate_id)
    if (!clip) return
    const pending = nudgeRef.current?.placement === placement.id ? nudgeRef.current.delta : 0
    const target = Math.max(0, Math.min(config.duration_frames - clip.frames, placement.start_frame + pending + delta))
    const shift = { placement: placement.id, delta: target - placement.start_frame }
    nudgeRef.current = shift; setNudge(shift)
    setStatus(`Nudge ${shift.delta > 0 ? '+' : ''}${shift.delta} frame${Math.abs(shift.delta) === 1 ? '' : 's'} → ${timecode(target)} · saves when you pause`)
    window.clearTimeout(nudgeTimer.current)
    nudgeTimer.current = window.setTimeout(() => void latest.current.flushNudge(), 450)
  }
  async function flushNudge() {
    const shift = nudgeRef.current
    nudgeRef.current = null
    const moving = config?.placements.find(p => p.id === shift?.placement)
    if (shift && moving && shift.delta) await place(moving.candidate_id, moving.start_frame + shift.delta, moving.id, false)
    setNudge(null)
  }
  const latest = useRef({ flushNudge })
  latest.current = { flushNudge }
  function overwrite() {
    if (nestedBed) { setError('Return to the Episode sequence to place actions.'); return }
    if (!candidate || !canPlace) { setError('Open an approved returning action take in the Viewer first.'); return }
    if (dirty) { setError('Apply the changed settings before placing an action.'); return }
    if (!busy) void place(candidate.id, marks.in ?? frame)
  }
  function save() {
    if (!config || busy || loading) return
    if (sequence && !dirty) { setStatus(`Already saved · revision ${saved?.revision}`); return }
    void commit(config)
  }
  function zoom(direction: 1 | -1) { setFit(false); setScale(s => zoomStep(s, direction)) }
  function cycleTracks() {
    const sizes: TrackDensity[] = ['reduced', 'small', 'standard', 'large']
    const next = sizes[(sizes.indexOf(density === 'default' ? 'standard' : density) + 1) % sizes.length]
    setRequestedHeight(upperHeight); setFitTracks(false); setDensity(next); setStatus(`Track height: ${next === 'standard' ? 'medium' : next}`)
  }
  function focusPane(pane: Pane) {
    setActivePane(pane); setMobileMonitor(pane === 'viewer' || pane === 'browser' ? 'viewer' : 'canvas')
    const selector = { browser: '.ed-browser', viewer: '.ed-viewer', canvas: '.ed-program', timeline: '.ed-timeline' }[pane]
    shell.current?.querySelector<HTMLElement>(selector)?.focus({ preventScroll: true })
  }
  function applyTimecode(target: 'source' | 'program', text: string) {
    const next = parseTimecodeEntry(text, target === 'source' ? sourceFrame : frame - viewStart)
    if (next === null) { setError(`“${text}” is not a timecode. Type digits such as 1419 (14 s 19 f), or +24 / -24 to move by frames.`); return }
    if (target === 'source') seekSource(next); else goto(viewStart + next)
  }
  function timecodeField(target: 'source' | 'program', shown: string) {
    if (timecodeEntry?.target !== target) return <span className="ed-timecode" title="Type a timecode to jump (e.g. 1419, +24, -1.)">{shown}</span>
    return <input className="ed-timecode ed-timecode-entry" aria-label="Timecode: type, then Enter. Esc cancels." value={timecodeEntry.text}
      ref={element => { if (element && document.activeElement !== element) { element.focus(); element.setSelectionRange(element.value.length, element.value.length) } }}
      onChange={e => setTimecodeEntry({ target, text: e.target.value.replace(/[^0-9+\-.:;]/g, '') })} onBlur={() => setTimecodeEntry(null)}
      onKeyDown={e => {
        if (e.key === 'Escape') { e.preventDefault(); setTimecodeEntry(null) }
        if (e.key === 'Enter') { e.preventDefault(); applyTimecode(target, timecodeEntry.text); setTimecodeEntry(null) }
      }} />
  }
  const commands: Record<string, () => void> = {
    'play.toggle': () => { if (viewerTransport) setSourceRate(r => r ? 0 : 1); else if (sequence) togglePlayback() },
    'play.reverse': () => kHeld.current ? step(-1) : shuttle(-1),
    'play.stop': () => { if (viewerTransport) setSourceRate(0); else stopProgram() },
    'play.forward': () => kHeld.current ? step(1) : shuttle(1),
    'play.inToOut': () => playSegment(Math.max(viewStart, marks.in ?? viewStart), Math.min(viewEnd, (marks.out ?? viewEnd - 1) + 1)),
    'play.around': () => playSegment(Math.max(viewStart, frame - 48), Math.min(viewEnd, frame + 48), frame),
    'play.loop': () => { setLoop(value => !value); setStatus(loop ? 'Loop playback off' : 'Loop playback on') },
    'nav.prevFrame': () => step(-1), 'nav.nextFrame': () => step(1),
    'nav.back1s': () => step(-24), 'nav.fwd1s': () => step(24),
    'nav.prevEdit': () => editStep(-1), 'nav.nextEdit': () => editStep(1),
    'nav.start': () => { if (viewerTransport) seekSource(0); else goto(viewStart) },
    'nav.end': () => { if (viewerTransport) seekSource(sourceFrames - 1); else goto(viewEnd - 1) },
    'nav.in': () => { if (marks.in === undefined) setStatus('No In point is set.'); else goto(marks.in) },
    'nav.out': () => { if (marks.out === undefined) setStatus('No Out point is set.'); else goto(marks.out) },
    'nav.prevMarker': () => markerStep(-1), 'nav.nextMarker': () => markerStep(1),
    'nav.matchFrame': matchFrame,
    'nav.prevTake': () => takeStep(-1), 'nav.nextTake': () => takeStep(1),
    'mark.in': () => setMark('in', frame), 'mark.out': () => setMark('out', frame),
    'mark.clearIn': () => setMark('in'), 'mark.clearOut': () => setMark('out'),
    'mark.clearBoth': () => { setMarks({}); setStatus('In and Out cleared') },
    'mark.clip': markClip,
    'mark.add': () => { if (!markers.includes(frame)) changeMarkers([...markers, frame].sort((a, b) => a - b)); setStatus(`Marker at ${timecode(frame - viewStart)}`) },
    'mark.delete': () => { if (!markers.includes(frame)) { setStatus('No marker at the playhead.'); return }; changeMarkers(markers.filter(m => m !== frame)); setStatus('Marker deleted') },
    'mark.deleteAll': () => { changeMarkers([]); setStatus('All markers deleted') },
    'edit.overwrite': overwrite,
    'edit.lift': () => { if (placement && !busy && !nestedBed) void removePlacement(); else setStatus('Select a placed action to lift it.') },
    'edit.nudgeLeft': () => nudgeBy(-1), 'edit.nudgeRight': () => nudgeBy(1),
    'edit.nudgeLeftMulti': () => nudgeBy(-5), 'edit.nudgeRightMulti': () => nudgeBy(5),
    'edit.deselect': () => { setSelection(''); setStatus('Selection cleared') },
    'edit.undo': () => void undo(), 'edit.redo': () => void undo(true),
    'edit.save': save,
    'edit.newAction': () => startCreate(),
    'edit.makeTake': () => { if (!data.worker.connected) setError('The worker is offline, so no take can be requested.'); else void requestTake() },
    'edit.export': () => { if (!sequence || dirty || ['exporting', 'queued'].includes(sequence.status)) setStatus(dirty ? 'Apply changes before exporting.' : 'Nothing to export yet.'); else void exportSequence() },
    'timeline.zoomIn': () => zoom(1), 'timeline.zoomOut': () => zoom(-1),
    'timeline.fit': () => { if (fit) { setFit(false); setScale(8) } else setFit(true) },
    'timeline.trackSize': cycleTracks,
    'window.viewer': () => focusPane('viewer'), 'window.canvas': () => focusPane('canvas'),
    'window.timeline': () => focusPane('timeline'), 'window.browser': () => focusPane('browser'),
    'window.toggleMonitor': () => focusPane(activePane === 'viewer' ? 'canvas' : 'viewer'),
    'window.standard': () => chooseLayout('standard'), 'window.allTracks': () => chooseLayout('all-tracks'),
    'window.tools': () => setHideTools(value => !value),
    'window.find': () => { setBrowser('actions'); setActivePane('browser'); setMobileMonitor('viewer'); requestAnimationFrame(() => { search.current?.focus(); search.current?.select() }) },
    'window.import': () => props.onImport(),
    'window.keyboard': () => setLayoutOpen(true),
  }
  const onKey = useRef<(event: KeyboardEvent) => void>(() => {})
  onKey.current = event => {
    if (event.defaultPrevented || event.isComposing || layoutOpen || !shell.current?.isConnected || document.querySelector('dialog[open]')) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target && target !== document.body && !shell.current.contains(target)) return // Another window has focus.
    const chord = chordFromEvent(event)
    if (!chord) return
    const id = index.get(chord), command = id ? COMMAND_BY_ID.get(id) : undefined
    const typing = !!target && isTyping(target)
    if (typing && !command?.inText) return
    if (!typing && target && nativeKey(target, chord)) return
    if (!command) {
      // FCP7: typing digits or +/- over a monitor or the Timeline starts timecode entry.
      if (!event.ctrlKey && !event.altKey && !event.metaKey && /^[0-9+-]$/.test(event.key) && activePane !== 'browser') {
        event.preventDefault(); setTimecodeEntry({ target: viewerTransport ? 'source' : 'program', text: event.key })
      }
      return
    }
    event.preventDefault()
    if (event.repeat && !command.repeat) return
    if (command.id === 'play.stop') { kHeld.current = true; kCode.current = event.code }
    commands[command.id]?.()
  }
  useEffect(() => {
    const down = (event: KeyboardEvent) => onKey.current(event)
    const up = (event: KeyboardEvent) => { if (event.code === kCode.current) kHeld.current = false }
    const release = () => { kHeld.current = false }
    window.addEventListener('keydown', down); window.addEventListener('keyup', up); window.addEventListener('blur', release)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', release); window.clearTimeout(nudgeTimer.current) }
  }, [])
  async function exportSequence() {
    if (!sequence || busy) return
    setBusy(true); setError('')
    try { const result = await api<SubjectSequence>(`pilots/${sequence.id}/export`, {}); setSequence(result); await refresh(); setStatus('CPU export queued. You can follow its progress in Jobs.'); setBrowser('jobs') }
    catch (problem) { setError(message(problem, 'The export could not start.')) }
    finally { setBusy(false) }
  }
  const dirty = !!config && !!saved && JSON.stringify(config) !== JSON.stringify(saved.config)
  const currentMask = showMask ? profile?.mask_url : undefined
  const canPlace = !nestedBed && candidate?.status === 'approved' && !!saved?.clips.some(c => c.id === candidate.id && !c.role.toLowerCase().includes('idle'))

  return <section ref={shell} className="editor-shell" data-layout={layout} data-fit-tracks={fitTracks} data-tools-hidden={hideTools} style={{ '--ed-upper': `${upperHeight}px` } as CSSProperties} data-active-pane={activePane} tabIndex={-1} aria-label="Scene timeline editor"
    onPointerDownCapture={e => { const pane = paneOf(e.target); if (pane) setActivePane(pane) }} onFocusCapture={e => { const pane = paneOf(e.target); if (pane) setActivePane(pane) }}>
    <header className="ed-titlebar"><strong><Icon name="radio" size={15} />Scene animation</strong><span>{scene?.title ?? 'No scene selected'} — {config?.title ?? 'Sequence'}</span><button onClick={props.onLegacy}>Film editor ↗</button></header>
    <nav className="ed-menubar" aria-label="Editor commands"><button title={titled('Import scene', 'window.import')} onClick={props.onImport}>Import scene…</button><button title={titled('Undo', 'edit.undo')} disabled={!history.length || busy} onClick={() => void undo()}>Undo</button><button title={titled('Redo', 'edit.redo')} disabled={!future.length || busy} onClick={() => void undo(true)}>Redo</button><button title={titled('Create action', 'edit.newAction')} onClick={() => startCreate()}>New action</button><button onClick={() => { setViewer('subjects'); setBrowser('subjects'); setMobileMonitor('viewer') }}>Subject setup</button><button onClick={props.onWorker}><span className={`ed-worker-light ${data.worker.connected ? 'online' : ''}`} />Worker</button><details className="ed-view-menu" ref={viewMenu} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) event.currentTarget.open = false }} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus() } }}>
      <summary>View</summary><div className="ed-view-options" role="group" aria-label="View options">
        <span className="ed-view-heading">Layout</span>
        <button aria-pressed={layout === 'standard'} onClick={() => chooseLayout('standard')}>Standard layout{key('window.standard') ? <kbd>{key('window.standard')}</kbd> : null}</button>
        <button aria-pressed={layout === 'all-tracks'} onClick={() => chooseLayout('all-tracks')}>All tracks overview{key('window.allTracks') ? <kbd>{key('window.allTracks')}</kbd> : null}</button>
      </div></details><button title={titled('Keyboard layout', 'window.keyboard')} onClick={() => setLayoutOpen(true)}>Keyboard…</button><span className="ed-menu-spacer" /><button aria-pressed={hideTools} onClick={() => setHideTools(value => !value)}>{hideTools ? 'Show tools' : 'Hide tools'}</button><button disabled={!sequence || busy || dirty || ['exporting', 'queued'].includes(sequence.status)} onClick={() => void exportSequence()}>Export sequence…</button></nav>
    <div className="ed-upper" data-mobile-monitor={mobileMonitor}>
      <aside className="ed-browser ed-pane" aria-label="Browser" tabIndex={-1}>
        <h2 className="ed-pane-title">Browser <span>{scene?.title}</span></h2>
        <div className="ed-tabs" aria-label="Browser content">{(['actions', 'subjects', 'effects', 'jobs'] as BrowserTab[]).map(tab => <button key={tab} aria-pressed={browser === tab} onClick={() => setBrowser(tab)}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}</div>
        <div className="ed-browser-scene"><label>Scene<select value={scene?.id ?? ''} disabled={busy} onChange={e => onScene(e.target.value)}>{data.scenes.map(s => <option value={s.id} key={s.id}>{s.title}</option>)}</select></label><button title="Import a scene" aria-label="Import a scene" onClick={props.onImport}><Icon name="plus" size={15} /></button></div>
        <div className="ed-browser-body">
          {browser === 'actions' ? <><button className="ed-primary ed-new-action" onClick={() => startCreate()}><Icon name="plus" size={14} />Create action</button><label className="ed-search"><span className="sr-only">Search actions</span><input ref={search} type="search" placeholder="Find an action…" title={titled('Find an action', 'window.find')} value={query} onChange={e => setQuery(e.target.value)} /></label><div className="ed-list-heading"><span>Action / take</span><span>Status</span></div>{actionProfiles.filter(p => `${p.name} ${p.actor}`.toLowerCase().includes(query.toLowerCase())).map(p => {
            const variants = data.candidates.filter(c => c.scene_id === scene?.id && profileFor(c, profiles)?.id === p.id).sort(takeOrder)
            return <div className="ed-action-bin" key={p.id}><button className={`ed-bin-folder ${profile?.id === p.id ? 'selected' : ''}`} onClick={() => chooseAction(p)}><Icon name="chevron" size={11} /><strong>{p.name}</strong><small>{readable(p.actor)}</small><span>{variants.length}</span></button>{profile?.id === p.id ? variants.map((take, i) => <button key={take.id} className={`ed-bin-take ${candidate?.id === take.id ? 'selected' : ''}`} draggable={take.status === 'approved'} onDragStart={e => e.dataTransfer.setData('application/x-llr-action', JSON.stringify({ candidate: take.id }))} onClick={() => chooseAction(p, take)}><img src={take.frames.start} alt="" /><span>Take {i + 1}<small>{take.metadata.outputs[0]?.properties.duration_seconds.toFixed(2)}s</small></span><span className={`ed-take-status ${take.status}`}>{take.status === 'candidate' ? 'Review' : take.status}</span></button>) : null}</div>
          })}{!actionProfiles.length ? <p className="ed-empty">Create a returning action for this scene. Approved idles are configured under Subjects.</p> : null}<details className="ed-excluded"><summary>Unavailable to this sequence ({saved?.excluded.length ?? 0})</summary>{saved?.excluded.map(item => <p key={item.id}><strong>{item.label}</strong><br />{item.reason}</p>)}</details></> : null}
          {browser === 'subjects' ? <><p className="ed-help">Automatic idles are set up once per subject.</p>{config?.subjects.map(s => <button className={`ed-subject-item ${subject === s.actor ? 'selected' : ''}`} key={s.actor} onClick={() => { setSubject(s.actor); setViewer('subjects'); setMobileMonitor('viewer') }}><Icon name="settings" size={15} /><span><strong>{readable(s.actor)}</strong><small>{s.pool.length} idle takes · {s.mode === 'still' ? 'Hold' : s.mode}</small></span></button>)}{!config?.subjects.length ? <p className="ed-empty">Create an action with a named subject to add its track.</p> : null}</> : null}
          {browser === 'effects' ? <><p className="ed-help">Rain and steam use saved regions. Video texture covers the whole picture.</p><button className={`ed-subject-item ${effect === 'texture' ? 'selected' : ''}`} onClick={() => { setEffect('texture'); setViewer('effects'); setMobileMonitor('viewer') }}><Icon name="spark" size={15} /><span><strong>Video texture</strong><small>Whole picture · adjustable film grain</small></span></button>{ambientLayers.map(layer => <button className={`ed-subject-item ${effect === layer.kind ? 'selected' : ''}`} key={layer.kind} onClick={() => { setEffect(layer.kind); setViewer('effects'); setMobileMonitor('viewer') }}><Icon name="spark" size={15} /><span><strong>{layer.label}</strong><small>{layer.kind === 'rain' ? 'Window region · background' : 'Mug region · fixed plume'}</small></span></button>)}{!ambientLayers.length ? <p className="ed-empty">This scene has no saved effect regions.</p> : null}</> : null}
          {browser === 'jobs' ? <><button className="ed-wide" onClick={props.onWorker}>Worker & connection settings</button>{data.jobs.filter(job => job.scene_id === scene?.id).map(job => <div className="ed-job" key={job.id}><strong>{job.label}</strong><span>{job.status}</span>{job.error ? <p role="alert">{job.error.message}</p> : null}</div>)}{sequence ? <div className="ed-job"><strong>Sequence export</strong><span>{sequence.status} {sequence.status === 'exporting' ? `${Math.round(sequence.progress * 100)}%` : ''}</span>{sequence.error ? <p role="alert">{sequence.error.message}</p> : null}{sequence.media_url ? <a href={sequence.media_url} download>Download MP4</a> : null}<a href={sequence.manifest_url} download>Saved manifest</a><a href={sequence.log_url} download>Event log</a></div> : null}</> : null}
        </div>
        <footer className="ed-pane-foot">{browser === 'actions' ? 'Actions → takes → approval → timeline' : 'Settings belong to this scene'}</footer>
      </aside>
      <section className="ed-viewer ed-pane" aria-label="Viewer" tabIndex={-1}>
        <h2 className="ed-pane-title">Viewer <span>{viewer === 'audition' ? profile?.name ?? 'Action audition' : viewer === 'create' ? authoringIdle ? 'Create subject idle' : 'Create action' : viewer === 'subjects' ? 'Subject setup' : viewer === 'mask' ? 'Adjust motion area' : viewer === 'audio' ? 'Sound & music' : 'Effects'}</span></h2>
        <div className="ed-tabs" aria-label="Viewer mode">{(['audition', 'create', 'subjects', 'effects', 'audio'] as ViewerTab[]).map(tab => <button key={tab} aria-pressed={viewer === tab} onClick={() => tab === 'create' ? startCreate() : setViewer(tab)}>{tab === 'create' ? 'Create action' : tab === 'subjects' ? 'Subject setup' : tab[0].toUpperCase() + tab.slice(1)}</button>)}</div>
        <div className="ed-viewer-content">
          {viewer === 'audio' && config ? <AudioWorkspace key={config.scene_id} config={config} busy={busy} frame={frame} onChange={setConfig} onApply={() => void commit(config)} /> : null}
          {viewer === 'create' ? <MotionGuide key={authoringIdle ? `idle:${activeSubject?.actor}` : 'action'} actionOnly={!authoringIdle} idleOnly={authoringIdle} initialActor={authoringIdle ? activeSubject?.actor : undefined} data={data} scene={scene} onScene={onScene} onImport={props.onImport} onCancel={() => setViewer(authoringIdle ? 'subjects' : 'audition')} refresh={refresh} onSaved={p => { setSelectedProfile(p.id); setSelectedTake(''); setViewer(authoringIdle ? 'subjects' : 'audition'); setStatus(authoringIdle ? 'Idle saved. Review its takes in Subject setup.' : 'Action saved. New takes appear in the Browser.'); void api<EditorState>(`editor/${p.scene_id}`).then(result => { setSaved(result); setConfig(result.config) }).catch(problem => setError(message(problem, 'Could not reload subject tracks.'))) }} /> : null}
          {viewer === 'mask' && candidate && profile && scene ? <AdjustMotionArea candidate={candidate} profile={profile} scene={scene} onCancel={() => setViewer('audition')} onSaved={async take => { await refresh(); setSelectedTake(take.id); setSelectedProfile(take.metadata.motion?.profile_id ?? profile.id); setViewer('audition'); setStatus('Corrected take saved separately. Review it before placing it.') }} /> : null}
          {viewer === 'audition' ? candidate ? <>
            <div className="ed-monitor-meta"><span>{readable(profile?.actor ?? '')} · Take {takes.indexOf(candidate) + 1} of {takes.length}</span><span className={`ed-take-status ${candidate.status}`}>{candidate.status === 'candidate' ? 'Needs review' : candidate.status}</span>{!compareTakes ? <label><input type="checkbox" checked={showMask} onChange={e => setShowMask(e.target.checked)} />Mask</label> : null}<button aria-pressed={compareTakes} onClick={() => { setSourcePlaying(false); setSourceFrame(0); setCompareTakes(value => !value) }}>{compareTakes ? 'Single take' : 'Compare takes'}</button></div>
            {compareTakes ? <TakeComparison key={candidate.id} candidate={candidate} options={data.candidates} profiles={profiles} /> : <>
            <div className="ed-source-stage"><video key={candidate.id} ref={sourceVideo} src={candidate.media_url} poster={candidate.frames.start} muted playsInline loop preload="metadata" aria-label={`Audition ${candidate.label}`} onTimeUpdate={e => { if (sourceRate >= 0) setSourceFrame(Math.floor(e.currentTarget.currentTime * 24)) }} onLoadedMetadata={applyPendingSourceSeek} onError={() => setError(`Could not load ${candidate.label}.`)} />{currentMask ? <div className="ed-mask-overlay" style={{ maskImage: `url("${currentMask}")`, WebkitMaskImage: `url("${currentMask}")` }} /> : null}</div>
            <div className="ed-transport">{timecodeField('source', timecode(sourceFrame))}{sourceRate && sourceRate !== 1 ? <span className="ed-shuttle" aria-live="polite">{sourceRate > 0 ? '▶▶' : '◀◀'} {Math.abs(sourceRate)}×</span> : null}<button aria-label="Previous take" title={titled('Previous take', 'nav.prevTake')} disabled={takes.indexOf(candidate) <= 0} onClick={() => setSelectedTake(takes[takes.indexOf(candidate) - 1].id)}>◀|</button><button className="ed-round-play" aria-label={sourcePlaying ? 'Pause audition' : 'Play audition'} title={titled(sourcePlaying ? 'Pause' : 'Play', 'play.toggle')} onClick={() => setSourceRate(r => r ? 0 : 1)}><Icon name={sourcePlaying ? 'pause' : 'play'} size={15} /></button><button aria-label="Next take" title={titled('Next take', 'nav.nextTake')} disabled={takes.indexOf(candidate) >= takes.length - 1} onClick={() => setSelectedTake(takes[takes.indexOf(candidate) + 1].id)}>|▶</button><span>{(sourceFrames / 24).toFixed(2)}s</span></div>
            <label className="ed-source-seek"><span className="sr-only">Audition position</span><input type="range" min={0} max={Math.max(0, sourceFrames - 1)} step={1} value={Math.min(sourceFrame, sourceFrames - 1)} onChange={e => { const next = Number(e.target.value); setSourceFrame(next); if (sourceVideo.current) sourceVideo.current.currentTime = next / 24 }} /></label>
            </>}
            <div className="ed-action-commands"><button disabled={busy || !data.worker.connected} onClick={() => void requestTake()}><Icon name="refresh" size={13} />Make another take</button>{candidate.can_adjust_area ? <button disabled={busy} onClick={() => { setSourcePlaying(false); setViewer('mask') }}><Icon name="settings" size={13} />Adjust mask…</button> : null}<button className="ed-primary" title={titled(marks.in !== undefined ? 'Overwrite at In' : 'Overwrite at playhead', 'edit.overwrite')} disabled={busy || !canPlace || dirty} draggable={canPlace && !busy && !dirty} onDragStart={e => e.dataTransfer.setData('application/x-llr-action', JSON.stringify({ candidate: candidate.id }))} onClick={() => void place(candidate.id, marks.in ?? frame)}><Icon name="arrow" size={14} />{marks.in !== undefined ? 'Place at In' : 'Place at playhead'}</button></div>
            <div className="ed-review">{!compareTakes ? <div className="ed-boundaries">{(['start', 'middle', 'end'] as const).map(part => <figure key={part}><button onClick={() => { setSourcePlaying(false); const at = part === 'start' ? 0 : part === 'middle' ? Math.floor(sourceFrames / 2) : sourceFrames - 1; setSourceFrame(at); if (sourceVideo.current) sourceVideo.current.currentTime = at / 24 }}><img src={candidate.frames[part]} alt={`${part} frame`} /></button><figcaption>{part === 'middle' ? 'Mid-action' : part === 'start' ? 'First frame' : 'Last frame'}</figcaption></figure>)}</div> : null}<details open={candidate.status === 'candidate'}><summary>Review this take</summary><label className="ed-field">Notes<textarea rows={2} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Check the action, identity, props and endpoint joins." /></label><div className="ed-field-row"><label className="ed-field">Start anchor<input value={entry} maxLength={200} onChange={e => setEntry(e.target.value)} /></label><label className="ed-field">End anchor<input value={exit} maxLength={200} onChange={e => setExit(e.target.value)} /></label></div><label className="ed-check"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} />I checked the action, master and start/end frames.</label><div className="ed-action-commands"><button disabled={busy || candidate.status === 'rejected'} onClick={() => void review('rejected')}>Reject take</button><button className="ed-primary" disabled={busy || !checked || !entry.trim() || !exit.trim() || candidate.status === 'approved'} onClick={() => void review('approved')}>Approve take</button></div></details></div>
          </> : <div className="ed-monitor-empty"><Icon name="play" size={36} /><strong>{profile?.name ?? 'Action audition'}</strong><p>{profile ? 'This action has no takes yet.' : 'Choose an action in the Browser, or create one.'}</p>{profile ? <button className="ed-primary" disabled={busy || !data.worker.connected} onClick={() => void requestTake()}>Make first take</button> : <button className="ed-primary" onClick={() => startCreate()}>Create action</button>}</div> : null}
          {viewer === 'subjects' ? activeSubject ? <div className="ed-setup"><h3>{readable(activeSubject.actor)} · automatic idles</h3><p className="ed-help">Motions take priority. Gaps use approved idle takes, then an exact held frame when no complete take fits.</p><label className="ed-field">Subject<select value={activeSubject.actor} onChange={e => setSubject(e.target.value)}>{config?.subjects.map(s => <option key={s.actor} value={s.actor}>{readable(s.actor)}</option>)}</select></label><label className="ed-field">Idle pacing<select value={activeSubject.mode} onChange={e => updateSubject({ mode: e.target.value as SubjectSettings['mode'] })}><option value="continuous">Continuous idles</option><option value="spaced">Idles with quiet holds (4–8 seconds)</option><option value="still">Hold current pose</option></select></label><label className="ed-field">Variation seed<input type="number" min={0} max={2147483647} step={1} value={activeSubject.seed} onChange={e => updateSubject({ seed: Number(e.target.value) })} /></label>            <button onClick={() => startCreate(true)}><Icon name="plus" size={13} />Create idle for this subject</button>
            <details className="ed-idle-review"><summary>Review idle takes</summary>{profiles.filter(p => p.actor.toLowerCase() === activeSubject.actor.toLowerCase() && p.role.toLowerCase().includes('idle') && returning(p, scene?.id ?? '')).map(p => <div key={p.id}><strong>{p.name}</strong>{data.candidates.filter(c => profileFor(c, profiles)?.id === p.id).sort(takeOrder).map((take, i) => <button key={take.id} onClick={() => { setSelectedProfile(p.id); setSelectedTake(take.id); setViewer('audition'); setSourcePlaying(false) }}>Take {i + 1} · {take.status === 'candidate' ? 'Needs review' : take.status}</button>)}</div>)}</details>
            <fieldset className="ed-idle-pool"><legend>Approved idle pool</legend>{saved?.clips.filter(c => c.actor === activeSubject.actor && c.role.toLowerCase().includes('idle')).map(clip => <label className="ed-check" key={clip.id}><input type="checkbox" checked={activeSubject.pool.includes(clip.id)} onChange={e => updateSubject({ pool: e.target.checked ? [...activeSubject.pool, clip.id] : activeSubject.pool.filter(id => id !== clip.id) })} /><span>{clip.label}<small>{(clip.frames / 24).toFixed(2)} seconds</small></span></label>)}{!saved?.clips.some(c => c.actor === activeSubject.actor && c.role.toLowerCase().includes('idle')) ? <p className="ed-help">No dedicated idle takes yet. Choose a compatible returning motion below, or leave the pool empty to hold the pose.</p> : null}</fieldset>
            <details className="ed-idle-review"><summary>Use other approved returning motions as idles</summary><p className="ed-help">Explicitly choose subtle motions that suit this subject’s idle behavior. Nothing is added automatically.</p>{saved?.clips.filter(c => c.actor === activeSubject.actor && !c.role.toLowerCase().includes('idle')).map(clip => <label className="ed-check" key={clip.id}><input type="checkbox" checked={activeSubject.pool.includes(clip.id)} onChange={e => updateSubject({ pool: e.target.checked ? [...activeSubject.pool, clip.id] : activeSubject.pool.filter(id => id !== clip.id) })} /><span>{clip.label}<small>Approved returning motion · {(clip.frames / 24).toFixed(2)} seconds</small></span></label>)}{!saved?.clips.some(c => c.actor === activeSubject.actor && !c.role.toLowerCase().includes('idle')) ? <p className="ed-help">No other compatible approved motions for this subject.</p> : null}</details>
            <button className="ed-primary" disabled={busy || !config} onClick={() => config && void commit(config)}>Apply subject setup</button><p className="ed-help">The automatic idle lane is generated from these settings. Place deliberate actions on Motions.</p></div> : <p className="ed-empty">Name a subject when creating an action to begin subject setup.</p> : null}
          {viewer === 'effects' && effect === 'texture' ? <TextureControls value={config?.texture} onChange={texture => config && setConfig({ ...config, texture })} onApply={() => config && void commit(config)} busy={busy || !config} dirty={dirty} /> : viewer === 'effects' ? <div className="ed-setup"><h3>{effect === 'rain' ? 'Window rain' : 'Mug steam'}</h3>{ambientLayers.some(l => l.kind === effect) ? <><label className="ed-field">Effect<select value={effect} onChange={e => setEffect(e.target.value as 'rain' | 'steam')}>{ambientLayers.map(l => <option key={l.kind} value={l.kind}>{l.label}</option>)}</select></label><label className="ed-field">Strength · {Math.round((config?.ambience.find(a => a.kind === effect)?.opacity ?? 0) * 100)}%<input type="range" min={0} max={40} step={1} value={Math.round((config?.ambience.find(a => a.kind === effect)?.opacity ?? 0) * 100)} onChange={e => updateEffect(Number(e.target.value) / 100)} /></label><div className="ed-effect-region">{sequence?.manifest.ambience?.layers.some(l => l.kind === effect) ? <img src={`/api/pilots/${sequence.id}/ambience/${effect}`} alt={`Saved ${effect} effect mask: white pixels animate, black pixels protected`} /> : <Icon name="lock" size={30} />}<p>{effect === 'rain' ? 'Saved window region; subject motion regions and foreground stay protected.' : 'Saved fixed mug plume. Procedural steam pauses during placed actions; the plume painted in the master remains.'}</p></div><p className="ed-help">Timing: absolute sequence clock. Effects continue across idle and hold cuts. Saved effect regions are fixed in this version.</p><button className="ed-primary" disabled={busy || !config} onClick={() => config && void commit(config)}>Apply effect settings</button></> : <p className="ed-help">This scene has no saved {effect} region.</p>}</div> : null}
        </div>
        <footer className="ed-pane-foot">{viewer === 'audition' ? 'Viewer · source take · no timeline edits until placed' : viewer === 'subjects' ? 'Automatic idles · subject settings' : 'Scene tools'}</footer>
      </section>
      <section className="ed-program ed-pane" aria-label="Canvas" tabIndex={-1}>
        <h2 className="ed-pane-title">Canvas <span>{config?.title ?? 'Sequence'}</span></h2>
        <div className="ed-monitor-meta"><span>{scene?.width} × {scene?.height} · 24 fps</span><span>Fit</span><span>{sequence ? 'Draft sequence' : 'Canonical still'}</span></div>
        <div className="ed-program-picture">{scene ? <EditorCanvas scene={scene} sequence={sequence} frame={frame} playing={rate > 0} rate={rate} texture={config?.texture} onError={setPlaybackError} /> : <p className="ed-empty">Import a scene to begin.</p>}</div>
        <div className="ed-program-caption">{sequence ? sequence.manifest.tracks.map(track => { const current = track.events.find(e => e.start_frame <= frame && frame < e.end_frame); return <span key={track.actor}><strong>{readable(track.actor)}</strong> · {current?.label ?? 'Hold'}</span> }) : <span>Build the sequence to preview automatic idles and placed actions.</span>}</div>
        <div className="ed-transport">{timecodeField('program', timecode(frame - viewStart))}{rate && rate !== 1 ? <span className="ed-shuttle" aria-live="polite">{rate > 0 ? '▶▶' : '◀◀'} {Math.abs(rate)}×</span> : null}{loop ? <span className="ed-shuttle" title={titled('Loop playback', 'play.loop')}>Loop</span> : null}<button aria-label="Go to sequence start" title={titled('Go to start', 'nav.start')} onClick={() => goto(viewStart)}>◀|</button><button aria-label="Previous frame" title={titled('Previous frame', 'nav.prevFrame')} onClick={() => goto(frame - 1)}>◀</button><button className="ed-round-play" disabled={!sequence} aria-label={playing ? 'Pause sequence' : 'Play sequence'} title={titled(playing ? 'Pause' : 'Play', 'play.toggle')} onClick={togglePlayback}><Icon name={playing ? 'pause' : 'play'} size={17} /></button><button aria-label="Next frame" title={titled('Next frame', 'nav.nextFrame')} onClick={() => goto(frame + 1)}>▶</button><span>{timecode(viewEnd - viewStart)}</span></div>
        <label className="ed-canvas-seek"><span className="sr-only">Sequence position</span><input type="range" min={viewStart} max={viewEnd - 1} step={1} value={frame} onChange={e => seek(Number(e.target.value))} /></label>
        <details className="ed-sequence-details" open={layout === 'standard' ? true : undefined}><summary>Sequence settings</summary><div className="ed-sequence-setup"><label>Sequence<input aria-label="Sequence title" maxLength={100} value={config?.title ?? ''} disabled={!config || busy} onChange={e => config && setConfig({ ...config, title: e.target.value })} /></label><label>Length (seconds)<input type="number" min={1} max={600} value={(config?.duration_frames ?? 14400) / 24} disabled={!config || busy} onChange={e => config && setConfig({ ...config, duration_frames: Math.round(Number(e.target.value) * 24) })} /></label><button className="ed-primary" disabled={!config || busy || loading} onClick={() => config && void commit(config)}>{busy ? 'Saving…' : sequence ? dirty ? 'Apply changes' : 'Rebuild sequence' : 'Build sequence'}</button></div></details>
        {placement ? <form className="ed-placement" onSubmit={e => { e.preventDefault(); void place(placement.candidate_id, Math.round(Number(placeAt) * 24), placement.id) }}><strong>{saved?.clips.find(c => c.id === placement.candidate_id)?.label}</strong><label>Start (seconds)<input type="number" min={0} step={1 / 24} value={placeAt} onChange={e => setPlaceAt(e.target.value)} /></label><button disabled={busy}>Move</button><button type="button" title={titled('Lift', 'edit.lift')} disabled={busy} onClick={() => void removePlacement()}>Remove</button></form> : null}
        <footer className="ed-pane-foot">{sequence ? `Saved revision ${saved?.revision} · joins require review` : 'Locked master · approved actions only'}</footer>
      </section>
    </div>
    <div className="ed-monitor-switch"><button aria-pressed={mobileMonitor === 'viewer'} onClick={() => setMobileMonitor('viewer')}>Viewer / action tools</button><button aria-pressed={mobileMonitor === 'canvas'} onClick={() => setMobileMonitor('canvas')}>Canvas / sequence</button></div>
    <div className="ed-divider" role="separator" aria-label="Resize monitors and timeline" aria-orientation="horizontal" aria-valuenow={upperHeight} aria-valuemin={monitorHeight(availableHeight, 0, desiredTimeline, false)} aria-valuemax={monitorHeight(availableHeight, availableHeight, desiredTimeline, false)} tabIndex={0} onPointerDown={resize} onKeyDown={e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); setFitTracks(false); setRequestedHeight(monitorHeight(availableHeight, upperHeight + (e.key === 'ArrowUp' ? -20 : 20), desiredTimeline, false)) } }} />
    <SequenceTimeline config={config} sequence={sequence} frame={frame} scale={scale} busy={busy} dirty={dirty} selection={selection}
      sceneTitle={scene?.title ?? 'Scene'} effects={ambientLayers.map(layer => layer.kind)} nested={nestedBed}
      layout={layout} trackReset={trackReset} density={density} onDensity={value => { setRequestedHeight(upperHeight); setFitTracks(false); setDensity(value) }}
      onScale={setScale} onSeek={seek} onDrop={drop}
      fit={fit} onFit={setFit} playing={playing} nudge={nudge} marks={marks} markers={markers}
      hints={`${key('play.toggle')} play · ${[key('play.reverse'), key('play.stop'), key('play.forward')].filter(Boolean).join('/')} shuttle · ${key('mark.in')}/${key('mark.out')} In/Out · ${key('nav.prevEdit')}/${key('nav.nextEdit')} edits · ${key('window.keyboard')} all keys`}
      onNested={bed => { setPlaying(false); setNestedBed(bed); setSelection(''); if (bed) { setFrame(bed.start_frame); setSeekVersion(v => v + 1) }; setStatus(bed ? `${bed.name} contents · source timing preserved` : 'Episode sequence') }}
      onSubject={actor => { setSubject(actor); setViewer('subjects'); setBrowser('subjects'); setMobileMonitor('viewer') }}
      onAudio={() => { setViewer('audio'); setMobileMonitor('viewer') }}
      onEffect={kind => { setEffect(kind); setViewer('effects'); setBrowser('effects'); setMobileMonitor('viewer') }}
      onEvent={event => { if (event.origin === 'motion') { setSelection(event.placement_id ?? ''); setPlaceAt(String(event.start_frame / 24)) }; const take = data.candidates.find(c => c.id === event.variant_id); const action = take && profileFor(take, profiles); if (take && action) chooseAction(action, take); else { setSubject(event.actor); setViewer('subjects'); setMobileMonitor('viewer') } }} />
    {layoutOpen ? <KeyboardLayout keymap={keymap} onChange={changeKeymap} onClose={() => { setLayoutOpen(false); shell.current?.focus({ preventScroll: true }) }} /> : null}
    {error ? <div className="ed-error" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss editor error">×</button></div> : null}
    <footer className="ed-status" role="status"><span>{loading ? 'Opening saved sequence…' : busy ? 'Saving and validating media…' : dirty ? 'Settings changed — apply to update the saved sequence and preview.' : status}</span><span>{data.worker.connected ? 'Worker connected' : 'Worker offline'} · local project</span></footer>
  </section>
}



