import { useEffect, useMemo, useRef, useState } from 'react'
import KeyboardLayout from './KeyboardLayout'
import type { Keymap } from './shortcuts'
import { parseTimecodeEntry, serializeKeymap, stepPoint } from './shortcuts'
import { addEdit, auditionWindow, cutAudioRange, extractRange, liftRange, editPointFrame, editPoints, editRange, itemStart, moveClip, nearestCut, placeTake, resolveSpot, snapFrame, extendEdit, fitToPicture, insertEdit, isGap, liftEdit, nearestEditPoint, overwriteEdit, replaceEdit, rippleDelete, slipEdit, trimEdit } from './filmEdits'
import type { AuditionAudio, AuditionVideo, AuditionWindow, EditPoint, EditResult, EditShot, TakeSpot, VideoShot } from './filmEdits'
import OwnedTake from './OwnedTake'
import { ReadOnlyReceipt } from './ReadOnlyReceipt'
import { ClipPrompt } from './ClipPrompt'
import { DeleteClips, type DeletableClip } from './DeleteClips'
import { promptOf } from './promptOf'
import ShotGeneration, { SHOT_BASE, type Take as ShotTake } from './ShotGeneration'
import AuditionPlayer from './AuditionPlayer'
import FilmMenuBar from './FilmMenuBar'
import type { MenuAction } from './filmMenus'
import Thumb from './Thumb'
import { clearThumbQueue } from './thumbs'
import { api, encodeFile } from './api'
import AudioWorkspace from './AudioWorkspace'
import AudioWaveform from './AudioWaveform'
import FilmGeneration from './FilmGeneration'
import type { ContinuationDraft, GenControl, GenSnapshot } from './FilmGeneration'
import MusicGeneration from './MusicGeneration'
import FilmShotPlan from './FilmShotPlan'
import type { PlannedSetup } from './FilmShotPlan'
import FilmStory, { StoryRehearsal } from './FilmStory'
import type { StoryManifest } from './FilmStory'
import type { GenerationJob, GenerationPlacement, GenerationTarget } from './GenerationFlow'
import { JobMetadata, JobStage, generationStage } from './GenerationFlow'
import { useProgramAudio } from './useProgramAudio'
import type { AudioAsset, AudioPlacement, EditorConfig } from './editorTypes'
import FilmBin, { FoldHead, useFold, useUserBins, updateUserBins, moveToUserBin, createUserBin, sourceKey } from './FilmBin'
import FilmHistory, { importTakeJob, resumeJob } from './FilmHistory'
import GenerationGuide, { guideSteps } from './GenerationGuide'
import ContextMenu from './ContextMenu'
import type { MenuEntry } from './ContextMenu'
import type { GuideTarget } from './GenerationGuide'
import type { BinItem } from './FilmBin'
import { emptyBrowserSelection, selectBrowserItem } from './browserSelection'
import type { BrowserSelection } from './browserSelection'
import type { ReferenceImage } from './FilmReferences'
import type { StudioState } from './types'
import { timecode } from './editorTypes'
/** Sequence timecode origin: one hour, 24 fps. Display and typing only; nothing stored changes. */
const SEQ_START = 24 * 3600
import { COMMAND_BY_ID, chordFromEvent, chordIndex, loadStoredKeymap, shuttleRate } from './shortcuts'
import './editor.css'
import './fcpFilm.css'

interface VideoAsset { id: string; label: string; filename: string; status: string; version: number; frame_count: number; fps: number; width: number; height: number; duration_seconds: number; source: { path: string; sha256: string }; provenance: Record<string, unknown>; media_url: string }
type Shot = EditShot /* video shot or gap; see filmEdits.ts */
interface Sequence { timeline_duration_frames?:number;picture_duration_frames?:number;media_kind?:string;markers?:{id:string;label:string;frame:number}[];selection?:{in_frame:number;out_frame:number}|null; id: string; project_id: string; title: string; revision: number; fps: number; width: number; height: number; duration_frames: number; shots: Shot[]; audio_tracks: AudioPlacement[]; manifest_hash?: string; export: { status: string; error?: unknown; media_url?: string; manifest_url?: string; report?: { manifest_hash?: string } } }
interface Project { id: string; title: string; revision: number; sequences: { id: string; title: string }[] }
interface GeneratedTake { candidate_id: string; label: string; outputs: { output_index: number; frame_count: number }[] }
interface Catalog { projects: Project[]; assets: VideoAsset[] }
const fail = (e: unknown) => e instanceof Error ? e.message : String(e)
const duration = (shots: Shot[]) => shots.reduce((sum, shot) => sum + shot.duration_frames, 0)
const signature = (seq: Sequence | null) => seq ? JSON.stringify([seq.title, seq.width, seq.height, seq.shots, seq.audio_tracks,seq.timeline_duration_frames,seq.markers,seq.selection]) : ''
function lastSequence() { try { return localStorage.getItem('llr.film.sequence.v1') ?? '' } catch { return '' } }

export default function FilmEditor({ data, onSceneAnimation, onGenerate }: { data: StudioState; onSceneAnimation: () => void; onGenerate: () => void }) {
  const [catalog, setCatalog] = useState<Catalog>({ projects: [], assets: [] })
  const [projectId, setProjectId] = useState('')
  const [sequence, setSequence] = useState<Sequence | null>(null)
  const [saved, setSaved] = useState<Sequence | null>(null)
  const [sourceId, setSourceId] = useState('')
  const [audioSourceId, setAudioSourceId] = useState('')
  const [audioSourceRole,setAudioSourceRole]=useState<'production'|'music'|undefined>('music')
  const [generations,setGenerations]=useState<GenerationPlacement[]>([])
  const [generationError,setGenerationError]=useState('')
  const [selectedJob,setSelectedJob]=useState('')
  const [preparedContinuation,setPreparedContinuation]=useState<ContinuationDraft|null>(null)
  const [queueEpoch,setQueueEpoch]=useState(0)
  const [shotId, setShotId] = useState('')
  const [projectName, setProjectName] = useState('')
  const [sequenceName, setSequenceName] = useState('')
  const [markerLabel,setMarkerLabel]=useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('Create a project, then a named sequence. Drag clips from the Browser onto the timeline; scene animation remains a separate tool.')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const [panel, setPanel] = useState<'video' | 'audio' | 'generate' | 'music' | 'fmv' | 'plan' | 'still' | 'history'>('video')
  const [storyDirty,setStoryDirty]=useState(false)
  const [planDirty,setPlanDirty]=useState(false)
  const [planRequest,setPlanRequest]=useState<{token:number;sequence_id:string;in_frame:number;out_frame:number}|null>(null)
  const [preparedPlan,setPreparedPlan]=useState<PlannedSetup|null>(null)
  const [rehearsal,setRehearsal]=useState<StoryManifest|null>(null)
  const [activePane, setActivePane] = useState('canvas')
  const [zoom, setZoom] = useState(100)
  const [sourceFrame, setSourceFrame] = useState(0)
  const [sourceMarks, setSourceMarks] = useState<{in:number;out:number|null}>({in:0,out:null})
  const [shuttle, setShuttle] = useState(0)
  const pendingSeek = useRef<number|null>(null)
  /** Set while the Canvas playhead sits at or past the end of the picture, so the shot-sync effect doesn't pull it back into the last shot. */
  const parkedFrame = useRef<number|null>(null)
  const pendingSourceFrame = useRef<number|null>(null)
  const [keymap,setKeymap] = useState<Keymap>(()=>loadStoredKeymap(localStorage,'llr.editor.keymap.v1').keymap)
  const bindings = useMemo(()=>chordIndex(keymap),[keymap])
  const [layoutOpen,setLayoutOpen] = useState(false)
  function changeKeymap(next:Keymap){setKeymap(next);try{localStorage.setItem('llr.editor.keymap.v1',serializeKeymap(next))}catch{setError('Keyboard changes apply now, but this browser could not save them for next time.')}}
  const [recipe, setRecipe] = useState('')
  const [fromScene, setFromScene] = useState('')
  const [takes, setTakes] = useState<GeneratedTake[]>([])
  const [fromTake, setFromTake] = useState('')
  const [takeError, setTakeError] = useState('')
  async function refreshTakes() { try { const result = await api<{takes: GeneratedTake[]}>('film/takes'); setTakes(result.takes); setTakeError('') } catch(e) { setTakeError(fail(e)) } }
  useEffect(() => { void refreshTakes() }, [])
  const [playing, setPlaying] = useState(false)
  const [programFrame, setProgramFrame] = useState(0)
  const [history, setHistory] = useState<Sequence[]>([])
  const [future, setFuture] = useState<Sequence[]>([])
  const sourceVideo = useRef<HTMLVideoElement>(null)
  const programVideo = useRef<HTMLVideoElement>(null)
  const currentId = useRef('')
  // FCP7 never blocks switching sequences: unsaved edits wait in memory, per sequence, until saved or discarded.
  // A draft keeps the revision it started from, so a save after dot changed the sequence is refused, never merged.
  const drafts = useRef(new Map<string, { sequence: Sequence; saved: Sequence; history: Sequence[]; future: Sequence[] }>())
  const [draftIds, setDraftIds] = useState<string[]>([])
  function syncDrafts() { setDraftIds([...drafts.current.keys()]) }
  function stashCurrent() {
    if (!sequence || !saved) return
    if (signature(sequence) !== signature(saved)) drafts.current.set(sequence.id, { sequence, saved, history, future })
    else drafts.current.delete(sequence.id)
    syncDrafts()
  }
  /** Per-sequence UI state that must not follow you into another sequence. */
  function resetForSequence() { setViewerShot(''); setSelectedClip(null); setMarkFlags(null); setEditNote(''); setProgramFrame(0); parkedFrame.current = null; pendingPlayhead.current = null }
  const source = catalog.assets.find(asset => asset.id === sourceId)
  const project = catalog.projects.find(item => item.id === projectId)
  const dirty = signature(sequence) !== signature(saved)
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty
  // A current render is one continuous, muxed AV stream: no decoder restart at cuts.
  const renderedPreview = !dirty && sequence?.export?.status === 'complete' && !!sequence.export.media_url && !!sequence.shots.length
  const pictureTotal=duration(sequence?.shots??[])
  const total = sequence?.timeline_duration_frames??pictureTotal
  const blankClock=useRef<{time:number;frame:number}|null>(null)
  const itemAt=(frame:number)=>{let start=0;for(const s of sequence?.shots??[]){if(frame<start+s.duration_frames)return s;start+=s.duration_frames}return sequence?.shots.at(-1)}
  const frameItem=pictureTotal>0?itemAt(Math.min(programFrame,pictureTotal-1)):undefined
  const pictureAtFrame=pictureTotal>0&&(programFrame<pictureTotal||total===pictureTotal)&&!(frameItem&&isGap(frameItem))
  /** The V1 item under the playhead (shot or gap); `activeShot` is it only when it is a video shot. */
  const activeItem = sequence?.shots.find(shot => shot.id === shotId) ?? sequence?.shots[0]
  const activeShot: VideoShot | undefined = activeItem && !isGap(activeItem) ? activeItem : undefined
  const activeAsset = catalog.assets.find(asset => asset.id === activeShot?.asset_id)
  const activeIndex = sequence?.shots.findIndex(shot => shot.id === activeItem?.id) ?? -1
  const shotStart = duration(sequence?.shots.slice(0, Math.max(0, activeIndex)) ?? [])
  const exporting = sequence?.export?.status === 'queued' || sequence?.export?.status === 'exporting'
  // FCP7: double-clicking a sequence clip opens that clip (not its master) in the Viewer; its In/Out are the timeline shot's own.
  const [viewerShot, setViewerShot] = useState('')
  const keepViewerShot = useRef(false)
  const boundShot = (sequence?.shots.find(shot => shot.id === viewerShot && !isGap(shot) && shot.asset_id === sourceId) as VideoShot | undefined) ?? null
  const marks = boundShot ? { in: boundShot.source_in_frame, out: boundShot.source_in_frame + boundShot.duration_frames - 1 as number | null } : sourceMarks
  function markIn(frame: number) {
    if (boundShot) { const out = Math.max(frame, boundShot.source_in_frame + boundShot.duration_frames - 1); patchShot(boundShot.id, { source_in_frame: frame, duration_frames: out - frame + 1 }) }
    else setSourceMarks(m => ({ in: frame, out: m.out !== null && m.out < frame ? null : m.out }))
  }
  function markOut(frame: number) {
    if (boundShot) patchShot(boundShot.id, { duration_frames: Math.max(boundShot.source_in_frame, frame) - boundShot.source_in_frame + 1 })
    else setSourceMarks(m => ({ ...m, out: Math.max(m.in, frame) }))
  }
  function openShotInViewer(shot: Shot) {
    if (isGap(shot)) return
    stopTransport()
    setViewerShot(shot.id); setPanel('video'); setActivePane('viewer')
    if (sourceId === shot.asset_id) { if (sourceVideo.current) sourceVideo.current.currentTime = shot.source_in_frame / 24; setSourceFrame(shot.source_in_frame) }
    else { pendingSourceFrame.current = shot.source_in_frame; keepViewerShot.current = true; setSourceId(shot.asset_id) }
  }
  // FCP7 selection is separate from the playhead. `shotId` stays the playhead's shot (it drives the live player).
  const [selectedClip, setSelectedClip] = useState<{ kind: 'shot' | 'audio'; id: string } | null>(null)
  const selectedShot = selectedClip?.kind === 'shot' ? sequence?.shots.find(s => s.id === selectedClip.id) ?? null : null
  const selectedAudio = selectedClip?.kind === 'audio' ? sequence?.audio_tracks.find(t => t.id === selectedClip.id) ?? null : null
  useEffect(() => { if (selectedClip && !selectedShot && !selectedAudio) setSelectedClip(null) }, [selectedClip, selectedShot, selectedAudio])
  const inspShot = selectedShot ?? (selectedAudio ? undefined : activeShot)
  const inspIndex = sequence?.shots.findIndex(s => s.id === inspShot?.id) ?? -1
  const inspAsset = inspShot && !isGap(inspShot) ? catalog.assets.find(a => a.id === inspShot.asset_id) : undefined
  const pendingPlayhead = useRef<number | null>(null)
  /** Set when an edit has just placed the playhead, so the shot re-sync effect below does not pull it back to the trimmed shot's start. */
  const editPlacedPlayhead = useRef(false)
  useEffect(() => { if (pendingPlayhead.current !== null) { const f = pendingPlayhead.current; pendingPlayhead.current = null; editPlacedPlayhead.current = true; seekProgram(f, true) } })
  /** keep: 'edit' keeps the selected edit point (trims), 'clip' keeps the selected clip (slip); otherwise selection clears. */
  function applyEdit(result: EditResult, extra: Partial<Sequence> = {}, keep: 'edit' | 'clip' | null = null, merge = false) {
    if (!sequence || busy || exporting || rehearsal) return
    if (!result.ok) { setError(result.error); return }
    const picture = duration(result.shots)
    // Fit duration, markers and In/Out to the new picture so the save validator accepts it (see fitToPicture).
    const fit = fitToPicture({ picture, explicit: sequence.timeline_duration_frames ?? undefined, audioEnd: Math.max(0, ...(extra.audio_tracks ?? sequence.audio_tracks).map(t => t.start_frame + t.duration_frames)) /* the audio after this edit */, markers: sequence.markers ?? [], selection: sequence.selection ?? null })
    stopTransport(); setError('')
    update({ shots: result.shots, ...(fit.duration !== undefined ? { timeline_duration_frames: fit.duration } : {}), markers: fit.markers, selection: fit.selection, ...extra }, merge)
    if (keep !== 'clip') setSelectedClip(null)
    if (keep !== 'edit') setSelectedEdit(null)
    pendingPlayhead.current = result.playhead
    setEditNote(`${result.message}${fit.note ? ' ' + fit.note : ''}`)
  }
  /** Step 5 slice B: FCP7 tools and the selected edit point (by item ids, so undo/redo keep it valid). */
  const [tool, setTool] = useState<'select' | 'razor' | 'roll' | 'ripple' | 'slip'>('select')
  const [selectedEdit, setSelectedEdit] = useState<EditPoint | null>(null)
  const selectedEditFrame = selectedEdit && sequence ? editPointFrame(sequence.shots, selectedEdit) : null
  useEffect(() => { if (selectedEdit && selectedEditFrame === null) setSelectedEdit(null) }, [selectedEdit, selectedEditFrame])
  useEffect(() => { setSelectedEdit(null) }, [sequence?.id])
  const frameCounts = (id: string) => catalog.assets.find(a => a.id === id)?.frame_count
  /** Step 5 B2: mouse trims. While dragging, V1 draws a local preview; the edit is applied once on release (one undo step). */
  const [dragPreview, setDragPreview] = useState<{ shots: Shot[]; note: string } | null>(null)
  const shownShots: Shot[] = dragPreview?.shots ?? sequence?.shots ?? []
  const dragMoved = useRef(false)
  function startDrag(e: React.PointerEvent<HTMLElement>, kind: 'edge' | 'slip' | 'move', point: EditPoint | null, shotId = '') {
    if (!sequence || busy || exporting || rehearsal || e.button !== 0) return
    const track = e.currentTarget.closest('.fcp-track-clips')
    if (!track) return
    if (kind !== 'move') e.preventDefault()
    e.stopPropagation()
    const shots = sequence.shots, element = e.currentTarget, pointerId = e.pointerId
    const perFrame = Math.max(0.0001, track.getBoundingClientRect().width / timelineSpan), x0 = e.clientX
    const run = (d: number) => kind === 'slip' ? slipEdit(shots, shotId, d, frameCounts) : trimEdit(shots, point!, d, frameCounts)
    // Drag move (4.2) with snapping (4.5): targets are cuts of the other items, the playhead, markers and In/Out.
    const from = itemStart(shots, shotId) ?? 0, length = shots.find(s => s.id === shotId)?.duration_frames ?? 0
    const targets: number[] = [programFrame, ...(sequence.markers ?? []).map(m => m.frame), ...(sequence.selection ? [sequence.selection.in_frame, sequence.selection.out_frame] : [])]
    { let at = 0; targets.push(0); for (const s of shots) { const end = at + s.duration_frames; if (s.id !== shotId) { targets.push(at, end) } at = end } }
    const tolerance = Math.max(1, Math.round(8 / perFrame))
    let best = 0, moveTo: { to: number; mode: 'overwrite' | 'insert' } | null = null
    dragMoved.current = false; setActivePane('timeline')
    if (kind !== 'move') stopTransport()
    if (kind === 'edge' && point) { setSelectedEdit(point); setSelectedClip(null) } else { setSelectedClip({ kind: 'shot', id: shotId }); setSelectedEdit(null) }
    try { element.setPointerCapture(pointerId) } catch { /* capture is optional */ }
    const move = (ev: PointerEvent) => {
      if (kind === 'move') {
        if (!dragMoved.current && Math.abs(ev.clientX - x0) < 4) return // a click, not a drag
        if (!dragMoved.current) stopTransport()
        dragMoved.current = true
        const candidate = from + Math.round((ev.clientX - x0) / perFrame)
        const mode = ev.altKey ? 'insert' : 'overwrite'
        let to = Math.max(0, candidate), how = ''
        if (mode === 'insert') { to = nearestCut(shots, candidate); how = ' · rearrange at a cut' }
        else if (snapping) {
          const a = snapFrame(candidate, targets, tolerance), b = snapFrame(candidate + length, targets, tolerance)
          if (a.snapped && (!b.snapped || Math.abs(a.frame - candidate) <= Math.abs(b.frame - candidate - length))) { to = a.frame; how = ' · snapped start' }
          else if (b.snapped) { to = b.frame - length; how = ' · snapped end' }
          to = Math.max(0, to)
        }
        const r = moveClip(shots, shotId, to, mode)
        moveTo = r.ok ? { to, mode } : null
        setDragPreview({ shots: r.ok ? r.shots : shots, note: r.ok ? `Move to ${seqTc(to)}${how}${mode === 'overwrite' ? ' · Alt: rearrange' : ''}` : (to === from ? 'No move' : r.error) })
        return
      }
      const raw = Math.round((ev.clientX - x0) / perFrame) * (kind === 'slip' ? -1 : 1)
      if (raw !== 0) dragMoved.current = true
      // Clamp at the limit: the largest delta toward the pointer that is still valid.
      let d = raw, r = run(d)
      while (d !== 0 && !r.ok) { d -= Math.sign(d); r = run(d) }
      best = d
      setDragPreview(d && r.ok ? { shots: r.shots, note: `${d > 0 ? '+' : ''}${d} frame${Math.abs(d) === 1 ? '' : 's'}${d !== raw ? ' (limit)' : ''}` } : { shots, note: raw ? 'At the limit' : '0 frames' })
    }
    const up = () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up)
      try { element.releasePointerCapture(pointerId) } catch { /* already released */ }
      setDragPreview(null)
      window.setTimeout(() => { dragMoved.current = false }, 0) // only the click fired by this release is swallowed
      if (kind === 'move') { if (moveTo) applyEdit(moveClip(shots, shotId, moveTo.to, moveTo.mode), {}, 'clip'); return }
      if (best) applyEdit(run(best), {}, kind === 'slip' ? 'clip' : 'edit')
    }
    // Listen on window: the release must end the drag even if capture is lost or the handle re-renders.
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up)
  }
  /** FCP7 Snapping (N), on by default. */
  const [snapping, setSnapping] = useState(true)
  /** Clip click: Razor cuts at the clicked frame; any other tool selects the clip (and clears an edit point). */
  function clickShot(e: React.MouseEvent<HTMLElement>, shot: Shot) {
    e.stopPropagation(); setActivePane('timeline')
    if (dragMoved.current) { dragMoved.current = false; return } // the click that ends a slip drag
    if (tool === 'razor' && sequence) {
      const rect = e.currentTarget.getBoundingClientRect()
      let start = 0; for (const s of sequence.shots) { if (s.id === shot.id) break; start += s.duration_frames }
      const at = start + Math.round(Math.max(0, Math.min(1, (e.clientX - rect.left) / Math.max(1, rect.width))) * shot.duration_frames)
      applyEdit(addEdit(sequence.shots, at)); return
    }
    setSelectedClip({ kind: 'shot', id: shot.id }); setSelectedEdit(null)
  }
  const [editNote, setEditNote] = useState('')
  const [markFlags, setMarkFlags] = useState<{ in: boolean; out: boolean } | null>(null)
  useEffect(() => { setMarkFlags(null) }, [sequence?.id])
  useEffect(() => { if (!sequence?.selection) setMarkFlags(null) }, [sequence?.selection])
  useEffect(() => { if (!dirty) setEditNote('') }, [dirty])
  // Three-point edits from the Viewer take into V1. Sequence In wins over the playhead; sequence In/Out clear afterwards, as in FCP7.
  function threePoint(kind: 'insert' | 'overwrite' | 'replace') {
    if (!sequence) return
    if (!source) { setError('Open a take in the Viewer first: double-click it in the Browser.'); return }
    if (boundShot) { setError('The Viewer is showing a shot from this sequence. Double-click the take in the Browser to open it as a source before editing it in.'); return }
    if (kind === 'replace') { applyEdit(replaceEdit(sequence.shots, programFrame, source, sourceFrame)); return }
    const sel = sequence.selection ?? null
    // The saved selection always holds both ends, so which marks were really set comes from markFlags (keys this session).
    // Without flags (range loaded from disk or set with the buttons): an Out at the very end counts as unset.
    const hasIn = !!sel && (markFlags ? markFlags.in : true)
    const hasOut = !!sel && (markFlags ? markFlags.out : sel.out_frame < total)
    const range = editRange(source, marks.in, marks.out, hasIn && hasOut ? sel!.in_frame : null, hasIn && hasOut ? sel!.out_frame : null)
    if ('error' in range) { setError(range.error ?? 'Edit not possible.'); return }
    // FCP7 backtiming: with only a sequence Out, the edit ends at Out.
    const at = hasIn ? sel!.in_frame : hasOut ? sel!.out_frame - range.length : programFrame
    if (at < 0) { setError(`Backtiming from the sequence Out needs ${range.length} frames before it, but Out is at frame ${sel!.out_frame}. Mark a shorter source range or a later Out.`); return }
    setMarkFlags(null)
    const result = (kind === 'insert' ? insertEdit : overwriteEdit)(sequence.shots, at, source.id, range.sourceIn, range.length)
    const audioNote = kind === 'insert' && result.ok && sequence.audio_tracks.length ? ' Audio stayed where it was, so sound placed under later shots is now out of sync with them.' : ''
    applyEdit(result.ok ? { ...result, message: result.message + audioNote } : result, { selection: null })
  }
  // Keyboard parity with the Scene editor: K-held stepping, bounded playback (In to Out / around), typed timecode.
  const kHeld = useRef(false), kCode = useRef('')
  const stopAt = useRef<{ frame: number; back: number | null } | null>(null)
  const sourceStop = useRef<{ frame: number; back: number | null } | null>(null)
  const playRef = useRef<() => void>(() => {})
  playRef.current = () => { void playProgram() }
  const [tcEntry, setTcEntry] = useState<{ target: 'source' | 'program'; text: string } | null>(null)
  function playSegment(start: number, end: number, back: number | null) {
    if (!total || end <= start) return
    const wasPlaying = playing
    setShuttle(0); seekProgram(start); stopAt.current = { frame: end, back }
    if (!wasPlaying) window.setTimeout(() => playRef.current(), 0)
  }
  function playSourceSegment(start: number, end: number, back: number | null) {
    const video = sourceVideo.current
    if (!video || end <= start) return
    stopTransport(); video.currentTime = start / 24; setSourceFrame(start); sourceStop.current = { frame: end, back }
    void video.play().catch(e => setError(fail(e)))
  }
  useEffect(() => { const s = stopAt.current; if (s && playing && programFrame >= s.frame) { stopTransport(); seekProgram(s.back ?? s.frame) /* playback overshoots by a frame or two before this runs; land exactly on Out */ } }, [programFrame, playing])
  useEffect(() => { if (!playing) stopAt.current = null }, [playing])
  useEffect(() => { const s = sourceStop.current, video = sourceVideo.current; if (s && video && sourceFrame >= s.frame) { sourceStop.current = null; video.pause(); const land = s.back ?? s.frame /* land exactly on Out, not a frame or two past it */; video.currentTime = land / 24; setSourceFrame(land) } }, [sourceFrame])
  useEffect(() => {
    const up = (event: KeyboardEvent) => { if (event.code === kCode.current) kHeld.current = false }
    const release = () => { kHeld.current = false }
    window.addEventListener('keyup', up); window.addEventListener('blur', release)
    return () => { window.removeEventListener('keyup', up); window.removeEventListener('blur', release) }
  }, [])
  useEffect(() => { document.querySelector('.film-assets > .selected')?.scrollIntoView({ block: 'nearest' }) }, [sourceId])

  const previewAudio = useProgramAudio(sequence?.audio_tracks ?? [], () => {
    if(playing&&!pictureAtFrame&&blankClock.current)return Math.min(total,blankClock.current.frame+(performance.now()-blankClock.current.time)*24/1000)
    const video = programVideo.current
    if (!playing || !video || video.paused || video.seeking || video.readyState < 3 || video.playbackRate !== 1 || !activeShot) return null
    return shotStart + Math.min(activeShot.duration_frames, Math.max(0, video.currentTime * 24 - activeShot.source_in_frame))
  }, message => { setError(message); setPlaying(false); programVideo.current?.pause() })
  useEffect(() => { if (!playing) { previewAudio.stop(); programVideo.current?.pause() } }, [playing])
  useEffect(() => { setPlaying(false); previewAudio.stop(); programVideo.current?.pause() }, [sequence?.id, signature(sequence)])
  useEffect(() => {
    const hide = () => { if(document.hidden) { setPlaying(false); previewAudio.stop(); programVideo.current?.pause() } }
    document.addEventListener('visibilitychange', hide)
    return () => document.removeEventListener('visibilitychange', hide)
  }, [])
  // Live playback through a gap: when the blank clock reaches picture again, hand over to that shot's video.
  useEffect(()=>{if(renderedPreview||!activeItem||!isGap(activeItem)||!frameItem||frameItem.id===activeItem.id||isGap(frameItem))return;let start=0;for(const s of sequence?.shots??[]){if(s.id===frameItem.id)break;start+=s.duration_frames}pendingSeek.current=(frameItem.source_in_frame+Math.max(0,programFrame-start))/24+0.001;setShotId(frameItem.id)},[programFrame,activeItem?.id,frameItem?.id,renderedPreview])// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{if(!playing||pictureAtFrame||renderedPreview){blankClock.current=null;return}blankClock.current={time:performance.now(),frame:programFrame};const timer=window.setInterval(()=>{const c=blankClock.current;if(!c)return;const next=Math.min(total-1,Math.floor(c.frame+(performance.now()-c.time)*24/1000));setProgramFrame(next);if(c.frame+(performance.now()-c.time)*24/1000>=total){setPlaying(false);previewAudio.stop()}},25);return()=>{clearInterval(timer);blankClock.current=null}},[playing,pictureAtFrame,total])
  function pauseForAudition(event: React.SyntheticEvent) {
    const storyVideo=document.querySelector<HTMLVideoElement>('.fcp-rehearsal video')
    if(storyVideo&&event.target!==storyVideo)storyVideo.pause()
    if(storyVideo&&event.target===storyVideo){sourceVideo.current?.pause();document.querySelectorAll<HTMLAudioElement>('.ed-audio-workspace audio').forEach(a=>a.pause())}
    if (event.target !== programVideo.current) { setPlaying(false); previewAudio.stop(); programVideo.current?.pause() }
  }

  useEffect(()=>{
    let live=true;let timer:number|undefined;const id=sequence?.id;setGenerations([]);setGenerationError('');if(!id)return
    const refresh=()=>api<{placements:GenerationPlacement[]}>(`film/sequences/${id}/generations`).then(result=>{if(live){setGenerations(result.placements);setGenerationError('');if(result.placements.some(p=>['pending','submitting','queued','running','importing','polling'].includes(p.stage)))timer=window.setTimeout(()=>{void refresh()},2500)}}).catch(e=>{if(live)setGenerationError(fail(e))})
    void refresh();return()=>{live=false;if(timer)clearTimeout(timer)}
  },[sequence?.id,queueEpoch,panel])
  async function afterGeneratedPlacement(){if(sequence){await open(sequence.id);const result=await api<{placements:GenerationPlacement[]}>(`film/sequences/${sequence.id}/generations`);setGenerations(result.placements)}}
  function inspectGeneration(p:GenerationPlacement){setSelectedJob(p.job_id);setPanel('history');setActivePane('viewer')}
  /** Generate tab (picture + sound or music) and where requested takes should go. Spots live in this browser, keyed by job id;
   *  they are markers, not server reservations, so they can always be removed. */
  useEffect(()=>{clearThumbQueue()},[sequence?.id]) // drop thumbnail captures for the previous sequence
  const [genMode,setGenMode]=useState<'take'|'music'>('take')
  /** Generate tab view: 'new' = the generation forms (default, so "place after selected clip" keeps working), 'take' = the selected take's receipt / reroll (only when pressed). */
  const [genView,setGenView]=useState<'new'|'take'>('new')
  // Selected take follows whatever was picked last: a timeline clip, or a take opened in the Viewer.
  const [genFocus,setGenFocus]=useState<'clip'|'source'>('clip')
  useEffect(()=>{if(selectedClip)setGenFocus('clip')},[selectedClip])
  useEffect(()=>{if(sourceId)setGenFocus('source')},[sourceId])
  function openGenerate(mode:'take'|'music'='take'){setGenMode(mode);setGenView('new');setPanel('generate');setActivePane('viewer')}
  const [takeSpots,setTakeSpots]=useState<Record<string,TakeSpot>>(()=>{try{const v=JSON.parse(localStorage.getItem('llr.film.takeSpots.v1')??'{}');return v&&typeof v==='object'&&!Array.isArray(v)?v:{}}catch{return {}}})
  // Flags are the only record of where a requested take should go, so a failed save must be visible.
  useEffect(()=>{try{localStorage.setItem('llr.film.takeSpots.v1',JSON.stringify(takeSpots))}catch(e){setError(`Could not save where requested takes should go (browser storage refused it: ${fail(e)}). The flags are kept for this session only.`)}},[takeSpots])
  const [spotCard,setSpotCard]=useState<{jobId:string;x:number;y:number}|null>(null)
  const [placePolicy,setPlacePolicy]=useState<'preserve'|'ripple'>('ripple')
  function removeSpot(jobId:string){setTakeSpots(s=>{const n={...s};delete n[jobId];return n})}
  /** What a library take needs before it can be placed, and whether it can be placed now. */
  function takeState(job:GenerationJob){
    const video=job.video_asset_id?catalog.assets.find(a=>a.id===job.video_asset_id):undefined
    const audio=job.audio_asset_id?audioLibrary.find(a=>a.id===job.audio_asset_id):undefined
    // No approve/reject since 2026-11-19: an imported take can be placed once its picture (and its sound, if it has one) is loaded here.
    const approved=!!video&&(!job.audio_asset_id||!!audio)
    return {video,audio,approved,spot:takeSpots[job.id]}
  }
  /** Menu bar items that are not keyboard commands. */
  function menuAction(a:MenuAction){
    const openDetails=(summary:string,focus?:string)=>{const d=[...document.querySelectorAll<HTMLDetailsElement>('.film-editor details')].find(x=>x.querySelector(':scope > summary')?.textContent?.startsWith(summary));if(!d)return;d.open=true;d.scrollIntoView({block:'nearest'});if(focus)d.querySelector<HTMLElement>(focus)?.focus()}
    if(a==='newSequence'){setActivePane('browser');openDetails('New sequence','input')}
    else if(a==='import'){setActivePane('browser');openDetails('Import / generated sources')}
    else if(a==='cleanup')openCleanup()
    else if(a==='generate')openGenerate('take')
    else if(a==='history'){setPanel('history');setActivePane('viewer')}
    else if(a==='guide')setGuide({jobId:null})
    else if(a==='keyboard')setLayoutOpen(true)
  }
  /** Audition in context: play the take at its spot (or the playhead) between its neighbours, without placing it. */
  const [audition,setAudition]=useState<{title:string;note:string;win:Extract<AuditionWindow,{ok:true}>}|null>(null)
  function auditionTake(job:GenerationJob,spotOverride?:TakeSpot){
    if(!sequence)return
    const {video,audio,spot:saved}=takeState(job)
    if(!video){setError('Import the take first.');return}
    const spot=spotOverride??(saved&&saved.sequence_id===sequence.id?saved:{sequence_id:sequence.id,kind:'playhead' as const,frame:programFrame})
    const where=resolveSpot(sequence.shots,spot,programFrame)
    if('error' in where){setError(where.error);return}
    const win=auditionWindow(sequence.shots,sequence.audio_tracks,where.frame,{videoAssetId:video.id,frames:video.frame_count,audioAssetId:audio?.id,audioFrames:audio?Math.floor(audio.duration_seconds*24):undefined},placePolicy)
    if(!win.ok){setError(win.error);return}
    stopTransport();previewAudio.stop()
    setAudition({title:job.label,note:`Placed ${where.note}; existing audio ${placePolicy==='ripple'?'moves with the picture':'keeps its timing'}.`,win})
  }
  /** Place an imported take with Insert: its picture on V1 and its production sound on A1 at the same start. One unsaved edit. */
  function placeTakeNow(job:GenerationJob,spotOverride?:TakeSpot){
    if(!sequence)return
    const {video,audio,approved,spot:saved}=takeState(job)
    if(!video||!approved){setError(video?'Its production sound is not loaded yet; try again in a moment (or check the Queue tab).':'This take is not in the Browser yet. Wait for it to import (see the Queue tab).');void refreshCatalog().catch(()=>{});return}
    if(sequence.shots.some(s=>!isGap(s)&&s.asset_id===video.id)&&!window.confirm(`“${job.label}” is already in this sequence. Place another copy?`))return
    const spot=spotOverride??saved??{sequence_id:sequence.id,kind:'playhead' as const,frame:programFrame}
    if(spot.sequence_id!==sequence.id){setError('This take was meant for another sequence. Open that sequence, or choose a new spot here.');return}
    const where=resolveSpot(sequence.shots,spot,programFrame)
    if('error' in where){setError(where.error);return}
    const r=placeTake(sequence.shots,sequence.audio_tracks,where.frame,{videoAssetId:video.id,frames:video.frame_count,audioAssetId:audio?.id,audioFrames:audio?Math.floor(audio.duration_seconds*24):undefined},placePolicy)
    if(!r.ok){setError(r.error);return}
    const explicit=sequence.timeline_duration_frames
    applyEdit(r,{audio_tracks:r.tracks,...(placePolicy==='ripple'&&explicit!==undefined&&explicit!==null?{timeline_duration_frames:explicit+video.frame_count}:{})})
    setStatus(`Placed “${job.label}” ${where.note}. Unsaved: Save (Ctrl+S) to keep it; Ctrl+Z undoes it.`)
  }
  /** Generation guide (optional walkthrough) and the card shown when a striped request block is clicked. */
  const [guide,setGuide]=useState<{jobId:string|null}|null>(null)
  const [blockCard,setBlockCard]=useState<{p:GenerationPlacement;x:number;y:number}|null>(null)
  const [hiddenJobs,setHiddenJobs]=useState<string[]>(()=>{try{const v=JSON.parse(localStorage.getItem('llr.film.hiddenGenerations.v1')??'[]');return Array.isArray(v)?v.filter(x=>typeof x==='string'):[]}catch{return []}})
  const [showHidden,setShowHidden]=useState(false)
  useEffect(()=>{try{localStorage.setItem('llr.film.hiddenGenerations.v1',JSON.stringify(hiddenJobs))}catch{/* optional preference */}},[hiddenJobs])
  /** Guide state for a take without a server reservation (Generate tab takes): built from the job and its review state. */
  function takeAsPlacement(job:GenerationJob):GenerationPlacement{
    // A flag means it is still waiting to go in there (the flag goes away once it is saved in that sequence).
    const st=takeState(job),placed=!st.spot&&!!job.video_asset_id&&(usedCount.get(job.video_asset_id)??0)>0
    const stage=job.status!=='success'?job.status:!job.video_asset_id?'awaiting_import':placed?'placed':'ready_to_place'
    return {job_id:job.id,job,stage,video_asset_id:job.video_asset_id,audio_asset_id:job.audio_asset_id,placed_revision:placed?(saved?.revision??0):null,destination:{sequence_id:st.spot?.sequence_id??sequence?.id??'',expected_revision:0,track:'V1'}}
  }
  /** Continue a saved shot: the server prepares its rendered last frame as the next take's first frame. Needs a saved, exported cut. */
  function prepareContinuation(shotId:string){
    if(!sequence)return
    void action(async()=>{const result=await api<ContinuationDraft>('film/continuations',{sequence_id:sequence.id,shot_id:shotId,expected_revision:saved?.revision});setPreparedContinuation(result);openGenerate('take');setStatus('Continuation prepared from the rendered last used frame. Edit the next action, check the worker, then explicitly Generate.')})
  }
  /** Why a continuation of this shot cannot be prepared right now (null = it can). */
  function continuationBlock(sequenceId:string,shotId?:string):string|null{
    if(!sequence||sequence.id!==sequenceId)return 'Open the sequence it came from first.'
    if(!shotId||!sequence.shots.some(s=>s.id===shotId))return 'The shot it continues is no longer in this sequence.'
    if(dirty)return 'Save the sequence first (it has unsaved edits).'
    if(sequence.export?.status!=='complete')return 'Export the sequence first (Export film): a continuation starts from the rendered frame.'
    return null
  }
  /** The guide reads the Generate form through this snapshot and drives it through genControl (the form stays the only copy). */
  const genControl=useRef<GenControl|null>(null)
  const [genSnap,setGenSnap]=useState<GenSnapshot|null>(null)
  /** Open the right place and briefly highlight the control the user should press themselves. */
  function guideShow(target:GuideTarget,p:GenerationPlacement|null){
    setBlockCard(null)
    const video=p?.video_asset_id??p?.job.video_asset_id,audio=p?.audio_asset_id??p?.job.audio_asset_id
    void video;void audio
    {const gen=['brief','destination','generate'].includes(target);if(gen)openGenerate('take');else{setPanel('history');setActivePane('viewer')}if(p)setSelectedJob(p.job_id)}
    let tries=0
    const look=()=>{
      const card=p?document.getElementById(`generation-job-${p.job_id}`):null
      const byText=(root:ParentNode|null,start:string)=>root?[...root.querySelectorAll('button')].find(b=>b.textContent?.startsWith(start))??null:null
      const el:Element|null=target==='brief'?document.querySelector('.film-generation textarea'):target==='destination'?document.querySelector('.generation-where'):target==='generate'?byText(document.querySelector('.film-generation'),'Generate video'):target==='import'&&!card?null:target==='import'?byText(card,'Import video')??card:target==='place'?byText(card,'Place at its spot')??byText(card,'Place at playhead')??byText(card,'Place clip')??card:card
      // Some panels (the Audio tab) load their controls a moment later: keep looking for ~3 s.
      if(!el){if(++tries<12){window.setTimeout(look,250);return}setStatus('The guide could not find that control here. Open the Queue tab and look for the take’s card.');return}
      const fold=el.closest('details');if(fold&&!fold.open)fold.open=true
      el.scrollIntoView({block:'center',behavior:'smooth'});el.classList.add('guide-flash');window.setTimeout(()=>el.classList.remove('guide-flash'),2600)
    }
    window.setTimeout(look,300)
  }
  function reviewGeneratedVideo(id:string){void refreshCatalog().then(()=>{setSourceId(id);setPanel('video');setActivePane('viewer')}).catch(e=>setError(fail(e)))}
  function reviewGeneratedAudio(id:string,role:'production'|'music'){setAudioSourceId(id);setAudioSourceRole(role);setPanel('audio');setActivePane('viewer')}
  function openBinItem(item:BinItem){
    if(item.kind==='video'){stopTransport();setSourceId(item.id);setViewerShot('');setPanel('video')}
    else if(item.kind==='audio'){setAudioSourceId(item.id);setAudioSourceRole(undefined)/* Browser does not know the role; the Audio tab defaults to production */;setPanel('audio')}
    else{setStillId(item.id);setPanel('still')}
    setActivePane('viewer')
  }
  async function refreshCatalog() { const result = await api<Catalog>('film'); setCatalog(result); return result }
  async function discard() {
    setSequence(saved); setHistory([]); setFuture([]); resetForSequence(); setStatus(`Discarded unsaved edits; back to revision ${saved?.revision}.`)
    // A parked draft may have started from an older revision; show what the library holds now.
    const id = currentId.current; if (!id || !saved) return
    try { const latest = await api<Sequence>(`film/sequences/${id}`); if (currentId.current === id && latest.revision !== saved.revision) { setSequence(latest); setSaved(latest); setError(''); setStatus(`Discarded unsaved edits; loaded the library's revision ${latest.revision}.`) } } catch (e) { setError(fail(e)) }
  }
  async function open(id: string) {
    if (lock.current) return
    // Opening another sequence parks this one's unsaved edits; reopening the current one takes the server's version.
    const switching = id !== currentId.current
    // Clicking the open sequence's own tab or row (or the second click of a double-click) must not reload over unsaved edits.
    if (!switching && dirtyRef.current) { setActivePane('timeline'); return }
    if (switching) stashCurrent()
    lock.current = true; setBusy(true); setError(''); setPlaying(false); previewAudio.stop()
    try {
      const result = await api<Sequence>(`film/sequences/${id}`)
      const draft = switching ? drafts.current.get(id) : undefined
      drafts.current.delete(id); syncDrafts()
      const shown = draft ? draft.sequence : result
      currentId.current = id; resetForSequence(); setSequence(shown); setSaved(draft ? (draft.saved.revision === result.revision ? { ...draft.saved, export: result.export } /* a render may have finished meanwhile */ : draft.saved) : result); setProjectId(result.project_id); setShotId(shown.shots[0]?.id ?? ''); setSourceId((shown.shots.find(s => !isGap(s)) as VideoShot | undefined)?.asset_id ?? ''); setProgramFrame(0); setHistory(draft?.history ?? []); setFuture(draft?.future ?? [])
      if (draft && draft.saved.revision !== result.revision) setError(`Your unsaved edits to “${draft.sequence.title}” started from revision ${draft.saved.revision}, but the library now has revision ${result.revision}. Save will be refused rather than overwrite it. Discard, then open the sequence again to load the newer revision.`)
      setStatus(draft ? `Restored your unsaved edits to “${draft.sequence.title}”.` : 'Opened named sequence. Drag a clip from the Browser onto the timeline, or open it in the Viewer and Insert (F9).')
      try { localStorage.setItem('llr.film.sequence.v1', id) } catch { /* optional preference */ } }
    catch(e) { if (switching) { drafts.current.delete(currentId.current); syncDrafts() } /* still showing it; not parked */ setError(fail(e)) } finally { lock.current = false; setBusy(false) }
  }
  useEffect(() => {
    let live = true
    api<Catalog>('film').then(result => {
      if (!live) return
      setCatalog(result)
      const previous = result.projects.find(p => p.sequences.some(s => s.id === lastSequence()))
      const first = previous ?? result.projects[0]
      if (first) { setProjectId(first.id); const target = first.sequences.find(s => s.id === lastSequence()) ?? first.sequences[0]; if (target) void open(target.id) }
    }).catch(e => { if(live) setError(fail(e)) })
    return () => { live = false }
  }, [])
  useEffect(() => { setSourceMarks({in:0,out:null});setSourceFrame(0);if(keepViewerShot.current)keepViewerShot.current=false;else setViewerShot('') }, [sourceId])
  useEffect(() => {
    if (!exporting || !sequence) return
    const id = sequence.id
    const timer = window.setInterval(() => { void api<Sequence>(`film/sequences/${id}`).then(result => { if(currentId.current === id) { setSequence(current => current ? { ...current, export: result.export } : current); setSaved(current => current ? { ...current, export: result.export } : current) } }).catch(e => setError(fail(e))) }, 1500)
    return () => clearInterval(timer)
  }, [sequence?.id, exporting])
  useEffect(() => {
    const video = programVideo.current
    if (editPlacedPlayhead.current) { editPlacedPlayhead.current = false; return }
    if (!video || !activeShot || renderedPreview) return
    video.currentTime = pendingSeek.current ?? activeShot.source_in_frame / 24
    if (parkedFrame.current !== null) { if (!playing) video.pause(); return }
    setProgramFrame(shotStart+Math.max(0,Math.round(video.currentTime*24)-activeShot.source_in_frame))
    // Changing a source trim or shot order is an editing operation, not playback.
    if (!playing) video.pause()
  }, [activeShot?.id, activeShot?.source_in_frame, activeShot?.duration_frames, shotStart])
  useEffect(() => { editPlacedPlayhead.current = false }) // the flag only covers the commit in which the edit placed the playhead
  useEffect(() => { sourceVideo.current?.pause(); setShuttle(0) }, [panel])
  useEffect(() => {
    if (!dirty && !draftIds.length) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, draftIds.length])
  /** merge: continue the last undo step (a held trim key is one undo step, not thirty). */
  function update(patch: Partial<Sequence>, merge = false) {
    if (!sequence || busy || exporting || rehearsal) return
    if (!merge || !history.length) setHistory(items => [...items.slice(-29), sequence])
    setFuture([]); setPlaying(false)
    setSequence({ ...sequence, ...patch })
  }
  async function action(work: () => Promise<void>) {
    if(lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await work() } catch(e) { setError(fail(e)) } finally { lock.current = false; setBusy(false) }
  }
  /** The save request for one sequence; `base` is the revision its edits started from. */
  function savePayload(s: Sequence, base: Sequence | null) {
    return { expected_revision: base?.revision, title: s.title, width: s.width, height: s.height, shots: s.shots, audio_tracks: s.audio_tracks ?? [],...(s.timeline_duration_frames?{timeline_duration_frames:s.timeline_duration_frames}:{}),markers:s.markers??[],selection:s.selection??null }
  }
  async function save() {
    if (!sequence) return
    await action(async () => { const result = await api<Sequence>(`film/sequences/${sequence.id}`, savePayload(sequence, saved)); setSequence(result); setSaved(result); await refreshCatalog(); setStatus(`Saved “${result.title}” revision ${result.revision}. Sources preserved.`) })
  }
  /** FCP7 Save All: the open sequence and every parked draft, one at a time. A refused save keeps its draft and is reported by name. */
  async function saveAll() {
    if (!sequence && !drafts.current.size) return
    await action(async () => {
      const done: string[] = [], failed: string[] = []
      if (sequence && dirty) { try { const result = await api<Sequence>(`film/sequences/${sequence.id}`, savePayload(sequence, saved)); setSequence(result); setSaved(result); done.push(result.title) } catch (e) { failed.push(`“${sequence.title}”: ${fail(e)}`) } }
      for (const [id, draft] of [...drafts.current]) {
        try { const result = await api<Sequence>(`film/sequences/${id}`, savePayload(draft.sequence, draft.saved)); drafts.current.delete(id); done.push(result.title) } catch (e) { failed.push(`“${draft.sequence.title}”: ${fail(e)}`) }
      }
      syncDrafts(); await refreshCatalog()
      setStatus(done.length ? `Saved ${done.length} sequence${done.length === 1 ? '' : 's'}: ${done.map(t => `“${t}”`).join(', ')}.` : 'Nothing was saved.')
      if (failed.length) throw new Error(`Not saved: ${failed.join(' ')}`)
    })
  }
  /** FCP7 Render (Alt+R): the same server export, which is both the smooth Canvas playback file and the deliverable. Saves unsaved edits first (Boden, 2026-11-14); a stale draft is refused by the server. */
  function render() {
    if (!sequence || !total) return
    if (exporting) return
    // Boden 2026-11-14 (decision 3): Render saves first. A draft based on an older revision is refused by the server, so nothing is overwritten.
    const saving = dirty
    void action(async()=>{let base=saved;if(saving){base=await api<Sequence>(`film/sequences/${sequence.id}`,savePayload(sequence,saved));setSequence(base);setSaved(base);await refreshCatalog()}const result=await api<Sequence>(`film/sequences/${sequence.id}/export`,{expected_revision:base?.revision});setSequence(result);setSaved(result);setStatus(saving?`Saved revision ${base?.revision} and queued the export.`:'Export queued. This renders the full shot order and audio mix.')})
  }
  function move(index: number, delta: number) {
    if (!sequence || index + delta < 0 || index + delta >= sequence.shots.length) return
    const shots = [...sequence.shots]; [shots[index], shots[index + delta]] = [shots[index + delta], shots[index]]
    update({shots})
  }
  function patchShot(id: string, patch: Partial<Omit<VideoShot, 'id' | 'kind'>>) { if(sequence) update({ shots: sequence.shots.map(shot => shot.id !== id ? shot : isGap(shot) ? (patch.duration_frames !== undefined ? { ...shot, duration_frames: patch.duration_frames } : shot) : { ...shot, ...patch }) }) }
  function addShot() {
    if(!source || !sequence) return
    const shot = { id: crypto.randomUUID(), asset_id: source.id, source_in_frame: marks.in, duration_frames: (marks.out??source.frame_count-1)-marks.in+1 }
    update({shots:[...sequence.shots,shot]}); setShotId(shot.id)
  }
  function updateRenderedFrame(video: HTMLVideoElement) {
    if (!sequence) return
    // Parked at the end of the sequence: the video shows the last frame, but the playhead stays after it until playback moves it.
    if (parkedFrame.current !== null) { if (!playing) return; parkedFrame.current = null }
    const frame = Math.min(total - 1, Math.max(0, Math.floor(video.currentTime * 24)))
    setProgramFrame(frame)
    let start = 0
    for (const shot of sequence.shots) {
      if (frame < start + shot.duration_frames) { setShotId(shot.id); break }
      start += shot.duration_frames
    }
  }
  useEffect(() => {
    if (!renderedPreview || !playing) return
    let request = 0
    const tick = () => { if (programVideo.current) updateRenderedFrame(programVideo.current); request = requestAnimationFrame(tick) }
    request = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(request)
  }, [renderedPreview, playing, sequence?.id, total])
  function loadedProgram() {
    const video = programVideo.current
    // The rendered cut is one continuous file (gaps are black in it), so it does not depend on the shot under the playhead.
    if(!video || (!renderedPreview && !activeShot)) return
    video.currentTime = renderedPreview || !activeShot ? programFrame / 24 : pendingSeek.current ?? activeShot.source_in_frame / 24
    pendingSeek.current=null
    video.playbackRate=shuttle>0?shuttle:1
    if(playing) void video.play().catch(e => { setPlaying(false); setError(fail(e)) })
  }
  function advance() {
    if (renderedPreview) { setPlaying(false); setProgramFrame(total - 1); return }
    if(!sequence || !activeShot) return
    const next = sequence.shots[activeIndex + 1]
    if(next && playing) { setShotId(next.id); setProgramFrame(shotStart + activeShot.duration_frames) }
    else if(playing&&total>pictureTotal){setProgramFrame(pictureTotal)}
    else { setPlaying(false); const video = programVideo.current; if(video) { video.pause(); video.currentTime = (activeShot.source_in_frame + activeShot.duration_frames) / 24 } }
  }
  function timeUpdate() {
    const video = programVideo.current
    if (video && renderedPreview) { updateRenderedFrame(video); return }
    if(!video || !activeShot || !pictureAtFrame) return
    // Paused, the live video only moves because the editor seeked it, and seekProgram has already set the frame;
    // reading it back here would snap a playhead parked past the picture into the shot the video still holds.
    if (!playing) return
    parkedFrame.current = null
    const local = Math.max(0, Math.floor(video.currentTime * 24) - activeShot.source_in_frame)
    setProgramFrame(shotStart + Math.min(local, activeShot.duration_frames))
    if(playing && local >= activeShot.duration_frames) advance()
  }
  async function playProgram() {
    const video = programVideo.current
    if(!total)return
    if (renderedPreview && video) {
      previewAudio.stop()
      if (playing) { video.pause(); setPlaying(false); return }
      document.querySelectorAll<HTMLMediaElement>('.film-editor video,.film-editor audio').forEach(m => { if (m !== video) m.pause() })
      if (video.ended || programFrame >= total - 1) { video.currentTime = 0; setProgramFrame(0) }
      try { setPlaying(true); await video.play() } catch(e) { setPlaying(false); setError(fail(e)) }
      return
    }
    if(!pictureAtFrame){if(playing){setPlaying(false);previewAudio.stop();return}document.querySelectorAll<HTMLMediaElement>('.film-editor video,.film-editor audio').forEach(m=>m.pause());if(programFrame>=total-1){if(pictureTotal)seekProgram(0);else setProgramFrame(0)}try{if(await previewAudio.start())setPlaying(true)}catch(e){setError(fail(e))}return}
    if(!video || !activeShot) return
    if(playing) { video.pause(); setPlaying(false); previewAudio.stop(); return }
    document.querySelectorAll<HTMLMediaElement>('.film-editor video, .film-editor audio').forEach(media => { if(media !== video) media.pause() })
    try {
      if(video.currentTime >= (activeShot.source_in_frame + activeShot.duration_frames) / 24) video.currentTime = pendingSeek.current ?? activeShot.source_in_frame / 24
      if (!await previewAudio.start()) return
      setPlaying(true)
      await video.play()
    } catch(e) { setPlaying(false); previewAudio.stop(); setError(fail(e)) }
  }
  function stopTransport() { stopAt.current=null;sourceStop.current=null;setShuttle(0);setPlaying(false);previewAudio.stop();[programVideo.current,sourceVideo.current].forEach(v=>{if(v){v.pause();v.playbackRate=1}}) }
  /** `atEnd` lets the playhead park one frame past the last (FCP7's end of sequence) so End and the end of an edit
   *  don't sit on the final frame, where the next Insert / Overwrite would cut into it. Only End and applyEdit pass it. */
  function seekProgram(frame: number, atEnd = false) {
    if(!sequence || !total)return
    const target=Math.max(0,Math.min(atEnd?total:total-1,Math.round(frame)))
    if (renderedPreview && programVideo.current && target>=total) { parkedFrame.current=target; programVideo.current.currentTime=(total-1)/24+0.001; setProgramFrame(target); return }
    if (renderedPreview && programVideo.current) { parkedFrame.current=null; programVideo.current.currentTime = target / 24 + 0.001 /* 1 ms inside the frame: 55/24*24 floors to 54 otherwise */; updateRenderedFrame(programVideo.current); return }
    if(target>=pictureTotal){parkedFrame.current=target;setProgramFrame(target);return}
    parkedFrame.current=null
    let start=0
    for(const shot of sequence.shots){if(target<start+shot.duration_frames&&isGap(shot)){parkedFrame.current=null;setShotId(shot.id);setProgramFrame(target);return}if(target<start+shot.duration_frames&&!isGap(shot)){const seconds=(shot.source_in_frame+target-start)/24+0.001/* 1 ms inside the frame, or the readback floors a frame early */;pendingSeek.current=seconds;setShotId(shot.id);setProgramFrame(target);if(shot.id===activeShot?.id&&programVideo.current&&programVideo.current.readyState>0){programVideo.current.currentTime=seconds;pendingSeek.current=null}break}start+=shot.duration_frames}
  }
  function undo(){if(sequence&&history.length&&!busy){setFuture(items=>[...items,sequence]);setSequence(history.at(-1)!);setHistory(items=>items.slice(0,-1));stopTransport()}}
  function redo(){if(sequence&&future.length&&!busy){setHistory(items=>[...items,sequence]);setSequence(future.at(-1)!);setFuture(items=>items.slice(0,-1));stopTransport()}}
  function sourceTransport(){const video=sourceVideo.current;if(!video)return;previewAudio.stop();setPlaying(false);programVideo.current?.pause();if(video.paused)void video.play().catch(e=>setError(fail(e)));else video.pause()}
  useEffect(()=>{
    if(shuttle>=0)return
    const viewer=activePane==='viewer'||activePane==='browser'
    const startFrame=viewer?(sourceVideo.current?.currentTime??0)*24:programFrame
    const started=performance.now()
    // Wall-clock anchored reverse jog; decoder seeks must not slow the transport clock.
    const timer=window.setInterval(()=>{
      const next=Math.max(0,Math.round(startFrame+(performance.now()-started)*24*shuttle/1000))
      if(viewer){const v=sourceVideo.current;if(v){v.pause();v.currentTime=next/24;setSourceFrame(next)}}else seekProgram(next)
      if(next===0)setShuttle(0)
    },1000/24)
    return ()=>clearInterval(timer)
  },[shuttle,activePane,sequence?.id,renderedPreview])
  useEffect(()=>{if(sourceVideo.current)sourceVideo.current.muted=shuttle!==0&&shuttle!==1},[shuttle,sourceId])
  useEffect(()=>{
    /** Runs one command (from a key or a transport strip button). pane overrides the active pane for strip buttons. */
    const exec=(command:string,event:KeyboardEvent|null,pane:'viewer'|'canvas'|null):boolean=>{
      if(rehearsal||layoutOpen||ctxMenu)return false
      const transportCommand = ['play.toggle','play.stop','play.reverse','play.forward'].includes(command)
      // Discrete presses change speed; holding a key must not race to 8x.
      if (transportCommand && event?.repeat) { event.preventDefault(); return true }
      const viewer=pane?pane==='viewer':(activePane==='viewer'||activePane==='browser')
      const v=viewer?sourceVideo.current:programVideo.current
      const current=viewer?Math.round((sourceVideo.current?.currentTime??0)*24):programFrame
      const seek=(f:number)=>{stopTransport();if(viewer&&sourceVideo.current){const target=Math.max(0,Math.min((source?.frame_count??1)-1,f));sourceVideo.current.currentTime=target/24;setSourceFrame(target)}else seekProgram(f)}
      const sel=sequence?.selection??null
      // A range covering the whole sequence is the same as no In/Out.
      const setSel=(next:{in_frame:number;out_frame:number})=>update({selection:next.in_frame<=0&&next.out_frame>=total?null:next})
      let handled=true
      switch(command){
        case 'window.viewer':(document.activeElement as HTMLElement)?.blur();setActivePane('viewer');setPanel('video');break
        case 'window.canvas':(document.activeElement as HTMLElement)?.blur();setActivePane('canvas');break
        case 'window.timeline':(document.activeElement as HTMLElement)?.blur();setActivePane('timeline');break
        case 'window.browser':(document.activeElement as HTMLElement)?.blur();setActivePane('browser');break
        case 'window.toggleMonitor':setActivePane(activePane==='viewer'?'canvas':'viewer');setPanel('video');break
        case 'play.toggle':setShuttle(0);if(v)v.playbackRate=1;viewer?sourceTransport():void playProgram();break
        case 'play.stop':kHeld.current=true;kCode.current=event?.code??'';stopTransport();break
        case 'play.reverse':if(kHeld.current){seek(current-1);break}stopTransport();setShuttle(shuttleRate(shuttle,-1));break
        case 'play.inToOut':if(viewer)playSourceSegment(marks.in,marks.out??(source?.frame_count??1)-1,null);else playSegment(sel?.in_frame??0,(sel?.out_frame??total)-1,null);break
        case 'play.around':if(viewer)playSourceSegment(Math.max(0,current-48),Math.min((source?.frame_count??1)-1,current+48),current);else playSegment(Math.max(0,current-48),Math.min(total-1,current+48),current);break
        case 'nav.prevEdit':case 'nav.nextEdit':{let points:number[];if(viewer)points=[0,marks.in,marks.out??0,(source?.frame_count??1)-1];else{points=[0,Math.max(0,total-1)];let at=0;for(const shot of sequence?.shots??[]){at+=shot.duration_frames;if(at<total)points.push(at)}}const next=stepPoint(points,current,command==='nav.nextEdit'?1:-1);if(next!==undefined)seek(next);break}
        case 'nav.prevMarker':case 'nav.nextMarker':{if(viewer||!sequence){handled=false;break}const next=stepPoint((sequence.markers??[]).map(m=>m.frame),current,command==='nav.nextMarker'?1:-1);if(next!==undefined)seek(next);break}
        case 'mark.clearIn':if(viewer){if(!boundShot)setSourceMarks(m=>({in:0,out:m.out}))}else if(sel){setSel({in_frame:0,out_frame:sel.out_frame});setMarkFlags({in:false,out:markFlags?.out??sel.out_frame<total})}break
        case 'mark.clearOut':if(viewer){if(!boundShot)setSourceMarks(m=>({...m,out:null}))}else if(sel){setSel({in_frame:sel.in_frame,out_frame:total});setMarkFlags({in:markFlags?.in??true,out:false})}break
        case 'mark.clip':if(viewer){if(!boundShot)setSourceMarks({in:0,out:null})}else if(activeItem&&programFrame<pictureTotal){update({selection:{in_frame:shotStart,out_frame:shotStart+activeItem.duration_frames}});setMarkFlags({in:true,out:true})}else handled=false;break
        case 'mark.add':if(!viewer&&sequence&&total)update({markers:[...(sequence.markers??[]),{id:crypto.randomUUID(),label:`Marker ${(sequence.markers?.length??0)+1}`,frame:Math.min(total-1,current)}]});else handled=false;break
        case 'mark.delete':if(!viewer&&sequence?.markers?.some(m=>m.frame===current))update({markers:sequence.markers.filter(m=>m.frame!==current)});else handled=false;break
        case 'mark.deleteAll':if(!viewer&&sequence?.markers?.length)update({markers:[]});else handled=false;break
        case 'timeline.trackSize':setTrackSize(size=>(size+1)%3);break
        case 'window.standard':setUpperSplit(52);setZoom(100);setTrackSize(1);break
        case 'window.find':setActivePane('browser');document.querySelector<HTMLInputElement>('.fcp-bin-filter')?.focus();break
        case 'window.keyboard':setLayoutOpen(true);break
        case 'edit.insert':threePoint('insert');break
        case 'edit.overwrite':threePoint('overwrite');break
        case 'edit.replace':threePoint('replace');break
        case 'edit.deselect':if(activePane==='browser')setBinSelection(emptyBrowserSelection);else{setSelectedClip(null);setSelectedEdit(null)}break
        case 'tool.select':setTool('select');break
        case 'tool.razor':setTool('razor');break
        case 'tool.roll':{const next=tool==='roll'?'ripple':'roll';setTool(next);if(selectedEdit&&selectedEdit.leftId&&selectedEdit.rightId)setSelectedEdit({...selectedEdit,side:next==='roll'?'both':(selectedEdit.side==='both'?'left':selectedEdit.side)});break}
        case 'tool.slip':setTool('slip');break
        case 'timeline.snap':setSnapping(s=>!s);setEditNote(snapping?'Snapping off (N).':'Snapping on (N): drags snap to cuts, the playhead, markers and In/Out.');break
        case 'edit.selectEdit':{if(viewer||!sequence?.shots.length){handled=false;break}const p=nearestEditPoint(sequence.shots,current,tool==='ripple'?'left':'both');if(p){setSelectedEdit(p);setSelectedClip(null);setActivePane('timeline');const f=editPointFrame(sequence.shots,p);if(f!==null){stopTransport();seekProgram(f,true)}}break}
        case 'edit.toggleSide':{if(!selectedEdit||!selectedEdit.leftId||!selectedEdit.rightId){handled=false;break}const order=['left','both','right'] as const;setSelectedEdit({...selectedEdit,side:order[(order.indexOf(selectedEdit.side)+1)%3]});break}
        case 'edit.trimBack':case 'edit.trimForward':case 'edit.trimBackMulti':case 'edit.trimForwardMulti':{if(viewer||!sequence){handled=false;break}const step=(command.endsWith('Multi')?5:1)*(command.startsWith('edit.trimBack')?-1:1);const held=!!event?.repeat;if(tool==='slip'&&selectedShot){applyEdit(slipEdit(sequence.shots,selectedShot.id,step,frameCounts),{},'clip',held);break}if(selectedEdit){applyEdit(trimEdit(sequence.shots,selectedEdit,step,frameCounts),{},'edit',held);break}setError(tool==='slip'?'Select a shot on V1 to slip it with [ and ].':'Select an edit point first: press V for the one nearest the playhead.');break}
        case 'edit.liftRange':case 'edit.extractRange':{
          if(viewer||!sequence){handled=false;break}
          if(!sel){setError('Mark an In and an Out on the sequence first (I and O), then ; lifts or \' extracts the range.');break}
          const inF=sel.in_frame,outF=Math.min(sel.out_frame,total),extract=command==='edit.extractRange'
          const r=(extract?extractRange:liftRange)(sequence.shots,inF,outF)
          if(!r.ok){setError(r.error);break}
          const explicit=sequence.timeline_duration_frames
          applyEdit(r,{audio_tracks:cutAudioRange(sequence.audio_tracks,inF,outF,extract),selection:null,...(extract&&explicit!==undefined&&explicit!==null?{timeline_duration_frames:Math.max(explicit-(outF-inF),duration(r.shots),1)}:{})})
          setMarkFlags(null)
          break}
        case 'edit.addEdit':if(viewer||!sequence){handled=false;break}applyEdit(addEdit(sequence.shots,current));break
        case 'edit.extend':if(viewer||!sequence){handled=false;break}if(!selectedEdit){setError('Select an edit point first (V), then move the playhead and press E.');break}applyEdit(extendEdit(sequence.shots,selectedEdit,current,frameCounts),{},'edit');break
        case 'edit.rippleDelete':if(viewer){handled=false;break}if(selectedShot&&sequence)applyEdit(rippleDelete(sequence.shots,selectedShot.id));else if(selectedAudio)handled=false;else setError('Select a shot on V1 first, then Shift+Delete removes it and closes the gap.');break
        case 'edit.lift':if(viewer){handled=false;break}if(selectedAudio&&sequence){update({audio_tracks:sequence.audio_tracks.filter(t=>t.id!==selectedAudio.id)});setSelectedClip(null);setEditNote('Removed the audio placement; its source is kept.')}else if(selectedShot&&sequence)applyEdit(liftEdit(sequence.shots,selectedShot.id));else handled=false;break
        case 'play.forward':{if(kHeld.current){seek(current+1);break}const rate=shuttleRate(shuttle,1);setShuttle(rate);if(v){v.playbackRate=rate;if(v.paused)viewer?sourceTransport():void playProgram()}else if(!viewer)void playProgram();break}
        case 'nav.prevFrame':seek(current-1);break
        case 'nav.nextFrame':seek(current+1);break
        case 'nav.back1s':seek(current-24);break
        case 'nav.fwd1s':seek(current+24);break
        case 'nav.start':seek(0);break
        case 'nav.end':if(viewer)seek((source?.frame_count??1)-1);else{stopTransport();seekProgram(total,true)}break
        case 'mark.in':if(viewer)markIn(current);else if(sequence&&total){const at=Math.min(current,total-1)/* the saved selection needs In on a frame, not the parked end */;const keepOut=!!sel&&sel.out_frame>at&&(markFlags?.out??false);setSel({in_frame:at,out_frame:keepOut?sel!.out_frame:total});setMarkFlags({in:true,out:keepOut})}break
        case 'mark.out':if(viewer)markOut(current);else if(sequence&&total){const keepIn=!!sel&&sel.in_frame<=current&&(markFlags?.in??false);setSel({in_frame:keepIn?sel!.in_frame:0,out_frame:Math.min(total,current+1)});setMarkFlags({in:keepIn,out:true})}break
        case 'mark.clearBoth':if(viewer){if(!boundShot)setSourceMarks({in:0,out:null})}else if(sel)update({selection:null});break
        case 'nav.in':seek(viewer?marks.in:sel?.in_frame??0);break
        case 'nav.out':seek(viewer?marks.out??(source?.frame_count??1)-1:(sel?.out_frame??total)-1);break
        case 'nav.matchFrame':if(activeShot){stopTransport();const frame=Math.min((catalog.assets.find(a=>a.id===activeShot.asset_id)?.frame_count??1)-1,activeShot.source_in_frame+Math.min(activeShot.duration_frames-1,Math.max(0,programFrame-shotStart)));pendingSourceFrame.current=frame;setSourceId(activeShot.asset_id);setPanel('video');setActivePane('viewer');if(sourceId===activeShot.asset_id&&sourceVideo.current){sourceVideo.current.currentTime=frame/24;setSourceFrame(frame);pendingSourceFrame.current=null}}break
        case 'edit.undo':undo();break
        case 'edit.redo':redo();break
        case 'edit.save':if(dirty)void save();break
        case 'edit.saveAll':if(dirty||draftIds.length)void saveAll();break
        case 'edit.render':render();break
        case 'timeline.zoomIn':setZoom(z=>Math.min(800,z*1.5));break
        case 'timeline.zoomOut':setZoom(z=>Math.max(100,z/1.5));break
        case 'timeline.fit':setZoom(100);break
        default:handled=false
      }
      return handled
    }
    execRef.current=exec
    const key=(event:KeyboardEvent)=>{
      if(event.isComposing||rehearsal||layoutOpen||ctxMenu)return
      const command=bindings.get(chordFromEvent(event)??'')
      const target = event.target instanceof HTMLElement ? event.target : null
      if(!command){
        // FCP7 typed timecode: digits, + or - with a monitor or the Timeline active.
        if(!event.ctrlKey&&!event.altKey&&!event.metaKey&&/^[0-9+\-]$/.test(event.key)&&!target?.closest('textarea,select,[contenteditable]:not([contenteditable=false]),input:not([type=range]),audio,video')){event.preventDefault();stopTransport();setTcEntry({target:activePane==='viewer'||activePane==='browser'?'source':'program',text:event.key})}
        return
      }
      const textEntry = target?.closest('textarea,select,[contenteditable]:not([contenteditable=false]),input:not([type=range]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=reset])')
      if (textEntry && !COMMAND_BY_ID.get(command)?.inText) return
      const transportCommand = ['play.toggle','play.stop','play.reverse','play.forward'].includes(command)
      if (!transportCommand && target?.closest('input:not([type=range]),audio,video') && !COMMAND_BY_ID.get(command)?.inText) return
      if(exec(command,event,null))event.preventDefault()
    }
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)
  })
  const generationTarget:GenerationTarget|null=sequence?{id:sequence.id,title:sequence.title,revision:saved?.revision??sequence.revision,shots:sequence.shots,duration_frames:total,timeline_duration_frames:sequence.timeline_duration_frames}:null
  const pending=generations.filter(p=>p.placed_revision===null)
  const plannedSlot=(p:GenerationPlacement)=>(p.job.metadata?.planned_shot as {slot?:{start_frame:number;end_frame:number}}|undefined)?.slot
  const generationStart=(p:GenerationPlacement)=>plannedSlot(p)?.start_frame??(p.destination.track==='V1'?duration(sequence?.shots.slice(0,p.destination.insert_index??0)??[]):p.destination.start_frame??0)
  const generationFrames=(p:GenerationPlacement)=>plannedSlot(p)?plannedSlot(p)!.end_frame-plannedSlot(p)!.start_frame:Math.max(1,(p.job.metadata?.length_frames??124)-((p.job.metadata?.continuation as {boundary_policy?:{drop_generated_first_frames?:number}}|undefined)?.boundary_policy?.drop_generated_first_frames??0))
  const timelineSpan=Math.max(1,total,...pending.map(p=>generationStart(p)+(p.destination.track==='V1'?generationFrames(p):Math.max(1,Math.min(720,total-generationStart(p))))))
  const pendingBlocks=(track:'V1'|'A1'|'A2')=>pending.filter(p=>showHidden||!hiddenJobs.includes(p.job_id)).filter(p=>track==='A2'?p.destination.track==='A2':p.destination.track==='V1'&&(track==='V1'||!plannedSlot(p))).map(p=><button key={`${p.job_id}-${track}`} className={`generation-pending ${['pending','submitting','queued','running','polling'].includes(p.stage)?'generation-active':''}`} style={{left:`${100*generationStart(p)/timelineSpan}%`,width:`${100*(p.destination.track==='V1'?generationFrames(p):Math.max(1,Math.min(720,total-generationStart(p))))/timelineSpan}%`}} data-hidden={hiddenJobs.includes(p.job_id)||undefined} title={`${p.job.label}: ${generationStage(p.stage)}. A requested take, not a clip yet. Click for what to do next.`} onContextMenu={e=>openCtx(e,{kind:'block',jobId:p.job_id})} onClick={e=>{e.stopPropagation();setBlockCard({p,x:Math.min(e.clientX,window.innerWidth-300),y:Math.max(8,e.clientY-200)})}}>{p.job.label} · <JobStage job={p.job} stage={p.stage}/></button>)
  const audioConfig: EditorConfig | undefined = sequence ? {scene_id:sequence.id,title:sequence.title,fps:24,duration_frames:total,seed:0,subjects:[],placements:[],ambience:[],audio_tracks:sequence.audio_tracks}:undefined
  // ---- Presentation only below: layout preferences and derived display values. No sequence data changes. ----
  const [upperSplit,setUpperSplit]=useState(()=>{try{const v=Number(localStorage.getItem('llr.film.split.v1'));return v>=28&&v<=72?v:52}catch{return 52}})
  /** Browser selection stays separate from the open Viewer source and Timeline sequence. */
  const [binSelection,setBinSelection]=useState<BrowserSelection>(emptyBrowserSelection)
  /** Step 4 slice C: the transport strips run the same command code as the keyboard. */
  const execRef=useRef<((command:string,event:KeyboardEvent|null,pane:'viewer'|'canvas'|null)=>boolean)|null>(null)
  const [volume,setVolume]=useState(()=>{try{const v=Number(localStorage.getItem('llr.film.volume.v1'));return Number.isFinite(v)&&localStorage.getItem('llr.film.volume.v1')!==null?Math.min(1,Math.max(0,v)):1}catch{return 1}})
  useEffect(()=>{try{localStorage.setItem('llr.film.volume.v1',String(volume))}catch{/* optional preference */}previewAudio.setVolume(volume)},[volume])// eslint-disable-line react-hooks/exhaustive-deps
  // Videos remount per take/render, so apply the monitor volume after every render (cheap).
  useEffect(()=>{document.querySelectorAll<HTMLVideoElement>('.fcp-film video').forEach(v=>{if(v.volume!==volume)v.volume=volume})})
  /** Step 4: audio sources and reference stills share the Browser with video takes (read-only lists). */
  const [audioLibrary,setAudioLibrary]=useState<AudioAsset[]>([])
  const [stills,setStills]=useState<ReferenceImage[]>([])
  const [stillId,setStillId]=useState('')
  /** All generation jobs (picture + sound takes), for linking a take's picture to its sound and for the Queue. */
  const [genJobs,setGenJobs]=useState<GenerationJob[]>([])
  // Finished takes import themselves on the server (2026-11-19): pull a clip into the Browser as soon as a job names it, and keep
  // asking for a short while when a job is finished but its import has not landed yet (no error reported).
  const importWait=useRef(new Map<string,number>()),catalogAsked=useRef(new Set<string>())
  useEffect(()=>{
    const missing=genJobs.map(j=>j.video_asset_id).filter((id):id is string=>!!id&&!catalog.assets.some(a=>a.id===id)&&!catalogAsked.current.has(id))
    if(missing.length){missing.forEach(id=>catalogAsked.current.add(id));void refreshCatalog().catch(()=>{})}
    const waiting=genJobs.filter(j=>j.status==='success'&&j.ready_to_import&&!j.video_asset_id&&!j.import_error&&(importWait.current.get(j.id)??0)<10)
    if(!waiting.length)return
    const timer=window.setTimeout(()=>{for(const j of waiting)importWait.current.set(j.id,(importWait.current.get(j.id)??0)+1);setQueueEpoch(e=>e+1)},3000)
    return()=>clearTimeout(timer)
  },[genJobs]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{let live=true;void Promise.all([api<{assets:AudioAsset[]}>('audio').then(r=>r.assets).catch(()=>null),api<{images:ReferenceImage[]}>('film/images').then(r=>r.images).catch(()=>null),api<{jobs:GenerationJob[]}>('film/generation').then(r=>r.jobs).catch(()=>null)]).then(([a,i,j])=>{if(!live)return;if(a)setAudioLibrary(a);if(i)setStills(i);if(j)setGenJobs(j)});return()=>{live=false}},[catalog,queueEpoch])
  const linkedAudioId=source?genJobs.find(j=>j.video_asset_id===source.id)?.audio_asset_id:undefined
  const linkedAudio=linkedAudioId?audioLibrary.find(a=>a.id===linkedAudioId):undefined
  // A take that is now in the open sequence no longer needs its marker.
  useEffect(()=>{if(!sequence)return;const done=Object.keys(takeSpots).filter(id=>{const j=genJobs.find(x=>x.id===id);return !!saved&&takeSpots[id].sequence_id===saved.id&&!!j?.video_asset_id&&saved.shots.some(s=>!isGap(s)&&s.asset_id===j.video_asset_id)});if(done.length)setTakeSpots(s=>{const n={...s};for(const id of done)delete n[id];return n})},[saved?.shots,genJobs])// eslint-disable-line react-hooks/exhaustive-deps
  const [seqOpen,toggleSeq]=useFold('sequences');const [srcOpen,toggleSrc]=useFold('sources');const userBins=useUserBins()
  const binItems=useMemo<BinItem[]>(()=>{const meta=(p:Record<string,unknown>|undefined)=>{const g=(p?.generation_metadata??{}) as Record<string,unknown>;return{seed:(typeof g.seed==='number'||typeof g.seed==='string')?g.seed:undefined,model:typeof g.model==='string'?g.model:undefined}}
    return[...catalog.assets.map(a=>({kind:'video' as const,id:a.id,label:a.label,status:a.status,version:a.version,seconds:a.frame_count/24,media:a.media_url,thumbFrame:Math.min(24,Math.max(0,a.frame_count-1)),width:a.width,height:a.height,created:(a as unknown as {created?:string}).created,...meta(a.provenance)})),
      ...audioLibrary.map(a=>({kind:'audio' as const,id:a.id,label:a.label,status:a.status,version:a.version,seconds:a.duration_seconds,created:(a as unknown as {created?:string}).created,...meta(a.provenance)})),
      ...stills.map(s=>({kind:'still' as const,id:s.id,label:s.label,status:'reference',seconds:null,media:s.media_url,width:s.width,height:s.height,created:(s as unknown as {created?:string}).created,note:(s as unknown as {usage?:string}).usage,...meta(s.provenance)}))]},[catalog.assets,audioLibrary,stills])
  const usedCount=useMemo(()=>{const m=new Map<string,number>();for(const p of catalog.projects)for(const s of p.sequences as unknown as {shots?:Shot[];audio_tracks?:AudioPlacement[]}[]){for(const x of s.shots??[])if(!isGap(x))m.set(x.asset_id,(m.get(x.asset_id)??0)+1);for(const x of s.audio_tracks??[])m.set(x.asset_id,(m.get(x.asset_id)??0)+1)}return m},[catalog.projects])
  const inSequence=useMemo(()=>new Set([...(sequence?.shots??[]).flatMap(s=>isGap(s)?[]:[s.asset_id]),...(sequence?.audio_tracks??[]).map(a=>a.asset_id)]),[sequence])
  // After usedCount: the guide for a Generate-tab take reads it (via takeAsPlacement).
  // A job just requested may not be in the job list yet: show it as waiting rather than dropping back to step 1.
  const guidePlacement=guide?.jobId?generations.find(p=>p.job_id===guide.jobId)??takeAsPlacement(genJobs.find(x=>x.id===guide.jobId)??{id:guide.jobId,label:genSnap?.label.trim()||'New take',status:'pending'}):null
  const guideJob=guidePlacement?.job
  const guideVideo=guidePlacement?catalog.assets.find(a=>a.id===(guidePlacement.video_asset_id??guidePlacement.job.video_asset_id)):undefined
  // A job with a server destination (continuation, shot plan) is placed by the server's own rules, even when its sequence is not open.
  const guideClient=!!guidePlacement&&!guidePlacement.job.destination&&!generations.some(p=>p.job_id===guidePlacement.job_id)
  const guideInTimeline=!!guideVideo&&inSequence.has(guideVideo.id)
  const guideSaved=!!guideVideo&&(!!saved?.shots.some(s=>!isGap(s)&&s.asset_id===guideVideo.id)||!!guideJob&&!takeSpots[guideJob.id]&&!guideInTimeline&&(usedCount.get(guideVideo.id)??0)>0)
  const guideSpot=guideJob&&sequence&&takeSpots[guideJob.id]?.sequence_id===sequence.id?resolveSpot(sequence.shots,takeSpots[guideJob.id],programFrame):null
  const guideActions={
    gen:genSnap,
    setBrief:(v:string)=>genControl.current?.setBrief(v),setLabel:(v:string)=>genControl.current?.setLabel(v),setWhere:(v:GenSnapshot['where'])=>genControl.current?.setWhere(v),
    generate:()=>genControl.current?.generate(),
    clearSetup:()=>genControl.current?.clearSetup(),
    prepareAgain:()=>{const s=genSnap?.setup;if(s?.shotId)prepareContinuation(s.shotId)},
    prepareBlock:genSnap?.setup?.kind==='continuation'?continuationBlock(genSnap.setup.sequenceId,genSnap.setup.shotId):null,
    canImport:!!guideJob?.ready_to_import&&!guideJob.video_asset_id,
    importTake:()=>{if(guideJob)importTakeNow(guideJob)},
    resume:guideJob?.can_resume&&!guideJob.video_asset_id?()=>{const job=guideJob;void action(async()=>{await resumeJob('take',job.id);setQueueEpoch(e=>e+1);setStatus(`Asked the worker about “${job.label}” again (nothing was resubmitted).`)})}:null,
    openReview:()=>{if(guideVideo)reviewGeneratedVideo(guideVideo.id)},
    audition:guideJob&&guideVideo&&!guideInTimeline?()=>auditionTake(guideJob):null,
    spotNote:guideSpot&&!('error' in guideSpot)?guideSpot.note:null,
    placeAtSpot:()=>{if(guideJob)placeTakeNow(guideJob)},
    placeAtPlayhead:()=>{if(guideJob&&sequence)placeTakeNow(guideJob,{sequence_id:sequence.id,kind:'playhead',frame:programFrame})},
    playheadNote:seqTc(programFrame),frame:programFrame,
    save:()=>{void save()},
    saveNote:dirty?(editNote||'sequence edits'):'',
    busy:busy||!!exporting,
    error,
  }
  /** Import a finished take by hand (only needed when its automatic import failed). It lands in the Browser. */
  function importTakeNow(job:GenerationJob){void action(async()=>{await importTakeJob(job.id);setQueueEpoch(e=>e+1);await refreshCatalog();setStatus(`Imported “${job.label}” into the Browser. Drag it onto the timeline, or Insert it.`)})}

  /** ---- Right-click menus (ContextMenu.tsx). Only what was clicked is stored; entries are built from current state each render,
   *  so a job that finishes while the menu is open is reflected at once. */
  type CtxTarget={kind:'bin';id:string;itemKind:BinItem['kind'];keys?:string[]}|{kind:'shot';id:string}|{kind:'audio';id:string}|{kind:'job';jobId:string;jobKind:'take'|'music'}|{kind:'spot';jobId:string}|{kind:'block';jobId:string}
  const [ctxMenu,setCtxMenu]=useState<{target:CtxTarget;x:number;y:number}|null>(null)
  const keyOf=(command:string)=>keymap[command]?.[0]
  const editBlock=!sequence?'Open a sequence first.':busy?'Wait for the current action to finish.':exporting?'Wait for the export to finish.':rehearsal?'Exit the FMV rehearsal first.':null
  /** Browser → V1 (picture only). Uses the Viewer's In–Out when this take is the Viewer's source, otherwise the whole clip. */
  function sendToTimeline(asset:VideoAsset,kind:'insert'|'overwrite'|'append'){
    if(!sequence)return
    const useMarks=source?.id===asset.id&&!boundShot
    const sourceIn=useMarks?marks.in:0,length=useMarks?(marks.out??asset.frame_count-1)-marks.in+1:asset.frame_count
    const at=kind==='append'?duration(sequence.shots):programFrame
    const result=(kind==='overwrite'?overwriteEdit:insertEdit)(sequence.shots,at,asset.id,sourceIn,length)
    const audioNote=kind==='insert'&&result.ok&&sequence.audio_tracks.length?' Audio stayed where it was, so sound placed under later shots is now out of sync with them.':''
    applyEdit(result.ok?{...result,message:result.message+audioNote}:result)
  }
  /** Browser → A1 / A2 at the playhead, trimmed to fit the sequence (the server refuses audio past the end). */
  function placeAudioAtPlayhead(a:AudioAsset,role:'production'|'music'){
    if(!sequence)return
    const start=programFrame,full=Math.floor(a.duration_seconds*24)
    if(start>=total){setError('The playhead is at the end of the sequence. Move it back, or make the sequence longer (Sequence duration), then place the sound.');return}
    const len=Math.min(full,total-start)
    if(len<1){setError('This sound is too short to place.');return}
    update({audio_tracks:[...sequence.audio_tracks,{id:crypto.randomUUID(),role,asset_id:a.id,start_frame:start,source_in_frame:0,duration_frames:len,gain_db:0,fade_in_frames:0,fade_out_frames:0,enabled:true}]})
    setEditNote(`Placed “${a.label}” on ${role==='music'?'A2':'A1'} at ${seqTc(start)}${len<full?`, trimmed to ${(len/24).toFixed(2)}s to fit the sequence`:''}.`)
  }
  /** Browser → timeline by drag and drop (Boden, 2026-11-19). Video dropped on V1 is an Insert at the drop point (a generated take
   *  brings its production sound to A1, like "Insert with its sound"); sound dropped on A1/A2 is placed there. One undo step. */
  const [binDrop,setBinDrop]=useState<{track:'V1'|'A1'|'A2';frame:number}|null>(null)
  const BIN_DRAG='application/x-llr-source',BIN_MULTI='application/x-llr-sources'
  function binDropFrame(e:React.DragEvent<HTMLElement>,track:'V1'|'A1'|'A2'){
    const r=e.currentTarget.getBoundingClientRect(),perFrame=Math.max(0.0001,r.width/timelineSpan)
    const raw=Math.max(0,Math.round((e.clientX-r.left)/perFrame)),picture=duration(sequence?.shots??[])
    const targets=[0,programFrame,picture];{let at=0;for(const s of sequence?.shots??[]){at+=s.duration_frames;targets.push(at)}}
    const f=snapping?snapFrame(raw,targets,Math.max(1,Math.round(10/perFrame))).frame:raw
    // V1: past the end of the picture means "add it at the end" (no accidental gap). Audio stays inside the sequence.
    return track==='V1'?Math.min(f,picture):Math.max(0,Math.min(f,total-1))
  }
  function binDragOver(e:React.DragEvent<HTMLElement>,track:'V1'|'A1'|'A2'){
    if(!sequence||!e.dataTransfer.types.includes(BIN_DRAG))return
    e.preventDefault();e.dataTransfer.dropEffect=editBlock?'none':'copy'
    const frame=binDropFrame(e,track);setBinDrop(d=>d&&d.track===track&&d.frame===frame?d:{track,frame})
  }
  function binDragLeave(e:React.DragEvent<HTMLElement>){if(!e.currentTarget.contains(e.relatedTarget as Node))setBinDrop(null)}
  function binDropOn(e:React.DragEvent<HTMLElement>,track:'V1'|'A1'|'A2'){
    if(!sequence||!e.dataTransfer.types.includes(BIN_DRAG))return
    e.preventDefault();setBinDrop(null)
    if(editBlock){setError(editBlock);return}
    let keys:string[]=[];try{const m=e.dataTransfer.getData(BIN_MULTI);keys=m?JSON.parse(m):[e.dataTransfer.getData(BIN_DRAG)]}catch{keys=[e.dataTransfer.getData(BIN_DRAG)]}
    const at=binDropFrame(e,track)
    const ids=(kind:string)=>keys.filter(k=>typeof k==='string'&&k.startsWith(kind+':')).map(k=>k.slice(kind.length+1))
    if(track==='V1'){
      const clips=ids('video').map(id=>catalog.assets.find(a=>a.id===id)).filter((a):a is VideoAsset=>!!a)
      if(!clips.length){setError(ids('audio').length?'Drop sound on A1 (production) or A2 (music).':'Only video clips go on V1.');return}
      const job=clips.length===1?genJobs.find(j=>j.video_asset_id===clips[0].id):undefined
      if(job?.audio_asset_id&&!job.destination){placeTakeNow(job,{sequence_id:sequence.id,kind:'playhead',frame:at});return}
      let shots:EditShot[]=sequence.shots,cursor=at
      for(const clip of clips){const r=insertEdit(shots,cursor,clip.id,0,clip.frame_count);if(!r.ok){setError(r.error);return}shots=r.shots;cursor+=clip.frame_count}
      const audioNote=sequence.audio_tracks.length&&at<duration(sequence.shots)?' Audio stayed where it was, so sound under later shots is now out of sync with them.':''
      applyEdit({ok:true,shots,playhead:cursor,message:`Inserted ${clips.length===1?`“${clips[0].label}”`:`${clips.length} clips`} at ${seqTc(at)}${clips.length>1?' (picture only)':''}.${audioNote}`})
      return
    }
    const sounds=ids('audio').map(id=>audioLibrary.find(a=>a.id===id)).filter((a):a is AudioAsset=>!!a)
    if(!sounds.length){setError(ids('video').length?'Drop video clips on V1.':'Only sound goes on A1 / A2.');return}
    const role=track==='A2'?'music':'production',added=[];let start=at
    for(const a of sounds){const len=Math.min(Math.floor(a.duration_seconds*24),total-start);if(len<1)break;added.push({id:crypto.randomUUID(),role,asset_id:a.id,start_frame:start,source_in_frame:0,duration_frames:len,gain_db:0,fade_in_frames:0,fade_out_frames:0,enabled:true} as const);start+=len}
    if(!added.length){setError('No room for this sound before the end of the sequence. Make the sequence longer (Sequence duration) first.');return}
    update({audio_tracks:[...sequence.audio_tracks,...added]})
    setEditNote(`Placed ${added.length===1?`“${sounds[0].label}”`:`${added.length} sounds`} on ${track} at ${seqTc(at)}${added.length<sounds.length?`; ${sounds.length-added.length} did not fit`:''}.`)
  }
  const dropMarker=(track:'V1'|'A1'|'A2')=>binDrop?.track===track?<i aria-hidden="true" className="fcp-drop-marker" style={{left:`${100*binDrop.frame/timelineSpan}%`}}><b>{seqTc(binDrop.frame)}</b></i>:null
  function menuModel(t:CtxTarget):{title:string;subtitle?:string;sections:MenuEntry[][]}|null{
    if(t.kind==='bin'){
      const item=binItems.find(i=>i.id===t.id&&i.kind===t.itemKind);if(!item)return null
      const open:MenuEntry={id:'open',icon:item.kind==='still'?'open-still':item.kind==='audio'?'open-audio':'open-viewer',label:item.kind==='still'?'Open still':item.kind==='audio'?'Open in Audio':'Open in Viewer',hint:item.kind==='video'?'Watch it and mark In / Out.':item.kind==='audio'?'Listen and trim it in the Audio tab.':'Show the reference still in the Viewer.',run:()=>openBinItem(item)}
      if(item.kind==='still')return {title:item.label,subtitle:'Reference still',sections:[[open]]}
      const uses=usedCount.get(item.id)??0
      const sub=`${item.kind==='audio'?'Audio':'Video'}${inSequence.has(item.id)?' · in this sequence':uses?` · used ${uses}×`:' · unused'}${item.seconds!==null?` · ${item.seconds.toFixed(2)}s`:''}`
      if(item.kind==='audio'){
        const a=audioLibrary.find(x=>x.id===item.id)
        const block=editBlock??(programFrame>=total?'The playhead is at the end: move it back first.':null)
        const place=(role:'production'|'music'):MenuEntry=>({id:`place-${role}`,icon:role==='music'?'place-a2':'place-a1',tone:'edit',label:role==='music'?'Place on A2 (music) at playhead':'Place on A1 (production) at playhead',hint:`Starts at ${seqTc(programFrame)}; trimmed if it runs past the end.`,disabled:block,run:()=>{if(a)placeAudioAtPlayhead(a,role)}})
        return {title:item.label,subtitle:sub,sections:[[open],[place('production'),place('music')]]}
      }
      const asset=catalog.assets.find(a=>a.id===item.id),job=genJobs.find(j=>j.video_asset_id===item.id)
      const block=editBlock
      const useMarks=source?.id===item.id&&!boundShot
      const what=useMarks?'the Viewer’s In–Out':'the whole clip'
      const pic=job?.audio_asset_id?' (picture only)':''
      const send:MenuEntry[]=[
        // Server-placed requests (continuation, shot plan) go in through their Queue card, never a plain Insert.
        ...(job?.audio_asset_id&&!job.destination?[{id:'place-take',icon:'place-take' as const,tone:'edit' as const,label:'Insert with its sound at playhead',hint:`Picture on V1 and its production sound on A1, at ${seqTc(programFrame)}.`,disabled:editBlock,run:()=>placeTakeNow(job,{sequence_id:sequence!.id,kind:'playhead',frame:programFrame})}]:[]),
        {id:'insert',icon:'insert',tone:'edit',label:`Insert at playhead${pic}`,hint:`Puts ${what} at ${seqTc(programFrame)}; later shots move right.`,shortcut:keyOf('edit.insert'),disabled:block,run:()=>{if(asset)sendToTimeline(asset,'insert')}},
        {id:'overwrite',icon:'overwrite',tone:'edit',label:`Overwrite at playhead${pic}`,hint:`Puts ${what} over what is at ${seqTc(programFrame)}.`,shortcut:keyOf('edit.overwrite'),disabled:block,run:()=>{if(asset)sendToTimeline(asset,'overwrite')}},
        {id:'append',icon:'append',tone:'edit',label:`Append to end${pic}`,hint:`Adds ${what} after the last shot.`,disabled:block,run:()=>{if(asset)sendToTimeline(asset,'append')}},
      ]
      const audition:MenuEntry[]=job&&!inSequence.has(item.id)?[{id:'audition',icon:'audition',label:'Audition in context',hint:'Plays it between its neighbours without placing it.',run:()=>auditionTake(job)}]:[]
      const del:MenuEntry={id:'delete-clip',icon:'remove',tone:'danger',label:'Delete clip…',hint:'Remove it from the editor, or delete its file from disk. Asks first.',disabled:busy?'Wait for the current action to finish.':uses?`Used ${uses}× in saved sequences: take it off those timelines first.`:inSequence.has(item.id)?'In the open sequence: remove it from the timeline first.':null,run:()=>{if(asset)setDelClips({clips:[{id:asset.id,label:asset.label,status:asset.status,version:asset.version}],cleanup:false})}}
      return {title:item.label,subtitle:sub,sections:[[open,...audition],send,[del]]}
    }
    if(t.kind==='shot'){
      if(!sequence)return null
      const index=sequence.shots.findIndex(s=>s.id===t.id),shot=sequence.shots[index];if(!shot)return null
      if(isGap(shot))return {title:'Gap',subtitle:`${shot.duration_frames} frames (${(shot.duration_frames/24).toFixed(2)}s) · black in the export`,sections:[[{id:'close-gap',icon:'close-gap',tone:'edit',label:'Close gap',hint:'Later shots move left to fill it.',shortcut:keyOf('edit.rippleDelete'),disabled:editBlock,run:()=>applyEdit(rippleDelete(sequence.shots,shot.id))}]]}
      const asset=catalog.assets.find(a=>a.id===shot.asset_id)
      return {title:asset?.label??'Shot',subtitle:`Shot ${index+1} of ${sequence.shots.length} · ${(shot.duration_frames/24).toFixed(2)}s`,sections:[
        [{id:'open-shot',icon:'open-viewer',label:'Open in Viewer',hint:'Opens this shot; In / Out there trim it in the sequence.',run:()=>openShotInViewer(shot)}],
        [{id:'continue',icon:'continue-shot',tone:'edit',label:'Continue this shot',hint:'Prepares a new take that starts from its last rendered frame.',disabled:busy?'Wait for the current action to finish.':continuationBlock(sequence.id,shot.id),run:()=>prepareContinuation(shot.id)}],
        [{id:'lift',icon:'lift',tone:'edit',label:'Lift',hint:'Removes it and leaves a gap.',shortcut:keyOf('edit.lift'),disabled:editBlock,run:()=>applyEdit(liftEdit(sequence.shots,shot.id))},
         {id:'ripple',icon:'ripple-delete',tone:'edit',label:'Ripple delete',hint:'Removes it; later shots close up.',shortcut:keyOf('edit.rippleDelete'),disabled:editBlock,run:()=>applyEdit(rippleDelete(sequence.shots,shot.id))},
         {id:'earlier',icon:'move-earlier',tone:'edit',label:'Move earlier',hint:'Swaps it with the shot before.',disabled:editBlock??(index<=0?'Already the first shot.':null),run:()=>move(index,-1)},
         {id:'later',icon:'move-later',tone:'edit',label:'Move later',hint:'Swaps it with the shot after.',disabled:editBlock??(index>=sequence.shots.length-1?'Already the last shot.':null),run:()=>move(index,1)}],
      ]}
    }
    if(t.kind==='audio'){
      const tr=sequence?.audio_tracks.find(a=>a.id===t.id);if(!sequence||!tr)return null
      const a=audioLibrary.find(x=>x.id===tr.asset_id),lane=tr.role==='music'?'A2 music':'A1 production'
      return {title:a?.label??lane,subtitle:`${lane} · ${seqTc(tr.start_frame)} · ${(tr.duration_frames/24).toFixed(2)}s${tr.enabled?'':' · muted'}`,sections:[
        [{id:'open-audio',icon:'open-audio',label:'Open in Audio',hint:'Gain, fades and trim in the Audio tab.',run:()=>reviewGeneratedAudio(tr.asset_id,tr.role)}],
        [{id:'mute',icon:tr.enabled?'mute':'unmute',tone:'edit',label:tr.enabled?'Mute':'Unmute',hint:tr.enabled?'Keeps it on the timeline but silent.':'Plays it again.',disabled:editBlock,run:()=>update({audio_tracks:sequence.audio_tracks.map(x=>x.id===tr.id?{...x,enabled:!x.enabled}:x)})},
         {id:'remove',icon:'remove',tone:'edit',label:'Remove placement',hint:'Takes it off the timeline; the sound stays in the library.',shortcut:keyOf('edit.lift'),disabled:editBlock,run:()=>{update({audio_tracks:sequence.audio_tracks.filter(x=>x.id!==tr.id)});setSelectedClip(null)}}],
      ]}
    }
    const job=genJobs.find(j=>j.id===t.jobId)
    const showInHistory:MenuEntry={id:'history',icon:'show-history',label:'Show in Queue',hint:'Its card, stage and details.',run:()=>{setSelectedJob(t.jobId);setPanel('history');setActivePane('viewer')}}
    const guideMe:MenuEntry={id:'guide',icon:'guide',label:'Guide me',hint:'Step-by-step from where this take is now.',run:()=>setGuide({jobId:t.jobId})}
    if(t.kind==='block'){
      const p=generations.find(x=>x.job_id===t.jobId);if(!p)return null
      const hidden=hiddenJobs.includes(p.job_id)
      return {title:p.job.label,subtitle:`Requested take · ${generationStage(p.stage)}`,sections:[[guideMe,{...showInHistory,label:'Open its card',run:()=>inspectGeneration(p)}],[{id:'hide',icon:hidden?'show':'hide',label:hidden?'Show on timeline again':'Hide from timeline',hint:'This computer only; the take and its request are kept.',run:()=>setHiddenJobs(h=>hidden?h.filter(x=>x!==p.job_id):[...h,p.job_id])}]]}
    }
    if(!job)return null
    if(t.kind==='job'&&t.jobKind==='music')return {title:job.label,subtitle:`Music cue · ${generationStage(job.status)}`,sections:[[...(job.audio_asset_id?[{id:'listen',icon:'open-audio' as const,label:'Listen',hint:'Opens the cue in the Audio tab.',run:()=>reviewGeneratedAudio(job.audio_asset_id!,'music')}]:[]),showInHistory]]}
    const server=!!job.destination
    const spot=takeSpots[job.id],spotHere=!!sequence&&spot?.sequence_id===sequence.id
    const where=spotHere&&sequence&&spot?resolveSpot(sequence.shots,spot,programFrame):null
    const placeBlock=editBlock??(!job.video_asset_id?'Not in the Browser yet: wait for it to import.':null)
    const review:MenuEntry[]=job.video_asset_id?[{id:'open',icon:'open-viewer',label:'Open in Viewer',hint:'Watch it and mark In / Out.',run:()=>reviewGeneratedVideo(job.video_asset_id!)}]:[]
    const imp:MenuEntry[]=!job.video_asset_id&&job.ready_to_import?[{id:'import',icon:'import',tone:'review',label:'Import picture and sound',hint:'Only needed if it did not import by itself. Brings picture and sound into the Browser.',disabled:busy?'Wait for the current action to finish.':null,run:()=>importTakeNow(job)}]:[]
    const audition:MenuEntry[]=job.video_asset_id&&!inSequence.has(job.video_asset_id)?[{id:'audition',icon:'audition',label:t.kind==='spot'?'Audition here':'Audition in context',hint:'Plays it between its neighbours without placing it.',run:()=>auditionTake(job)}]:[]
    const place:MenuEntry[]=server?[]:[
      ...(where&&!('error' in where)?[{id:'place-spot',icon:'place-take' as const,tone:'edit' as const,label:t.kind==='spot'?'Place it here':'Place at its spot',hint:`Picture and its sound go in ${where.note}.`,disabled:placeBlock,run:()=>placeTakeNow(job)}]:[]),
      ...(t.kind==='spot'?[]:[{id:'place-playhead',icon:'insert' as const,tone:'edit' as const,label:'Place at playhead',hint:`Picture and its sound go in at ${seqTc(programFrame)}.`,disabled:placeBlock,run:()=>{if(sequence)placeTakeNow(job,{sequence_id:sequence.id,kind:'playhead',frame:programFrame})}}]),
    ]
    const flags:MenuEntry[]=t.kind==='spot'&&sequence?[
      {id:'flag-here',icon:'flag-here',label:'Move marker to playhead',hint:'Changes where the take will go.',run:()=>{setTakeSpots(x=>({...x,[job.id]:{sequence_id:sequence.id,kind:'playhead',frame:programFrame}}));setStatus('Moved the marker to the playhead.')}},
      {id:'flag-remove',icon:'flag-remove',tone:'danger',label:'Remove marker',hint:'The take stays in the Browser.',run:()=>{removeSpot(job.id);setStatus('Removed the marker. The take stays in the Browser.')}},
    ]:[]
    return {title:job.label,subtitle:`${t.kind==='spot'?'Marker for a requested take':'Picture + sound take'} · ${generationStage(job.status!=='success'?job.status:!job.video_asset_id?'awaiting_import':'ready_to_place')}`,sections:[[...review,...imp,...audition],place,[guideMe,...(t.kind==='spot'?[showInHistory]:[])],flags]}
  }
  /** Right-click on a Browser source: a Bins section (browser-local organisation; nothing in the library changes). */
  function binMenuSection(t:CtxTarget):MenuEntry[]{
    if(t.kind!=='bin')return[]
    const key=sourceKey(t.itemKind,t.id),known=new Set(binItems.map(i=>sourceKey(i.kind,i.id)))
    const keys=(t.keys?.includes(key)?t.keys:[key]).filter(k=>known.has(k)),many=keys.length>1
    const current=userBins.bins.find(b=>b.id===userBins.member[key])
    const moves=userBins.bins.map((b):MenuEntry=>({id:`bin-${b.id}`,icon:'bin-move',label:`Move ${many?`${keys.length} sources to bin`:'to bin'} “${b.name}”`,hint:'Organises the Browser only; the library is unchanged.',disabled:keys.every(k=>userBins.member[k]===b.id)?'Already in this bin.':null,run:()=>{moveToUserBin(keys,b.id);setStatus(`Moved ${keys.length} source${many?'s':''} to the bin “${b.name}”.`)}}))
    const out:MenuEntry[]=keys.some(k=>userBins.member[k])?[{id:'bin-out',icon:'bin-out',label:many?`Move ${keys.length} sources to Unsorted`:`Remove from “${current?.name??'bin'}”`,hint:'Back to Unsorted.',run:()=>{moveToUserBin(keys,null);setStatus(`Moved ${keys.length} source${many?'s':''} to Unsorted.`)}}]:[]
    const make:MenuEntry={id:'bin-new',icon:'bin-new',label:many?`New bin with ${keys.length} sources…`:'New bin with this source…',hint:'Asks for a name. Bins are kept in this browser only.',run:()=>{const name=window.prompt('Name for the new bin')?.trim().slice(0,60);if(name){createUserBin(name,keys);setStatus(`Made the bin “${name}”.`)}}}
    return[...moves,...out,make]
  }
  // Delete / clean up clips (DeleteClips.tsx). The server refuses clips used by saved sequences; unsaved edits are checked here.
  const [delClips,setDelClips]=useState<{clips:DeletableClip[];cleanup:boolean}|null>(null)
  function localUse(id:string):string[]{
    const linked=genJobs.find(j=>j.video_asset_id===id)?.audio_asset_id
    const seqs=[...(sequence?[sequence]:[]),...[...drafts.current.values()].map(d=>d.sequence)]
    const uses=(s:Sequence)=>s.shots.some(x=>!isGap(x)&&x.asset_id===id)||s.audio_tracks.some(a=>a.asset_id===id||(!!linked&&a.asset_id===linked))
    return [...new Set(seqs.filter(s=>unsaved(s.id)&&uses(s)).map(s=>s.title))]
  }
  function openCleanup(){
    const clips=catalog.assets.filter(a=>!usedCount.get(a.id)).map(a=>({id:a.id,label:a.label,status:a.status,version:a.version}))
    if(!clips.length){setStatus('Every clip is used by a saved sequence; nothing to clean up.');return}
    setDelClips({clips,cleanup:true})
  }
  function beforeDelete(ids:string[]){
    if(source&&ids.includes(source.id)){stopTransport();setSourceId('');setViewerShot('')}
    const removed=new Set(ids.map(id=>sourceKey('video',id)))
    setBinSelection(s=>({keys:s.keys.filter(k=>!removed.has(k)),anchor:s.anchor&&removed.has(s.anchor)?null:s.anchor}))
  }
  async function afterDelete(ids:string[]){
    if(!ids.length)return
    updateUserBins(u=>{const member={...u.member};for(const id of ids)delete member[sourceKey('video',id)];return {...u,member}})
    await refreshCatalog();setQueueEpoch(e=>e+1)
    setStatus(`${ids.length} clip${ids.length===1?'':'s'} removed.`)
  }
  const ctxBase=ctxMenu?menuModel(ctxMenu.target):null
  const ctxModel=ctxBase&&ctxMenu?{...ctxBase,sections:[...ctxBase.sections,binMenuSection(ctxMenu.target)]}:ctxBase
  useEffect(()=>{if(ctxMenu&&!ctxModel)setCtxMenu(null)}) // what was right-clicked is gone (deleted, re-sorted away)
  const openCtx=(e:React.MouseEvent,target:CtxTarget)=>{e.preventDefault();e.stopPropagation();setCtxMenu({target,x:e.clientX,y:e.clientY})}
  const upperRef=useRef<HTMLDivElement>(null)
  useEffect(()=>{try{localStorage.setItem('llr.film.split.v1',String(Math.round(upperSplit)))}catch{/* optional preference */}},[upperSplit])
  function dragSplit(event:React.PointerEvent<HTMLDivElement>){
    const top=upperRef.current?.getBoundingClientRect().top??0
    event.preventDefault()
    const move=(e:PointerEvent)=>setUpperSplit(Math.max(28,Math.min(72,100*(e.clientY-top)/window.innerHeight)))
    const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up)}
    window.addEventListener('pointermove',move);window.addEventListener('pointerup',up)
  }
  /** Side-by-side pane widths: Browser in px, Viewer share of the two monitors (0.2–0.8). */
  const [cols,setCols]=useState<{browser:number,viewer:number}>(()=>{try{const v=JSON.parse(localStorage.getItem('llr.film.cols.v1')??'null');if(v&&v.browser>=140&&v.browser<=560&&v.viewer>=0.2&&v.viewer<=0.8)return v}catch{/* optional preference */}return {browser:240,viewer:0.5}})
  useEffect(()=>{try{localStorage.setItem('llr.film.cols.v1',JSON.stringify(cols))}catch{/* optional preference */}},[cols])
  const clampCols=(c:{browser:number,viewer:number})=>{const w=upperRef.current?.clientWidth??1600;return {browser:Math.round(Math.max(140,Math.min(560,w-12-560,c.browser))),viewer:Math.max(0.2,Math.min(0.8,c.viewer))}}
  function dragCols(event:React.PointerEvent<HTMLDivElement>,which:'browser'|'viewer'){
    const box=upperRef.current?.getBoundingClientRect();if(!box)return
    event.preventDefault()
    const start=cols
    const move=(e:PointerEvent)=>setCols(which==='browser'?clampCols({...start,browser:e.clientX-box.left}):clampCols({...start,viewer:(e.clientX-box.left-start.browser-6)/Math.max(1,box.width-start.browser-12)}))
    const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up)}
    window.addEventListener('pointermove',move);window.addEventListener('pointerup',up)
  }
  function colKeys(e:React.KeyboardEvent,which:'browser'|'viewer'){
    if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return
    e.preventDefault();e.stopPropagation()
    const d=e.key==='ArrowLeft'?-1:1
    setCols(c=>clampCols(which==='browser'?{...c,browser:c.browser+d*16}:{...c,viewer:c.viewer+d*0.02}))
  }
  const viewerTransport=activePane==='viewer'||activePane==='browser'
  const shuttleLabel=shuttle===0?'':`${shuttle<0?'◀◀':'▶▶'} ${Math.abs(shuttle)}×${shuttle!==1?' · muted':''}`
  const tickStep=[1,2,4,6,12,24,48,120,240,480,720,1440,2880,7200].find(step=>timelineSpan/step<=8*zoom/100)??14400
  const ticks=Array.from({length:Math.floor(timelineSpan/tickStep)+1},(_,i)=>i*tickStep)
  const sourceLast=Math.max(0,(source?.frame_count??1)-1)
  const markedOut=marks.out??sourceLast
  const boundIndex=boundShot&&sequence?sequence.shots.findIndex(shot=>shot.id===boundShot.id):-1
  // Unsaved sequence edits no longer block navigation (they are parked as drafts). Story and shot-plan edits still do: those panels keep no drafts.
  const navBlocked=busy||storyDirty||planDirty||!!rehearsal
  const unsaved=(id:string)=>id===sequence?.id?dirty:draftIds.includes(id)
  const unsavedCount=draftIds.length+(dirty?1:0)
  const renderState=!sequence||!total?'empty':dirty?'stale':exporting?'rendering':sequence.export?.status==='complete'&&(!sequence.export.report?.manifest_hash||sequence.export.report.manifest_hash===sequence.manifest_hash)?'rendered':'stale'
  const renderTitle={empty:'Nothing to render',stale:dirty?'Needs rendering: save first (Ctrl+S), then Render (Alt+R)':'Needs rendering: Render (Alt+R)',rendering:'Rendering…',rendered:'Rendered: Canvas plays the render'}[renderState]
  const [trackSize,setTrackSize]=useState(1)
  function applyTimecode(target:'source'|'program',text:string){
    const next=target==='source'?parseTimecodeEntry(text,sourceFrame):programEntry(text)
    if(next===null){setError(`“${text}” is not a timecode. Type digits such as 1419 (14 s 19 f), or +24 / -24 to move by frames.`);return}
    stopTransport()
    if(target==='source'){const frame=Math.max(0,Math.min(sourceLast,next));if(sourceVideo.current)sourceVideo.current.currentTime=frame/24;setSourceFrame(frame)}else seekProgram(next)
  }
  /** Sequence timecode starts at 01:00:00:00 (broadcast convention, Boden 2026-11-14); stored frames stay 0-based. */
  function seqTc(frame:number){return timecode(frame+SEQ_START,24)}
  /** Typed sequence timecode: 01:00:14:19 and plain 1419 both mean 14 s 19 f into the sequence; +/- stay relative. */
  function programEntry(text:string){const relative=/^\s*[+-]/.test(text);const value=parseTimecodeEntry(text,programFrame);if(value===null||relative)return value;return value>=SEQ_START?value-SEQ_START:value}
  /** One transport button: runs the same command as its key, aimed at that monitor. */
  function stripButton(pane:'viewer'|'canvas',command:string,label:string,title:string,disabled=false){return <button key={command} type="button" className="fcp-strip-btn" data-command={command} disabled={disabled||!!rehearsal} title={title} aria-label={title} onMouseDown={e=>e.preventDefault()} onClick={()=>{setActivePane(pane);execRef.current?.(command,null,pane)}}>{label}</button>}
  const volumeControl=<label className="fcp-volume" title={`Monitor volume ${Math.round(volume*100)}% (what you hear only; the saved mix and export are unchanged)`}><span aria-hidden="true">{volume===0?'🔇':'🔊'}</span><input type="range" aria-label="Monitor volume" min={0} max={1} step={0.05} value={volume} onChange={e=>setVolume(Number(e.target.value))}/></label>
  function timecodeField(target:'source'|'program',shown:string,title:string){
    if(tcEntry?.target!==target)return <span className="ed-timecode" title={`${title} — type a timecode to jump (e.g. 1419, +24, -1.)`}>{shown}</span>
    return <input className="ed-timecode ed-timecode-entry" aria-label="Timecode: type, then Enter. Esc cancels." value={tcEntry.text}
      ref={element=>{if(element&&document.activeElement!==element){element.focus();element.setSelectionRange(element.value.length,element.value.length)}}}
      onChange={e=>setTcEntry({target,text:e.target.value.replace(/[^0-9+\-.:;]/g,'')})} onBlur={()=>setTcEntry(null)}
      onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();setTcEntry(null)}if(e.key==='Enter'){e.preventDefault();applyTimecode(target,tcEntry.text);setTcEntry(null)}}}/>
  }
  // Generate › Selected take (ported from Codex's native viewer, 2026-11-18): the selected V1 clip, the Viewer's
  // timeline shot, or the Viewer source; an editor-owned job can be rerolled as a separate take, an Astrid
  // local-director shot through the shot-control service, anything else shows its recorded receipt.
  const sameSourceShots=genView==='take'&&source?sequence?.shots.filter((s):s is VideoShot=>!isGap(s)&&s.asset_id===source.id):undefined
  const genUsesClip=genFocus==='clip'&&!!(selectedShot||selectedAudio)
  const genShot:VideoShot|undefined=genUsesClip?(selectedShot&&!isGap(selectedShot)?selectedShot:undefined):boundShot??(sameSourceShots?.length===1?sameSourceShots[0]:undefined)
  const genAsset=genShot?catalog.assets.find(x=>x.id===genShot.asset_id):genUsesClip?undefined:source
  const ownedGen=genAsset?genJobs.find(job=>job.video_asset_id===genAsset.id):undefined
  const showSelectedTake=panel==='generate'&&genView==='take'&&!!genAsset
  // Clip prompt → New generation brief. The clip is the one open in the Viewer (double-click on V1 or in the Browser).
  // An empty or previously auto-filled brief is filled in; anything the user typed is only replaced on request.
  const promptFor=(a?:VideoAsset)=>a?promptOf(a.provenance as Record<string,unknown>|undefined,genJobs.find(j=>j.video_asset_id===a.id)?.metadata as Record<string,unknown>|undefined):undefined
  const sourcePrompt=promptFor(source)
  const autoBrief=useRef<{brief:string;label:string}|null>(null)
  const genSnapRef=useRef(genSnap);genSnapRef.current=genSnap
  function carryPrompt(text:string,asset?:VideoAsset,ask=true){
    const snap=genSnapRef.current
    if(snap?.busy){setStatus('The New generation form is busy; try again when it finishes.');return}
    if(ask&&snap?.locked&&!window.confirm(`The New generation form is set up for: ${snap.locked}\n\nClear that setup and use this prompt instead?`))return
    if(ask&&snap?.brief.trim()&&snap.brief.trim()!==text&&snap.brief!==autoBrief.current?.brief&&!window.confirm('Replace the brief already in the New generation form with this prompt?'))return
    if(snap?.locked)genControl.current?.clearSetup()
    const label=asset?`${asset.label} - new take`.slice(0,100):snap?.label??''
    genControl.current?.setBrief(text)
    if(asset&&(!snap?.label.trim()||snap.label===autoBrief.current?.label||ask))genControl.current?.setLabel(label)
    autoBrief.current={brief:text,label}
    setGenMode('take');setGenView('new')
  }
  useEffect(()=>{
    if(panel!=='generate'||genMode!=='take'||genView==='take'||!source||!sourcePrompt)return
    const snap=genSnapRef.current
    if(!snap||snap.busy||snap.locked)return
    if(!snap.brief.trim()||snap.brief===autoBrief.current?.brief)carryPrompt(sourcePrompt,source,false)
  },[panel,genMode,source?.id,sourcePrompt,!!genSnap])// eslint-disable-line react-hooks/exhaustive-deps
  function auditionShotTake(take:ShotTake){
    if(!sequence||!genShot)return
    let cursor=0
    const at=sequence.shots.slice(0,sequence.shots.findIndex(s=>s.id===genShot.id)).reduce((n,s)=>n+s.duration_frames,0)
    const end=at+genShot.duration_frames,from=Math.max(0,at-48),to=Math.min(total,end+48)
    const video:AuditionVideo[]=[],audio:AuditionAudio[]=[]
    for(const s of sequence.shots){
      const start=cursor;cursor+=s.duration_frames
      const a=Math.max(start,from),b=Math.min(cursor,to)
      if(a<b)video.push({start:a-from,frames:b-a,assetId:isGap(s)?null:s.id===genShot.id?'astrid-preview:'+take.id:s.asset_id,sourceIn:isGap(s)?0:s.source_in_frame+a-start,part:s.id===genShot.id?'take':a<at?'outgoing':'incoming'})
    }
    for(const t of sequence.audio_tracks){
      const a=Math.max(t.start_frame,from),b=Math.min(t.start_frame+t.duration_frames,to)
      if(t.enabled&&a<b)audio.push({start:a-from,frames:b-a,assetId:t.asset_id,sourceIn:t.source_in_frame+a-t.start_frame,gainDb:t.gain_db,role:t.role})
    }
    stopTransport();previewAudio.stop()
    setAudition({title:'Alternate take · seed '+take.seed,note:'Your existing trim, up to two seconds of neighbouring picture on either side, and the existing audio. Not placed in the timeline.',win:{ok:true,video,audio,length:to-from,takeStart:at-from,takeFrames:end-at}})
  }
  return <main tabIndex={-1} className="editor-shell film-editor fcp-film" style={{'--fcp-upper':`${upperSplit}dvh`} as React.CSSProperties} onPlayCapture={pauseForAudition}>
    <header className="ed-titlebar"><strong>Last Light Radio · Generative NLE</strong><FilmMenuBar keymap={keymap} disabled={!!rehearsal} onCommand={id=>{execRef.current?.(id,null,null)}} onAction={menuAction}/><span>{project?`${project.title} — `:''}{sequence?.title??'Film project'}</span><button disabled={unsavedCount>0||busy||storyDirty||planDirty||!!rehearsal} title={unsavedCount?`Save or discard unsaved edits first (${unsavedCount} sequence${unsavedCount===1?'':'s'}): leaving the Film editor would lose them`:undefined} onClick={onSceneAnimation}>Scene animation tools</button><button disabled={!!rehearsal} title="Show and change every shortcut (Alt+H)" onClick={()=>setLayoutOpen(true)}>Keyboard…</button></header>
    <nav inert={!!rehearsal} className="ed-menubar film-toolbar">{sequence?<>
      <input aria-label="Sequence name" value={sequence.title} disabled={busy||exporting} onChange={e=>update({title:e.target.value})}/>
      <span className="fcp-seq-meta">{(total/24).toFixed(2)}s · 24fps · {sequence.width}×{sequence.height} · revision {saved?.revision}</span>
      <span className={`fcp-chip ${dirty?'fcp-chip-warn':'fcp-chip-ok'}`}>{dirty?'● Unsaved edits':'✓ Saved'}</span>
      <span className="ed-menu-spacer"/>
      <button disabled={!history.length||busy||exporting} onClick={()=>{const previous=history.at(-1)!;setFuture(items=>[...items,sequence]);setHistory(items=>items.slice(0,-1));setSequence(previous)}}>Undo</button>
      <button disabled={!future.length||busy||exporting} onClick={()=>{const next=future.at(-1)!;setHistory(items=>[...items,sequence]);setFuture(items=>items.slice(0,-1));setSequence(next)}}>Redo</button>
      <i className="fcp-sep" aria-hidden="true"/>
      <button className={dirty?'ed-primary':''} disabled={busy||exporting||!dirty||!total} onClick={()=>void save()}>Save sequence</button>
      {draftIds.length?<button title="Save every sequence with unsaved edits (Ctrl+Alt+S)" disabled={busy} onClick={()=>void saveAll()}>Save all ({unsavedCount})</button>:null}
      <button disabled={busy||exporting||!dirty} onClick={discard}>Discard edits</button>
      <i className="fcp-sep" aria-hidden="true"/>
      <button className="fcp-export-button" disabled={busy||exporting||!total} title={dirty?'Render (Alt+R): saves your edits first, then builds the playback render and the exported file':'Render (Alt+R): builds the playback render and the exported file'} onClick={render}>{sequence.shots.length?'Export film':'Export WAV'}</button>
    </>:<span>Choose or create a project and named sequence in the Browser</span>}</nav>
    <div ref={upperRef} className="ed-upper fcp-film-upper" style={{gridTemplateColumns:`${cols.browser}px 6px minmax(280px,${cols.viewer}fr) 6px minmax(280px,${1-cols.viewer}fr)`}}>
      <aside className={`ed-pane fcp-browser ${activePane==='browser'?'active-pane':''}`} onPointerDown={()=>setActivePane('browser')}>
        <h2 className="ed-pane-title">Browser <span>Projects · sequences · sources</span></h2><div className="ed-browser-body film-projects">
        <label className="fcp-browser-project">Project<select value={projectId} disabled={navBlocked} onChange={e=>{ const p=catalog.projects.find(p=>p.id===e.target.value);setProjectId(e.target.value);if(p?.sequences.length) void open(p.sequences[0].id);else {stashCurrent();resetForSequence();setSequence(null);setSaved(null);currentId.current=''} }}><option value="">Choose a project</option>{catalog.projects.map(p=><option value={p.id} key={p.id}>{p.title}</option>)}</select></label>
        <details><summary>New project…</summary><form onSubmit={e=>{e.preventDefault(); void action(async()=>{ const p=await api<Project>('film/projects',{title:projectName}); await refreshCatalog(); setProjectId(p.id);setProjectName('');stashCurrent();resetForSequence();setSequence(null);setSaved(null);currentId.current='' })}}>
          <label>New project name<input required maxLength={100} value={projectName} disabled={navBlocked} onChange={e=>setProjectName(e.target.value)} /></label><button disabled={navBlocked||!projectName.trim()}>Create project</button>
        </form></details>
        <FoldHead open={seqOpen} onToggle={toggleSeq} label="Sequences" kind="sequence"><small>{project?.sequences.length??0}</small></FoldHead>{seqOpen?<>
        <div className="fcp-bin fcp-seq-bin" onKeyDown={e=>{
          const keys=project?.sequences.map(i=>`sequence:${i.id}`)??[]
          if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&e.key.toLowerCase()==='a'){e.preventDefault();e.stopPropagation();setBinSelection({keys,anchor:keys[0]??null})}
          else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setBinSelection(emptyBrowserSelection)}
        }}>{project?.sequences.map(item=><button className={sequence?.id===item.id?'selected':''} aria-current={sequence?.id===item.id?'true':undefined} data-unsaved={unsaved(item.id)||undefined} disabled={navBlocked} key={item.id} data-picked={binSelection.keys.includes(`sequence:${item.id}`)||undefined} aria-pressed={binSelection.keys.includes(`sequence:${item.id}`)} title={`${item.title} — Ctrl-click to toggle, Shift-click for a range; double-click or Enter to open in the Timeline`} onClick={e=>setBinSelection(s=>selectBrowserItem(s,`sequence:${item.id}`,project?.sequences.map(i=>`sequence:${i.id}`)??[],e))} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();e.stopPropagation();void open(item.id)}}} onDoubleClick={e=>{if(!e.ctrlKey&&!e.metaKey&&!e.shiftKey)void open(item.id)}}><i aria-hidden="true" className="fcp-seq-icon"/><span>{item.title}</span><small className="fcp-seq-count">{((item as unknown as {shots?:Shot[]}).shots??[]).filter(s=>!isGap(s)).length} shots</small></button>)}{project&&!project.sequences.length?<p>No sequences in this project yet.</p>:null}</div>
        <details><summary>New sequence…</summary><form onSubmit={e=>{e.preventDefault();void action(async()=>{const next=await api<Sequence>(`film/projects/${projectId}/sequences`,{title:sequenceName});await refreshCatalog();stashCurrent();resetForSequence();currentId.current=next.id;setSequence(next);setSaved(next);setSequenceName('');setHistory([]);setFuture([]);setShotId('');try{localStorage.setItem('llr.film.sequence.v1',next.id)}catch{/* optional preference */}})}}>
          <label>New sequence name<input required maxLength={100} value={sequenceName} disabled={navBlocked||!projectId} onChange={e=>setSequenceName(e.target.value)} /></label><button disabled={navBlocked||!projectId||!sequenceName.trim()}>Create sequence</button>
        </form></details></>:null}
        <FoldHead open={srcOpen} onToggle={toggleSrc} label="Sources"><small>{binItems.length} · shared library</small></FoldHead>{srcOpen?<>
        <details><summary>Import / generated sources</summary><p>Scene animation builds a single animated environment. Export it there, then import that finished scene as a shot here.</p><h2>Video sources <small>Shared clip library</small></h2><div className="film-imports"><label>Import MP4<input type="file" accept=".mp4,video/mp4" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;void action(async()=>{if(file.size>20*1024*1024)throw new Error('Choose an MP4 under 20 MiB for this milestone.');let provenance={};if(recipe.trim()){provenance=JSON.parse(recipe);if(!provenance||Array.isArray(provenance)||typeof provenance!=='object')throw new Error('Recipe must be a JSON object.')}const result=await api<VideoAsset>('film/assets/import',{filename:file.name,video_base64:await encodeFile(file),label:file.name,provenance});await refreshCatalog();setSourceId(result.id);setPanel('video')})}}/></label><label>Completed scene animation<select value={fromScene} onChange={e=>setFromScene(e.target.value)}><option value="">Choose an exported scene</option>{(data.sequences??[]).filter(s=>s.media_url).map(s=><option value={s.id} key={s.id}>{s.title}</option>)}</select></label><button disabled={busy||!fromScene} onClick={()=>void action(async()=>{const asset=await api<VideoAsset>('film/assets/from-sequence',{sequence_id:fromScene,label:'Scene animation export'});await refreshCatalog();setSourceId(asset.id);setPanel('video')})}>Import scene as source</button></div><div className="film-imports"><label>Completed H3 take<select value={fromTake} onChange={e=>setFromTake(e.target.value)}><option value="">Choose a registered completed take</option>{takes.flatMap(t=>t.outputs.map(o=><option key={`${t.candidate_id}:${o.output_index}`} value={`${t.candidate_id}:${o.output_index}`}>{t.label} · output {o.output_index+1}</option>))}</select></label><button disabled={busy} onClick={()=>void refreshTakes()}>Refresh completed takes</button><button disabled={busy||!fromTake} onClick={()=>void action(async()=>{const split=fromTake.lastIndexOf(':');const asset=await api<VideoAsset>('film/assets/from-take',{candidate_id:fromTake.slice(0,split),output_index:Number(fromTake.slice(split+1))});await refreshCatalog();setSourceId(asset.id);setPanel('video');setStatus('Imported generated take with provenance. Drag it onto the timeline, or Insert it from the Viewer.')})}>Import generated take</button><button disabled={navBlocked} onClick={onGenerate}>Reference-motion workspace</button></div><p>Uses this library's registered completed MP4 takes, preserving generation receipts. Importing does not run a model. This reference-motion route is video-only. For text-to-video with generated sound, use Generate a film take above. {!(data.motion_profiles??[]).length?'No motion recipe is configured here: open Reference-motion workspace to set up a reference scene and recipe first.':''}</p>{takeError?<p role="alert">Completed takes: {takeError}</p>:null}<details><summary>Import recipe / provenance (optional JSON)</summary><textarea aria-label="Video provenance JSON" value={recipe} onChange={e=>setRecipe(e.target.value)} placeholder='{"model":"H3","seed":123}'/></details></details>
        <FilmBin items={binItems} usedCount={usedCount} inSequence={inSequence} openKey={panel==='still'?sourceKey('still',stillId):panel==='audio'?sourceKey('audio',audioSourceId):sourceKey('video',sourceId)} selection={binSelection} busy={busy} onSelection={setBinSelection} onOpen={openBinItem} onMenu={(item,x,y,keys)=>setCtxMenu({target:{kind:'bin',id:item.id,itemKind:item.kind,keys},x,y})}/></>:null}</div>
      </aside>
      <div role="separator" tabIndex={0} aria-orientation="vertical" aria-label="Resize Browser and monitors" aria-valuemin={140} aria-valuemax={560} aria-valuenow={cols.browser} title="Drag to resize · double-click to reset" className="fcp-col-divider" onPointerDown={e=>dragCols(e,'browser')} onDoubleClick={()=>setCols(c=>clampCols({...c,browser:240}))} onKeyDown={e=>colKeys(e,'browser')}/>
      <section className={`ed-pane fcp-viewer ${activePane==='viewer'?'active-pane':''}`} onPointerDown={()=>setActivePane('viewer')}>
        <h2 className="ed-pane-title">Viewer <span>{panel==='still'?(stills.find(x=>x.id===stillId)?.label??'Still'):boundShot&&sequence?`Shot ${boundIndex+1} from ${sequence.title} · ${source?.label??''}`:source?.label??'Source / custom tools'}</span></h2>
        <div className="ed-tabs">{(['video','audio','generate','history','fmv','plan'] as const).map(tab=><button aria-pressed={panel===tab} key={tab} onClick={()=>{if(tab==='generate')setGenView('new');setPanel(tab)}}>{({video:'Video',audio:'Audio',generate:'Generate',history:'Queue',fmv:'FMV',plan:'Shot plan'})[tab]}{tab==='history'&&pending.some(p=>p.stage!=='placed')?<i aria-hidden="true" className="fcp-dot fcp-dot-info" title="Takes waiting for you"/>:null}{(tab==='fmv'&&storyDirty)||(tab==='plan'&&planDirty)?<i aria-hidden="true" className="fcp-dot" title="Unsaved edits in this tool"/>:null}</button>)}</div>
        <div className="ed-viewer-content">
          <div hidden={panel!=='video'} className="fcp-source">
            <div className="fcp-monitor-head"><span className={`fcp-monitor-label ${boundShot?'fcp-monitor-bound':''}`} title={boundShot?'Opened from the Timeline: Mark In / Mark Out trim this shot in the sequence':'Opened from the Browser: marks choose the range for the next append'}>{boundShot?`▦ Timeline shot ${boundIndex+1}`:'Source'}</span>{source?<span className="fcp-source-chip" title={`${(source.frame_count/24).toFixed(2)}s · ${source.width}×${source.height}${linkedAudio?' · with production sound':''}`}>{linkedAudio?'♪ ':''}{source.width}×{source.height}</span>:null}{source?<span className="fcp-monitor-dur" title="Marked source duration (In to Out, inclusive)">{timecode(Math.max(0,markedOut-sourceMarks.in+1),24)}</span>:null}{timecodeField('source',timecode(sourceFrame,24),'Source timecode')}</div>
            <div className="fcp-stage">{source ? <video ref={sourceVideo} key={source.id} onClick={sourceTransport} onPause={()=>{sourceStop.current=null}}onLoadedMetadata={e=>{if(pendingSourceFrame.current!==null){e.currentTarget.currentTime=pendingSourceFrame.current/24;setSourceFrame(pendingSourceFrame.current);pendingSourceFrame.current=null}}} onTimeUpdate={e=>setSourceFrame(Math.min((source?.frame_count??1)-1,Math.round(e.currentTarget.currentTime*24)))} src={source.media_url} preload="metadata"/>:<div className="film-empty">Import or choose a source take in the Browser.</div>}{shuttleLabel&&viewerTransport?<span className="ed-shuttle fcp-shuttle-osd" aria-live="polite">{shuttleLabel}</span>:null}</div>
            <div className={`fcp-scrub ${boundShot?'fcp-scrub-bound':''}`}>{source?<i aria-hidden="true" className="fcp-scrub-range" style={{'--in':marks.in/Math.max(1,sourceLast),'--len':(markedOut-marks.in)/Math.max(1,sourceLast)} as React.CSSProperties}/>:null}<input aria-label="Viewer source playhead" type="range" min={0} max={Math.max(0,(source?.frame_count??1)-1)} value={Math.min(sourceFrame,Math.max(0,(source?.frame_count??1)-1))} onChange={e=>{stopTransport();if(sourceVideo.current)sourceVideo.current.currentTime=Number(e.target.value)/24;setSourceFrame(Number(e.target.value))}}/></div>
            <div className="ed-transport fcp-transport" role="toolbar" aria-label="Viewer transport">{stripButton('viewer','nav.in','⇤','Go to In (Shift+I)')}{stripButton('viewer','play.inToOut','▷|','Play In to Out (Shift+\)')}<button title="Mark In (I)" disabled={!!boundShot&&(busy||exporting)} onClick={()=>markIn(sourceFrame)}>Mark In</button><button className="fcp-play" title="Play / pause source (Space)" onClick={sourceTransport}>Play / pause</button><button title="Mark Out (O)" disabled={!!boundShot&&(busy||exporting)} onClick={()=>markOut(sourceFrame)}>Mark Out</button>{stripButton('viewer','play.around','↔','Play around the current frame (\)')}{stripButton('viewer','nav.out','⇥','Go to Out (Shift+O)')}{volumeControl}</div>
            <div className="fcp-marks-row"><p className="fcp-marks">In {timecode(marks.in,24)} · Out {timecode(marks.out??Math.max(0,(source?.frame_count??1)-1),24)}. {boundShot?`Mark In / Mark Out trim shot ${boundIndex+1} in the sequence (unsaved until you Save; later shots shift).`:'Append uses this source range.'}</p>{source?<button className="ed-primary" disabled={busy||!!exporting} title="Append the marked source range to the end of V1" onClick={addShot}>Append shot</button>:null}</div>
            {source&&!boundShot&&(linkedAudioId||source.provenance.generation_metadata) ? <div className="fcp-review"><div className="film-actions">{linkedAudioId?(()=>{const job=genJobs.find(j=>j.video_asset_id===source.id);return job?<button title="Play it between its neighbours at its spot (or the playhead) without placing it" disabled={busy} onClick={()=>auditionTake(job)}>Audition in context</button>:null})():null}</div>{source.provenance.generation_metadata?<JobMetadata job={{metadata:source.provenance.generation_metadata as GenerationJob['metadata']}}/>:null}</div>:null}
          </div>
          {panel==='still'?(()=>{const s=stills.find(x=>x.id===stillId);return <div className="fcp-still">{s?<><img src={s.media_url} alt={s.label}/><p><strong>{s.label}</strong> · {s.width}×{s.height} · {(s as unknown as {usage?:string}).usage??'reference still'}</p><p>Use it as a first or last frame in the Generate tab.</p></>:<p>Choose a still in the Browser.</p>}<button onClick={()=>setPanel('video')}>Back to Video</button></div>})():null}
          {panel==='audio'?<AudioWorkspace initialRole={audioSourceId?audioSourceRole:undefined} initialAssetId={audioSourceId} mixedPreview noReview config={audioConfig} frame={programFrame} busy={busy||!!exporting} onChange={next=>update({audio_tracks:next.audio_tracks??[]})} onApply={()=>void save()}/>:null}
          {panel==='generate'?<div className="generate-mode gen-workspace" aria-label="Generation workspace"><button type="button" aria-pressed={!showSelectedTake} onClick={()=>setGenView('new')}>New generation</button><button type="button" disabled={!genAsset} title={genAsset?`Receipt and reroll for ${genAsset.label}`:'Select a clip on V1 or open a take in the Viewer'} aria-pressed={showSelectedTake} onClick={()=>setGenView('take')}>Selected take</button></div>:null}
          {showSelectedTake&&genAsset?<section className="gen-selected-take" key={(genShot?.id??'source')+':'+genAsset.id}><h3>{genAsset.label}</h3>{genShot?<p>Frames {genShot.source_in_frame}–{genShot.source_in_frame+genShot.duration_frames} (Out exclusive)</p>:<p>Viewer source</p>}<ClipPrompt key={genAsset.id} prompt={promptFor(genAsset)} onUse={text=>carryPrompt(text,genAsset)}/>{ownedGen?<OwnedTake job={ownedGen} onQueued={()=>setQueueEpoch(e=>e+1)} onHistory={()=>{setSelectedJob(ownedGen.id);setPanel('history')}}/>:<ReadOnlyReceipt hidePrompt provenance={genAsset.provenance} missing={<ShotGeneration assetId={genAsset.id} sourceIn={genShot?.source_in_frame} length={genShot?.duration_frames} dirty={!genShot||dirty||busy||!!exporting} onAudition={genShot?auditionShotTake:undefined}/>}/>}</section>:null}
          {panel==='generate'&&!showSelectedTake?<div className="generate-mode" role="radiogroup" aria-label="What to generate">{(['take','music'] as const).map(m=><button key={m} type="button" role="radio" aria-checked={genMode===m} onClick={()=>setGenMode(m)}>{m==='take'?'Picture + sound':'Music cue'}</button>)}</div>:null}
          {panel==='generate'&&!showSelectedTake&&genMode==='take'&&source&&sourcePrompt&&genSnap&&genSnap.brief.trim()!==sourcePrompt.trim()&&genSnap.brief!==autoBrief.current?.brief?<div className="gen-clip-offer"><span>Viewer clip <strong>{source.label}</strong> has a recorded prompt.</span><button onClick={()=>carryPrompt(sourcePrompt,source)}>Use clip prompt</button></div>:null}<div hidden={panel!=='generate'||showSelectedTake||genMode!=='take'}><FilmGeneration control={genControl} onSnapshot={setGenSnap} onSubmitted={id=>setGuide(g=>g&&!g.jobId?{jobId:id}:g)} selectedClip={selectedShot&&!isGap(selectedShot)?{id:selectedShot.id,label:catalog.assets.find(a=>a.id===selectedShot.asset_id)?.label??'Shot'}:null} onRequested={(id,spot)=>{if(spot)setTakeSpots(s=>({...s,[id]:spot}))}} onOpenHistory={id=>{if(id)setSelectedJob(id);setPanel('history')}} mediaFor={id=>catalog.assets.find(a=>a.id===id)?.media_url} assetStatus={id=>catalog.assets.find(a=>a.id===id)?.status} onAudition={auditionTake} auditionBlocked={!sequence?'Open a sequence to audition a take in context':null} onLibraryChanged={refreshCatalog} epoch={queueEpoch} active={panel==='generate'&&genMode==='take'&&!showSelectedTake} onGuide={id=>setGuide({jobId:id})} onOpenPlan={()=>{setPanel('plan');setQueueEpoch(e=>e+1)}} preparedPlan={preparedPlan} preparedContinuation={preparedContinuation} referenceSource={source?{id:source.id,label:source.label,frame:sourceFrame,frame_count:source.frame_count}:null} target={generationTarget} timelineDirty={dirty||busy||!!exporting||!!rehearsal} onJobsChanged={()=>setQueueEpoch(e=>e+1)} frame={programFrame} placements={generations} selectedJob={selectedJob} onPlaced={afterGeneratedPlacement} onReviewVideo={reviewGeneratedVideo} onReviewAudio={id=>reviewGeneratedAudio(id,'production')} onImported={async id=>{await refreshCatalog();setSourceId(id);setPanel('video')}}/></div>
          <div hidden={panel!=='history'}><FilmHistory onMenu={(job,kind,x,y)=>setCtxMenu({target:{kind:'job',jobId:job.id,jobKind:kind},x,y})}isHere={job=>!!sequence&&takeSpots[job.id]?.sequence_id===sequence.id} isPlaced={job=>!!job.video_asset_id&&(usedCount.get(job.video_asset_id)??0)>0} placer={job=>{if(!sequence||!job.video_asset_id)return null;if(dirty&&inSequence.has(job.video_asset_id)&&!saved?.shots.some(s=>!isGap(s)&&s.asset_id===job.video_asset_id))return <div className="take-placer"><p className="generation-next">Placed in this sequence (unsaved). Save (Ctrl+S) to keep it, or Ctrl+Z to undo.</p></div>;const st=takeState(job);const w=st.spot?resolveSpot(sequence.shots,st.spot,programFrame):null;const other=!!st.spot&&st.spot.sequence_id!==sequence.id;const sel=selectedShot&&!isGap(selectedShot)?selectedShot:null
          return <div className="take-placer"><p className="generation-next">{other?'It was meant for another sequence; place it here or open that sequence.':'In the Browser. Place it on the timeline, or drag it there.'}{st.spot&&!other&&w?(' Spot: '+('error' in w?w.error:w.note)+'.'):''}</p>
            <div className="film-actions"><button title="Play it between its neighbours at its spot (or the playhead) without placing it" onClick={()=>auditionTake(job)}>Audition here</button>{!st.approved?null:<>
              {st.spot&&!other&&w&&!('error' in w)?<button className="ed-primary" disabled={busy||!!exporting} onClick={()=>placeTakeNow(job)}>Place at its spot</button>:null}
              <button disabled={busy||!!exporting} onClick={()=>placeTakeNow(job,{sequence_id:sequence.id,kind:'playhead',frame:programFrame})}>Place at playhead ({seqTc(programFrame)})</button>
              <button disabled={busy||!!exporting||!sel} title={sel?undefined:'Select a clip on V1 first'} onClick={()=>sel&&placeTakeNow(job,{sequence_id:sequence.id,kind:'after',clipId:sel.id})}>Place after selected clip</button>
              <button disabled={busy||!!exporting||!sel} title={sel?undefined:'Select a clip on V1 first'} onClick={()=>sel&&placeTakeNow(job,{sequence_id:sequence.id,kind:'before',clipId:sel.id})}>Place before selected clip</button>
              <button disabled={busy||!!exporting} onClick={()=>placeTakeNow(job,{sequence_id:sequence.id,kind:'end'})}>Place at end</button>
              <label className="take-policy">Existing audio<select value={placePolicy} onChange={e=>setPlacePolicy(e.target.value as 'preserve'|'ripple')}><option value="ripple">Moves with the picture</option><option value="preserve">Keeps its timing</option></select></label></>}
              {st.spot?<button onClick={()=>removeSpot(job.id)}>Remove marker</button>:null}</div></div>}} target={generationTarget}timelineDirty={dirty||busy||!!exporting||!!rehearsal} placements={generations} selectedJob={selectedJob} epoch={queueEpoch} onPlaced={afterGeneratedPlacement} onReviewVideo={reviewGeneratedVideo} onReviewAudio={reviewGeneratedAudio} onImported={async(kind,id)=>{if(kind==='take'){await refreshCatalog();setSourceId(id);setPanel('video')}else{setAudioSourceId(id);setAudioSourceRole('music');setPanel('audio');setStatus('Music imported. Listen, then place it on A2.')}}} onJobsChanged={()=>setQueueEpoch(e=>e+1)} onGuide={id=>setGuide({jobId:id})} onPlan={()=>{setPanel('plan');setQueueEpoch(e=>e+1)}}/></div>
          <div hidden={panel!=='generate'||showSelectedTake||genMode!=='music'}><MusicGeneration onOpenHistory={()=>setPanel('history')} target={generationTarget} timelineDirty={dirty||busy||!!exporting||!!rehearsal} onJobsChanged={()=>setQueueEpoch(e=>e+1)} frame={programFrame} placements={generations} selectedJob={selectedJob} onPlaced={afterGeneratedPlacement} onReviewVideo={reviewGeneratedVideo} onReviewAudio={id=>reviewGeneratedAudio(id,'music')} onImported={async id=>{setAudioSourceId(id);setAudioSourceRole('music');setPanel('audio');setStatus('Music imported. Listen, then place it on A2.')}}/></div>
          <div hidden={panel!=='plan'}><FilmShotPlan projectId={projectId} sequenceId={sequence?.id??''} revision={saved?.revision??0} duration={total} request={planRequest} assets={catalog.assets} blocked={dirty||busy||!!exporting||!!rehearsal} onDirty={setPlanDirty} onGenerate={p=>{setPreparedPlan(p);openGenerate('take')}} onReview={reviewGeneratedVideo} onPlaced={afterGeneratedPlacement} epoch={queueEpoch}/></div>
          <div hidden={panel!=='fmv'}><FilmStory projectId={projectId} sequences={project?.sequences??[]} onDirty={setStoryDirty} onRehearse={manifest=>{if(dirty){setError('Save or discard sequence edits before rehearsal.');return}stopTransport();setRehearsal(manifest);setActivePane('canvas')}}/></div>
        </div>
      </section>
      <div role="separator" tabIndex={0} aria-orientation="vertical" aria-label="Resize Viewer and Canvas" aria-valuemin={20} aria-valuemax={80} aria-valuenow={Math.round(cols.viewer*100)} title="Drag to resize · double-click to reset" className="fcp-col-divider" onPointerDown={e=>dragCols(e,'viewer')} onDoubleClick={()=>setCols(c=>({...c,viewer:0.5}))} onKeyDown={e=>colKeys(e,'viewer')}/>
      <section className={`ed-pane fcp-canvas ${activePane==='canvas'?'active-pane':''}`} onPointerDown={()=>setActivePane('canvas')}>
        <h2 className="ed-pane-title">Canvas <span>{sequence?.title??'No sequence selected'}</span></h2>
        {rehearsal?<StoryRehearsal manifest={rehearsal} onExit={()=>{if(activeShot)pendingSeek.current=(activeShot.source_in_frame+Math.min(activeShot.duration_frames-1,Math.max(0,programFrame-shotStart)))/24;setRehearsal(null);setActivePane('canvas')}}/>:sequence?<div className="fcp-program">
          <div className="fcp-monitor-head"><span className={`fcp-mode ${renderedPreview?'fcp-mode-rendered':'fcp-mode-live'}`} title={renderedPreview?'Rendered playback: the completed export of this saved revision. Continuous picture and mixed sound, frame-exact cuts. Editing switches back to the live preview until you save and export again.':'Live edit preview: sources play shot by shot, so cuts may buffer. Save and export for seamless rendered playback with mixed sound. Source video sound is not automatically mixed.'}>{renderedPreview?'■ Rendered playback':'◇ Live edit preview'}</span>{sequence.export?.status==='complete'&&sequence.export.media_url?<a className="fcp-export-link" href={sequence.export.media_url} target="_blank" rel="noreferrer" title={sequence.shots.length?'Open exported film':'Open exported WAV'} aria-label={sequence.shots.length?'Open exported film':'Open exported WAV'}>↗</a>:null}<span className="fcp-monitor-dur" title="Sequence duration">{timecode(total,24)}</span>{timecodeField('program',seqTc(programFrame),'Sequence timecode')}</div>
          <div className="fcp-stage">{renderedPreview||(pictureAtFrame&&activeAsset&&activeShot)?<video key={renderedPreview ? `render:${sequence.id}:${sequence.revision}` : activeShot?.id} ref={programVideo} src={renderedPreview ? `${sequence.export.media_url}?revision=${sequence.revision}` : activeAsset?.media_url} muted={!renderedPreview || (shuttle !== 0 && shuttle !== 1)} playsInline preload="auto" onLoadedMetadata={loadedProgram} onTimeUpdate={timeUpdate} onEnded={advance} onError={()=>{setPlaying(false);setError('The selected program source could not be played.')}}/>:<div className="film-empty">{total?(pictureTotal?'Uncovered picture tail · audio continues':'Audio-only sequence · no picture'): 'Set a duration below to start with audio, or drag a clip from the Browser onto V1.'}</div>}{shuttleLabel&&!viewerTransport?<span className="ed-shuttle fcp-shuttle-osd" aria-live="polite">{shuttleLabel}</span>:null}</div>
          <div className="fcp-scrub"><input aria-label="Canvas playhead" type="range" min={0} max={Math.max(0,total-1)} value={Math.min(programFrame,Math.max(0,total-1))} onChange={e=>{stopTransport();seekProgram(Number(e.target.value))}}/></div>
          <div className="fcp-edit-buttons" role="group" aria-label="Edit the Viewer take into the sequence">{(()=>{const why=!source?'Open a take in the Viewer first':boundShot?'The Viewer shows a sequence shot; open the take from the Browser':busy||exporting?'Busy':'';return <>
            <button className="fcp-edit-insert" disabled={!!why} title={why||'Insert (F9): splice the Viewer range in at the sequence In, or the playhead; later picture moves later. Audio stays put.'} onClick={()=>threePoint('insert')}>Insert</button>
            <button className="fcp-edit-overwrite" disabled={!!why} title={why||'Overwrite (F10): cover the picture from the sequence In, or the playhead, with the Viewer range.'} onClick={()=>threePoint('overwrite')}>Overwrite</button>
            <button className="fcp-edit-replace" disabled={!!why} title={why||'Replace (F11): swap the shot under the playhead for the Viewer take, lining up the Viewer frame with the Canvas frame. F11 may be taken by the browser for full screen.'} onClick={()=>threePoint('replace')}>Replace</button></>})()}</div>
          <div className="ed-transport film-actions fcp-transport" role="toolbar" aria-label="Canvas transport">{stripButton('canvas','nav.in','⇤','Go to sequence In (Shift+I)',!total)}{stripButton('canvas','play.inToOut','▷|','Play In to Out (Shift+\)',!total)}{stripButton('canvas','mark.in','In','Mark sequence In (I)',!total)}<button className="fcp-play" disabled={!total} title="Play / pause sequence (Space)" onClick={()=>void playProgram()}>{playing?'Pause sequence':'Play sequence'}</button>{stripButton('canvas','mark.out','Out','Mark sequence Out (O)',!total)}{stripButton('canvas','play.around','↔','Play around the playhead (\)',!total)}{stripButton('canvas','nav.out','⇥','Go to sequence Out (Shift+O)',!total)}{stripButton('canvas','mark.add','◆','Add marker (M)',!total)}{stripButton('canvas','nav.matchFrame','Match','Match frame: open the take under the playhead in the Viewer (F)',!activeShot)}{volumeControl}<span className="fcp-readout">{(programFrame/24).toFixed(2)} / {(total/24).toFixed(2)}s</span></div>
          {sequence.export?.status&&!['complete','draft','none'].includes(sequence.export.status)?<div className="fcp-monitor-info"><p role="status" className="fcp-export" data-export={sequence.export.status}>Export: {sequence.export.status}</p></div>:null}
          {sequence.export?.error?<p role="alert">{typeof sequence.export.error==='string'?sequence.export.error:JSON.stringify(sequence.export.error)}</p>:null}
        </div>:<div className="ed-monitor-empty">Open or create a named sequence in the Browser. Audio can be auditioned independently in the Viewer.</div>}
      </section>
    </div>
    <div role="separator" tabIndex={0} aria-orientation="horizontal" aria-label="Resize monitors and timeline" aria-valuemin={28} aria-valuemax={72} aria-valuenow={Math.round(upperSplit)} title="Drag to resize · double-click to reset" className="ed-divider fcp-divider" onPointerDown={dragSplit} onDoubleClick={()=>setUpperSplit(52)} onKeyDown={e=>{if(e.key==='ArrowUp'||e.key==='ArrowDown'){e.preventDefault();e.stopPropagation();setUpperSplit(v=>Math.max(28,Math.min(72,v+(e.key==='ArrowUp'?-2:2))))}}}/>
    <section inert={!!rehearsal} data-track-size={trackSize} className={`ed-pane fcp-timeline ${activePane==='timeline'?'active-pane':''}`} onPointerDown={()=>setActivePane('timeline')}>
      <h2 className="ed-pane-title">Timeline <span>{sequence?.title??'No sequence'} · 24 fps · V1 / A1 / A2</span></h2>
      <div className="ed-tabs fcp-timeline-bar"><div className="fcp-seq-tabs">{project?.sequences.map(item=><button key={item.id} disabled={navBlocked} data-unsaved={unsaved(item.id)||undefined} aria-pressed={item.id===sequence?.id} title={item.title} onClick={()=>void open(item.id)}>{item.title}</button>)}</div><span className="ed-timecode" title="Sequence timecode">{seqTc(programFrame)}</span><button aria-label="Zoom timeline out" title="Zoom out (Ctrl+-)" onClick={()=>setZoom(z=>Math.max(100,z/1.5))}>−</button><button aria-label="Zoom timeline in" title="Zoom in (Ctrl+=)" onClick={()=>setZoom(z=>Math.min(800,z*1.5))}>+</button><button title="Fit sequence (Shift+Z)" onClick={()=>setZoom(100)}>Fit sequence</button><button type="button" className="fcp-snap" data-on={snapping||undefined} aria-label={`Snapping ${snapping?'on':'off'} (N)`} title={`Snapping ${snapping?'on':'off'} (N): clip drags snap to cuts, the playhead, markers and In/Out`} onMouseDown={e=>e.preventDefault()} onClick={()=>setSnapping(s=>!s)}>🧲</button><span className="fcp-tools" role="radiogroup" aria-label="Timeline tool">{([['select','➚','Selection (A)'],['razor','✂','Razor (B): click a clip to cut it'],['roll','⇹','Roll (R): [ and ] move the selected edit'],['ripple','⇥','Ripple (R R): [ and ] trim one side; later shots follow'],['slip','↔','Slip (S): [ and ] slip the selected shot']] as const).map(([id,icon,label])=><button key={id} type="button" role="radio" data-tool={id} aria-checked={tool===id} aria-label={label} title={label} onMouseDown={e=>e.preventDefault()} onClick={()=>{setTool(id);if(selectedEdit&&selectedEdit.leftId&&selectedEdit.rightId&&(id==='roll'||id==='ripple'))setSelectedEdit({...selectedEdit,side:id==='roll'?'both':(selectedEdit.side==='both'?'left':selectedEdit.side)})}}>{icon}</button>)}</span>{selectedEdit&&selectedEditFrame!==null?<span className="fcp-edit-readout" title="Selected edit point: [ ] trim, Shift+[ ] by 5, U changes side, E extends to the playhead">Edit {seqTc(selectedEditFrame)} · {selectedEdit.side==='both'?'roll':selectedEdit.side==='left'?'Out side':'In side'}</span>:null}<span className="fcp-zoom">{Math.round(zoom)}%</span></div>
      <div className="fcp-timeline-tools"><details><summary>Sequence duration / audio-first</summary><label>Timeline duration (seconds)<input type="number" min={1/24} max={600} step={1/24} value={Number((total/24).toFixed(4))} disabled={busy||exporting} onChange={e=>{if(e.target.value)update({timeline_duration_frames:Math.max(1,Math.round(Number(e.target.value)*24))})}}/></label><p>Explicit duration supports sound before picture. Audio-only exports WAV; adding picture preserves duration and uncovered time renders black. Save rejects a duration shorter than placed content.</p></details>{sequence&&total?<details><summary>Selection & markers{sequence.selection||sequence.markers?.length?<small> · {sequence.selection?'range set':'no range'} · {sequence.markers?.length??0} marker(s)</small>:null}</summary><button disabled={busy||exporting} onClick={()=>update({selection:{in_frame:programFrame,out_frame:Math.max(programFrame+1,sequence.selection?.out_frame??total)}})}>Set selection In</button><button disabled={busy||exporting} onClick={()=>update({selection:{in_frame:Math.min(programFrame,sequence.selection?.in_frame??0),out_frame:Math.min(total,programFrame+1)}})}>Set selection Out</button><button disabled={busy||exporting||!sequence.selection} onClick={()=>update({selection:null})}>Clear selection</button>{sequence.selection?<><label>Selection In frame<input type="number" min={0} max={sequence.selection.out_frame-1} value={sequence.selection.in_frame} disabled={busy||exporting} onChange={e=>{const n=Number(e.target.value);if(e.target.value&&Number.isInteger(n)&&n>=0&&n<(sequence.selection?.out_frame??0))update({selection:{in_frame:n,out_frame:sequence.selection!.out_frame}})}}/></label><label>Selection Out frame (exclusive)<input type="number" min={sequence.selection.in_frame+1} max={total} value={sequence.selection.out_frame} disabled={busy||exporting} onChange={e=>{const n=Number(e.target.value);if(e.target.value&&Number.isInteger(n)&&n>(sequence.selection?.in_frame??0)&&n<=total)update({selection:{in_frame:sequence.selection!.in_frame,out_frame:n}})}}/></label></>:null}<button disabled={busy||dirty||exporting||planDirty||!sequence.selection} onClick={()=>{if(sequence.selection){setPlanRequest({token:Date.now(),sequence_id:sequence.id,...sequence.selection});setPanel('plan');setActivePane('viewer')}}}>Make shot from selection</button>{sequence.selection?<span>Frames {sequence.selection.in_frame}–{sequence.selection.out_frame} (Out exclusive); {((sequence.selection.out_frame-sequence.selection.in_frame)/24).toFixed(3)}s</span>:null}<label>Marker label<input value={markerLabel} onChange={e=>setMarkerLabel(e.target.value)} maxLength={100}/></label><button disabled={busy||exporting} onClick={()=>{update({markers:[...(sequence.markers??[]),{id:crypto.randomUUID(),label:markerLabel.trim()||'Marker',frame:Math.min(total-1,programFrame)}]});setMarkerLabel('')}}>Add marker at playhead</button>{sequence.markers?.map(m=><span className="fcp-marker-item" key={m.id}><button onClick={()=>{stopTransport();seekProgram(m.frame)}}>{m.label} · {seqTc(m.frame)}</button><button aria-label={`Remove marker ${m.label}`} disabled={busy||exporting} onClick={()=>update({markers:sequence.markers?.filter(x=>x.id!==m.id)})}>×</button></span>)}<p>Selection and markers save with this sequence. They do not trim media or generate lip-sync.</p></details>:null}</div>
      <div className="generation-queue-status">{generationError?`Job status unavailable: ${generationError}`:pending.length?`${pending.length} requested take(s): the striped blocks are reserved spots, not clips yet. Click one to see what to do next.`:''}{pending.length?<button onClick={()=>setGuide({jobId:pending.find(p=>!hiddenJobs.includes(p.job_id))?.job_id??null})}>Guide me</button>:null}{pending.some(p=>hiddenJobs.includes(p.job_id))?<label className="generation-showall"><input type="checkbox" checked={showHidden} onChange={e=>setShowHidden(e.target.checked)}/>Show hidden ({pending.filter(p=>hiddenJobs.includes(p.job_id)).length})</label>:null}{(generations.length>0||generationError)?<button onClick={()=>setQueueEpoch(e=>e+1)}>Refresh job status</button>:null}</div>
      <div className="fcp-track-scroll" onClick={e=>{if(!(e.target as HTMLElement).closest('button,input'))setSelectedClip(null)}}><div className="fcp-track-surface" style={{width:`${zoom}%`}}>
        <div className="fcp-ruler"><span className="fcp-track-head">Timecode</span><div className="fcp-ruler-body">{renderState!=='empty'?<i className="fcp-render-bar" data-state={renderState} title={renderTitle} style={{width:`${100*total/timelineSpan}%`}}/>:null}{ticks.map(frame=><small key={frame} style={{left:`${100*frame/timelineSpan}%`}}>{seqTc(frame)}</small>)}{sequence?.selection?<i aria-hidden="true" className="fcp-ruler-selection" title="Sequence selection" style={{left:`${100*sequence.selection.in_frame/timelineSpan}%`,width:`${100*(sequence.selection.out_frame-sequence.selection.in_frame)/timelineSpan}%`}}/>:null}{sequence?.markers?.map(m=><i aria-hidden="true" className="fcp-ruler-marker" key={m.id} style={{left:`${100*m.frame/timelineSpan}%`}}><b>{m.label}</b></i>)}<i aria-hidden="true" className="fcp-ruler-playhead" style={{left:`${100*programFrame/timelineSpan}%`}}/><input aria-label="Timeline playhead" type="range" style={{width:`${100*Math.max(1,total)/timelineSpan}%`}} min={0} max={Math.max(0,total-1)} value={Math.min(programFrame,Math.max(0,total-1))} onChange={e=>{stopTransport();seekProgram(Number(e.target.value))}}/></div></div>
        <div className="fcp-track fcp-track-video"><strong className="fcp-track-head"><b>V1</b><span>Picture</span></strong><div className="fcp-track-clips" data-tool={tool} onDragOver={e=>binDragOver(e,'V1')} onDragLeave={binDragLeave} onDrop={e=>binDropOn(e,'V1')}>{dropMarker('V1')}{(()=>{const f=selectedEdit?editPointFrame(shownShots,selectedEdit):null;return f!==null&&selectedEdit?<i aria-hidden="true" className="fcp-edit-point" data-side={selectedEdit.side} style={{left:`${100*f/timelineSpan}%`}}/>:null})()}{(tool==='roll'||tool==='ripple')&&!dragPreview?editPoints(shownShots).map(p=><i key={`${p.leftId}|${p.rightId}`} aria-hidden="true" className="fcp-edge" data-tool={tool} style={{left:`${100*p.frame/timelineSpan}%`}} title={tool==='roll'?'Drag to roll this edit':'Drag the left half to ripple the Out, the right half to ripple the In'} onPointerDown={e=>{const r=e.currentTarget.getBoundingClientRect();const side=!p.leftId?'right':!p.rightId?'left':tool==='roll'?'both':(e.clientX<r.left+r.width/2?'left':'right');startDrag(e,'edge',{leftId:p.leftId,rightId:p.rightId,side})}}/>):null}{dragPreview?<span className="fcp-drag-readout" aria-live="polite">{dragPreview.note}</span>:null}{shownShots.map((shot,index)=>{if(isGap(shot))return <button key={shot.id} type="button" data-kind="gap" className="fcp-gap" style={{width:`${100*shot.duration_frames/timelineSpan}%`}} aria-pressed={selectedClip?.id===shot.id} aria-label={`Gap, ${shot.duration_frames} frames`} title={`Gap · ${shot.duration_frames} frames (${(shot.duration_frames/24).toFixed(2)}s) · black in the export — Shift+Delete closes it up; Overwrite fills it`} onClick={e=>clickShot(e,shot)} onContextMenu={e=>{setSelectedClip({kind:'shot',id:shot.id});setSelectedEdit(null);setActivePane('timeline');openCtx(e,{kind:'shot',id:shot.id})}}/>;const label=catalog.assets.find(a=>a.id===shot.asset_id)?.label;return <button style={{width:`${100*shot.duration_frames/timelineSpan}%`}} className={shot.id===activeShot?.id?'selected':''} aria-current={shot.id===activeShot?.id?'true':undefined} key={shot.id} data-in-viewer={boundShot?.id===shot.id?'true':undefined} aria-pressed={selectedClip?.id===shot.id} onClick={e=>clickShot(e,shot)} onDoubleClick={()=>{if(tool==='select')openShotInViewer(shot)}} onContextMenu={e=>{setSelectedClip({kind:'shot',id:shot.id});setSelectedEdit(null);setActivePane('timeline');openCtx(e,{kind:'shot',id:shot.id})}} onPointerDown={e=>{if(tool==='slip')startDrag(e,'slip',null,shot.id);else if(tool==='select')startDrag(e,'move',null,shot.id)}} title={`${label} · ${shot.duration_frames} frames — double-click to open this shot in the Viewer`}><Thumb className="fcp-thumb fcp-clip-thumb" src={catalog.assets.find(a=>a.id===shot.asset_id)?.media_url} frame={shot.source_in_frame} cacheKey={`${shot.asset_id}:${shot.source_in_frame}`}/><span>{label??'Shot'}</span><small aria-hidden="true">{index+1} · {(shot.duration_frames/24).toFixed(2)}s</small></button>})}{pendingBlocks('V1')}{sequence?Object.entries(takeSpots).filter(([,s])=>s.sequence_id===sequence.id).map(([jobId,s])=>{const w=resolveSpot(shownShots,s,programFrame);if('error' in w)return null;const job=genJobs.find(j=>j.id===jobId);return <span key={`spot-${jobId}`} role="button" tabIndex={0} className="take-spot" data-ready={(job&&takeState(job).approved)||undefined} data-placed={(job?.video_asset_id&&inSequence.has(job.video_asset_id))||undefined} style={{left:`${100*w.frame/timelineSpan}%`}} title={`${job?.label??'Requested take'} will go here (${w.note}). Click for options.`} onClick={e=>{e.stopPropagation();setSpotCard({jobId,x:Math.min(e.clientX,window.innerWidth-300),y:Math.max(8,e.clientY-220)})}} onContextMenu={e=>openCtx(e,{kind:'spot',jobId})} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();const r=e.currentTarget.getBoundingClientRect();setSpotCard({jobId,x:Math.min(r.left,window.innerWidth-300),y:Math.max(8,r.top-220)})}}}><b aria-hidden="true">⚑</b><span>{job?.label??'Take'}</span></span>}):null}</div></div>
        {(['production','music'] as const).map((role,index)=><div className="fcp-track fcp-track-audio" key={role}><strong className="fcp-track-head"><b>A{index+1}</b><span>{role==='music'?'Music':'Production'}</span></strong><div className="fcp-track-clips" onDragOver={e=>binDragOver(e,role==='music'?'A2':'A1')} onDragLeave={binDragLeave} onDrop={e=>binDropOn(e,role==='music'?'A2':'A1')}>{dropMarker(role==='music'?'A2':'A1')}{sequence?.audio_tracks.filter(t=>t.role===role).map(t=><button key={t.id} data-enabled={t.enabled} title={`${role} · ${t.gain_db}dB · ${(t.duration_frames/24).toFixed(2)}s${t.enabled?'':' · disabled (muted)'} — open audio controls`} style={{position:'absolute',left:`${100*t.start_frame/timelineSpan}%`,width:`${100*t.duration_frames/timelineSpan}%`,opacity:t.enabled?1:.4}} aria-pressed={selectedClip?.id===t.id} onClick={e=>{e.stopPropagation();setSelectedClip({kind:'audio',id:t.id});setActivePane('timeline')}} onDoubleClick={()=>reviewGeneratedAudio(t.asset_id,role)} onContextMenu={e=>{setSelectedClip({kind:'audio',id:t.id});setActivePane('timeline');openCtx(e,{kind:'audio',id:t.id})}}>{role} · {t.gain_db}dB{t.enabled?'':' · off'}<AudioWaveform assetId={t.asset_id} sourceIn={t.source_in_frame/24} duration={t.duration_frames/24} compact/></button>)}{pendingBlocks(role==='music'?'A2':'A1')}</div></div>)}
        <div className="fcp-playhead" style={{left:`calc(var(--fcp-label) + (100% - var(--fcp-label)) * ${programFrame/timelineSpan})`}}/>
      </div></div>
      {sequence?<>{inspShot&&isGap(inspShot)?<div className="film-shot-controls"><strong>{selectedShot?'Selected gap':'Gap'} {inspIndex+1}</strong><span className="fcp-shot-name">of {sequence.shots.length} · {inspShot.duration_frames} frames ({(inspShot.duration_frames/24).toFixed(2)}s) · black in the export</span><span className="ed-menu-spacer"/></div>:inspShot?<div className="film-shot-controls"><strong>{selectedShot?'Selected shot':'Shot'} {inspIndex+1}</strong><span className="fcp-shot-name" title={inspAsset?.label}>of {sequence.shots.length} · {inspAsset?.label??'Source unavailable'}</span><label>Source in (seconds)<input type="number" min={0} step={1/24} value={Number((inspShot.source_in_frame/24).toFixed(4))} disabled={busy||exporting} onChange={e=>patchShot(inspShot.id,{source_in_frame:Math.round(Number(e.target.value)*24)})}/></label><label>Duration (seconds)<input type="number" min={1/24} step={1/24} value={Number((inspShot.duration_frames/24).toFixed(4))} disabled={busy||exporting} onChange={e=>patchShot(inspShot.id,{duration_frames:Math.round(Number(e.target.value)*24)})}/></label><span>Source out: {((inspShot.source_in_frame + inspShot.duration_frames)/24).toFixed(3)}s</span><span className="ed-menu-spacer"/><button disabled={busy||exporting||dirty||sequence.export?.status!=='complete'} title="Prepare from the last used frame of this shot in the current completed sequence export; no generation starts." onClick={()=>prepareContinuation(inspShot.id)}>Continue this shot</button><button disabled={busy||exporting||inspIndex<=0} onClick={()=>move(inspIndex,-1)}>Move earlier</button><button disabled={busy||exporting||inspIndex>=sequence.shots.length-1} onClick={()=>move(inspIndex,1)}>Move later</button><button disabled={busy||exporting} title="Ripple delete (Shift+Delete): later shots move earlier" onClick={()=>applyEdit(rippleDelete(sequence.shots,inspShot.id))}>Remove shot</button></div>:selectedAudio?<div className="film-shot-controls"><strong>Selected {selectedAudio.role==='music'?'A2 music':'A1 production'}</strong><span className="fcp-shot-name">{selectedAudio.asset_id.slice(0,18)}…</span><span>Start {seqTc(selectedAudio.start_frame)} · {(selectedAudio.duration_frames/24).toFixed(2)}s · {selectedAudio.gain_db}dB{selectedAudio.enabled?'':' · off'}</span><span className="ed-menu-spacer"/><button onClick={()=>reviewGeneratedAudio(selectedAudio.asset_id,selectedAudio.role)}>Open in Audio tab</button><button disabled={busy||exporting} title="Lift (Delete): remove this placement; the source is kept" onClick={()=>{update({audio_tracks:sequence.audio_tracks.filter(t=>t.id!==selectedAudio.id)});setSelectedClip(null)}}>Remove placement</button></div>:<p className="fcp-no-shots">No shots yet.</p>}
          </>:null}
    </section>
    {layoutOpen?<KeyboardLayout keymap={keymap} onChange={changeKeymap} onClose={()=>setLayoutOpen(false)}/>:null}
    {blockCard?(()=>{const p=blockCard.p,hidden=hiddenJobs.includes(p.job_id),steps=guideSteps({placement:p,hasBrief:true}),next=steps.find(s=>s.status==='current');return <div className="fcp-context-backdrop" onMouseDown={()=>setBlockCard(null)}><div role="dialog" aria-label={`Requested take ${p.job.label}`} className="generation-block-card" style={{left:blockCard.x,top:blockCard.y}} onMouseDown={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setBlockCard(null)}}}>
      <header><strong>{p.job.label}</strong><button aria-label="Close" onClick={()=>setBlockCard(null)}>×</button></header>
      <p>This striped block is a <b>reserved spot</b> for a generated take you requested. It is not a clip yet and is not in the export.</p>
      <p className="generation-next">{next?`Next: ${next.title}.`:'All steps done.'} <span className="job-stage-inline">({generationStage(p.stage)})</span></p>
      <div className="film-actions">
        <button className="ed-primary" autoFocus onClick={()=>{setBlockCard(null);setGuide({jobId:p.job_id})}}>Guide me</button>
        {next?<button onClick={()=>guideShow(next.id,p)}>Show me: {next.title.toLowerCase()}</button>:null}
        <button onClick={()=>{setBlockCard(null);inspectGeneration(p)}}>Open its card</button>
        <button title="Hides this block on this computer only. The take and its request are kept; tick Show hidden to see it again." onClick={()=>{setBlockCard(null);setHiddenJobs(h=>hidden?h.filter(x=>x!==p.job_id):[...h,p.job_id]);setStatus(hidden?`Showing “${p.job.label}” on the timeline again.`:`Hid “${p.job.label}” from the timeline (this computer only). Show hidden brings it back.`)}}>{hidden?'Show on timeline again':'Hide from timeline'}</button>
      </div>
      <p className="generation-block-foot">When it finishes it appears in the Browser; place it here, or drag it onto the timeline. Hiding only tidies the timeline; the take stays in the library.</p>
    </div></div>})():null}
    {spotCard&&sequence?(()=>{const job=genJobs.find(j=>j.id===spotCard.jobId),s=takeSpots[spotCard.jobId];if(!s)return null;const w=resolveSpot(sequence.shots,s,programFrame);const st=job?takeState(job):null;const close=()=>setSpotCard(null)
      const state=!job?'Waiting for the job to appear.':['pending','submitting','queued','running'].includes(job.status)?'Generating on the worker.':['failed','canceled'].includes(job.status)?'The generation failed.':!job.video_asset_id?'Finished: importing into the Browser (see the Queue tab if it failed).':'In the Browser: ready to place.'
      return <div className="fcp-context-backdrop" onMouseDown={close}><div role="dialog" aria-label={`Spot for ${job?.label??'requested take'}`} className="generation-block-card" style={{left:spotCard.x,top:spotCard.y}} onMouseDown={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();close()}}}>
        <header><strong>⚑ {job?.label??'Requested take'}</strong><button aria-label="Close" onClick={close}>×</button></header>
        <p>This flag marks where the take will go: {'error' in w?w.error:w.note}. It is only a marker; nothing is on the timeline yet.</p>
        <p className="generation-next">{state}</p>
        <div className="film-actions">
          {job?.video_asset_id&&inSequence.has(job.video_asset_id)?<span className="generation-next">Placed (unsaved): Save to keep it, Ctrl+Z to undo.</span>:st?.approved?<button className="ed-primary" autoFocus onClick={()=>{close();if(job)placeTakeNow(job)}}>Place it here</button>:null}
          {job?.video_asset_id&&!inSequence.has(job.video_asset_id)?<button onClick={()=>{close();auditionTake(job)}}>Audition here</button>:null}
          <button onClick={()=>{close();setGuide({jobId:spotCard.jobId})}}>Guide me</button>
          <button onClick={()=>{close();setSelectedJob(spotCard.jobId);setPanel('history');setActivePane('viewer')}}>Show in Queue</button>
          <button onClick={()=>{setTakeSpots(x=>({...x,[spotCard.jobId]:{sequence_id:sequence.id,kind:'playhead',frame:programFrame}}));close();setStatus('Moved the marker to the playhead.')}}>Move to playhead</button>
          <button onClick={()=>{removeSpot(spotCard.jobId);close();setStatus('Removed the marker. The take stays in the Browser.')}}>Remove marker</button>
        </div>
      </div></div>})():null}
    {audition?<AuditionPlayer title={audition.title} note={audition.note} video={audition.win.video} audio={audition.win.audio} length={audition.win.length} takeStart={audition.win.takeStart} takeFrames={audition.win.takeFrames} volume={volume} mediaFor={(id,kind)=>kind==='video'?(id.startsWith('astrid-preview:')?SHOT_BASE+'/media/take/'+id.slice(15):catalog.assets.find(a=>a.id===id)?.media_url):audioLibrary.find(a=>a.id===id)?.media_url} onClose={()=>setAudition(null)}/>:null}
    {guide?<GenerationGuide placement={guidePlacement} client={guidePlacement?guideClient:!genSnap?.setup} inTimeline={guideInTimeline} savedPlaced={guideSaved} act={guideActions} onShow={guideShow} onClose={()=>setGuide(null)} onPickNew={()=>{setGuide({jobId:null});openGenerate('take')}}/>:null}
    {delClips?<DeleteClips clips={delClips.clips} cleanup={delClips.cleanup} localUse={localUse} onBefore={beforeDelete} onDone={afterDelete} onClose={()=>setDelClips(null)}/>:null}
    {ctxMenu&&ctxModel?<ContextMenu x={ctxMenu.x} y={ctxMenu.y} title={ctxModel.title} subtitle={ctxModel.subtitle} sections={ctxModel.sections} onClose={()=>setCtxMenu(null)}/>:null}
    {error?<div className="film-error" role="alert"><span>{error}</span><button onClick={()=>setError('')}>Dismiss</button></div>:null}
    <footer className="ed-pane-foot"><span className="fcp-foot-status" data-state={busy?'busy':dirty||storyDirty?'dirty':'idle'}>{busy?'Working…':rehearsal?'Frozen FMV rehearsal; exit to resume timeline editing':storyDirty?'Unsaved story edits: save or discard in Viewer FMV':dirty?(editNote?`Unsaved · ${editNote}`:'Unsaved sequence edits'):status}</span><span>Active: {activePane}{shuttleLabel?` · ${shuttleLabel}`:''} · Space / J K L · I / O · ↑ ↓ edits · M marker · type a timecode · Ctrl+1–4 · Alt+H keys · Shuttle audio muted outside 1×</span></footer>
  </main>
}
