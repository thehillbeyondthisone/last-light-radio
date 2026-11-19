// Pure FCP7-style edit operations on a Film sequence's V1 list of shots and gaps (gaps: film.py, 2026-11-14).
// No I/O, no React. Every function returns a new shot list or an error string; the caller applies it as one undo step.
// Rules mirror the save validator in last_light_radio/film.py: at most 256 shots, any imported source (no approve/reject since 2026-11-19),
// 0 <= source_in < frame_count, 1 <= duration <= frame_count - source_in, total picture <= 14400 frames.
// Media is never stretched or looped. A gap is {id, kind:'gap', duration_frames} with no source fields (the server refuses any).

export interface VideoShot { id: string; kind?: 'video'; asset_id: string; source_in_frame: number; duration_frames: number }
export interface GapShot { id: string; kind: 'gap'; duration_frames: number }
export type EditShot = VideoShot | GapShot
export const isGap = (shot: EditShot): shot is GapShot => shot.kind === 'gap'
export const gap = (duration_frames: number, id: string = crypto.randomUUID()): GapShot => ({ id, kind: 'gap', duration_frames })
/** Adjacent gaps become one (keeps the first id); zero-length items are dropped. */
export function mergeGaps(shots: readonly EditShot[]): EditShot[] {
  const out: EditShot[] = []
  for (const shot of shots) {
    if (shot.duration_frames < 1) continue
    const last = out.at(-1)
    if (last && isGap(last) && isGap(shot)) out[out.length - 1] = gap(last.duration_frames + shot.duration_frames, last.id)
    else out.push({ ...shot })
  }
  return out
}
export interface EditSource { id: string; status: string; frame_count: number }
export type EditResult = { ok: true; shots: EditShot[]; playhead: number; message: string } | { ok: false; error: string }

export const MAX_SHOTS = 256
export const MAX_FRAMES = 14400
const fail = (error: string): EditResult => ({ ok: false, error })
const total = (shots: readonly EditShot[]) => shots.reduce((sum, shot) => sum + shot.duration_frames, 0)
const newId = () => crypto.randomUUID()

/** Split so that a cut exists exactly at `frame`. The head keeps its id; the tail gets a new one. */
export function splitAt(shots: readonly EditShot[], frame: number): EditShot[] {
  const out: EditShot[] = []
  let start = 0
  for (const shot of shots) {
    const end = start + shot.duration_frames
    if (frame > start && frame < end) {
      const head = frame - start
      if (isGap(shot)) { out.push(gap(head, shot.id)); out.push(gap(shot.duration_frames - head)) }
      else {
        out.push({ ...shot, duration_frames: head })
        out.push({ ...shot, id: newId(), source_in_frame: shot.source_in_frame + head, duration_frames: shot.duration_frames - head })
      }
    } else out.push({ ...shot })
    start = end
  }
  return out
}
/** Index of the first shot starting at `frame` (a cut must already exist there), or shots.length at the end. */
function indexAt(shots: readonly EditShot[], frame: number) {
  let start = 0
  for (let i = 0; i < shots.length; i++) { if (start >= frame) return i; start += shots[i].duration_frames }
  return shots.length
}
function check(shots: EditShot[], playhead: number, message: string): EditResult {
  if (shots.length > MAX_SHOTS) return fail(`A sequence can hold at most ${MAX_SHOTS} shots.`)
  if (total(shots) > MAX_FRAMES) return fail('Film sequences currently support up to ten minutes.')
  return { ok: true, shots, playhead, message }
}

/** Three-point range. Source Out is inclusive (null = last frame); sequence Out is exclusive (null = not set). */
export function editRange(source: EditSource, sourceIn: number, sourceOut: number | null, seqIn: number | null, seqOut: number | null) {
  const last = source.frame_count - 1
  if (sourceIn < 0 || sourceIn > last) return { error: 'The source In point is outside this take.' } as const
  const sourceLength = (sourceOut ?? last) - sourceIn + 1
  // FCP7: when both sequence marks are set they decide the duration, taken from the source In.
  const length = seqIn !== null && seqOut !== null ? seqOut - seqIn : sourceLength
  if (length < 1) return { error: 'The marked range is empty.' } as const
  if (sourceIn + length > source.frame_count) return { error: `The sequence range needs ${length} frames but this take has only ${source.frame_count - sourceIn} after its In point. Media is never stretched or looped; mark a shorter sequence range or an earlier source In.` } as const
  return { sourceIn, length } as const
}

/** Insert (F9): splice the source range in at `at`, pushing later picture later. */
export function insertEdit(shots: readonly EditShot[], at: number, asset: string, sourceIn: number, length: number): EditResult {
  const picture = total(shots)
  const padded = at > picture ? [...shots, gap(at - picture)] : shots
  const split = splitAt(padded, at)
  const index = indexAt(split, at)
  split.splice(index, 0, { id: newId(), asset_id: asset, source_in_frame: sourceIn, duration_frames: length })
  return check(mergeGaps(split), at + length, `Inserted ${length} frames at ${at}${at > picture ? ` after a ${at - picture}-frame gap` : '; later shots moved ' + length + ' frames later'}.`)
}

/** Overwrite (F10): replace whatever picture lies in [at, at + length); extends the picture when it runs past the end. */
export function overwriteEdit(shots: readonly EditShot[], at: number, asset: string, sourceIn: number, length: number): EditResult {
  const picture = total(shots)
  const end = at + length
  const split = splitAt(splitAt(at > picture ? [...shots, gap(at - picture)] : shots, at), end)
  const kept: EditShot[] = []
  let start = 0, index = -1
  for (const shot of split) {
    if (start === at && index < 0) index = kept.length
    if (start < at || start >= end) kept.push(shot)
    start += shot.duration_frames
  }
  if (index < 0) index = kept.length
  kept.splice(index, 0, { id: newId(), asset_id: asset, source_in_frame: sourceIn, duration_frames: length })
  return check(mergeGaps(kept), end, `Overwrote ${length} frames from ${at}${at > picture ? ` after a ${at - picture}-frame gap` : ''}${end > picture ? `; picture extended by ${end - Math.max(at, picture)} frames` : ''}.`)
}

/** Replace (F11): swap the shot under `programFrame` for the source, keeping its position and duration.
 *  As in FCP7 the frame at the Viewer playhead lands on the frame at the Canvas playhead. */
export function replaceEdit(shots: readonly EditShot[], programFrame: number, source: EditSource, sourceFrame: number): EditResult {
  let start = 0
  for (let i = 0; i < shots.length; i++) {
    const shot = shots[i], end = start + shot.duration_frames
    if (programFrame >= start && programFrame < end) {
      if (isGap(shot)) return fail('The Canvas playhead is over a gap. Use Overwrite to fill a gap.')
      const sourceIn = sourceFrame - (programFrame - start)
      const before = programFrame - start, after = end - programFrame - 1
      if (sourceIn < 0) return fail(`Replace needs ${before} source frames before the Viewer playhead; this take has ${sourceFrame}. Move the Viewer playhead later, or the Canvas playhead earlier in the shot.`)
      if (sourceIn + shot.duration_frames > source.frame_count) return fail(`Replace needs ${after} source frames after the Viewer playhead; this take has ${source.frame_count - sourceFrame - 1}. Move the Viewer playhead earlier.`)
      const next = shots.map(s => ({ ...s }))
      next[i] = { id: newId(), asset_id: source.id, source_in_frame: sourceIn, duration_frames: shot.duration_frames }
      return check(next, programFrame, `Replaced shot ${i + 1} (${shot.duration_frames} frames) with the Viewer take, aligned at the playheads.`)
    }
    start = end
  }
  return fail('There is no shot under the Canvas playhead to replace.')
}

/** Ripple delete (Shift+Delete): remove a shot and close the gap. */
export function rippleDelete(shots: readonly EditShot[], id: string): EditResult {
  let start = 0
  for (const shot of shots) {
    if (shot.id === id) return check(mergeGaps(shots.filter(s => s.id !== id)), start, `Removed a ${shot.duration_frames}-frame ${isGap(shot) ? 'gap' : 'shot'}; later shots moved earlier.`)
    start += shot.duration_frames
  }
  return fail('That shot is no longer in the sequence.')
}

/** Lift (Delete): remove a shot and leave a gap of the same length, so later shots stay put. */
export function liftEdit(shots: readonly EditShot[], id: string): EditResult {
  let start = 0
  for (const shot of shots) {
    if (shot.id === id) {
      if (isGap(shot)) return fail('That is already a gap. Shift+Delete closes it up.')
      return check(mergeGaps(shots.map(s => s.id === id ? gap(s.duration_frames) : s)), start, `Lifted a ${shot.duration_frames}-frame shot; a gap holds its place.`)
    }
    start += shot.duration_frames
  }
  return fail('That shot is no longer in the sequence.')
}
// ---- Step 5 slice B: trims. An edit point is the boundary between two V1 items, named by their ids.
// leftId null = start of V1; rightId null = end of the picture. Frames are recomputed from the list, so undo/redo keep it valid.
export type EditSide = 'left' | 'both' | 'right'
export interface EditPoint { leftId: string | null; rightId: string | null; side: EditSide }
export type FrameCounts = (assetId: string) => number | undefined
const AUDIO = 'Audio stays put.'

/** Frame of an edit point, or null if its items are no longer adjacent. */
export function editPointFrame(shots: readonly EditShot[], point: EditPoint): number | null {
  let start = 0
  for (let i = 0; i <= shots.length; i++) {
    const left = shots[i - 1]?.id ?? null, right = shots[i]?.id ?? null
    if (left === point.leftId && right === point.rightId) return start
    if (i < shots.length) start += shots[i].duration_frames
  }
  return null
}
/** All edit points (start, cuts, end) with their frames. */
export function editPoints(shots: readonly EditShot[]): { frame: number; leftId: string | null; rightId: string | null }[] {
  const out = []; let start = 0
  for (let i = 0; i <= shots.length; i++) {
    out.push({ frame: start, leftId: shots[i - 1]?.id ?? null, rightId: shots[i]?.id ?? null })
    if (i < shots.length) start += shots[i].duration_frames
  }
  return shots.length ? out : []
}
/** FCP7 Select Edit (V): the edit point nearest the frame. */
export function nearestEditPoint(shots: readonly EditShot[], frame: number, side: EditSide = 'both'): EditPoint | null {
  let best: EditPoint | null = null, distance = Infinity
  for (const p of editPoints(shots)) {
    const d = Math.abs(p.frame - frame)
    if (d < distance) { distance = d; best = { leftId: p.leftId, rightId: p.rightId, side: p.leftId === null ? 'right' : p.rightId === null ? 'left' : side } }
  }
  return best
}
function sourceLimit(shot: EditShot, counts: FrameCounts): string | null {
  if (isGap(shot)) return null
  const n = counts(shot.asset_id)
  if (n === undefined) return 'A source take for this shot is missing from the library.'
  if (shot.source_in_frame < 0) return 'That would need source frames before the start of the take.'
  if (shot.source_in_frame + shot.duration_frames > n) return `That would need ${shot.source_in_frame + shot.duration_frames - n} source frame(s) past the end of the take. Media is never stretched or looped.`
  return null
}

/** Razor / Add Edit (Ctrl+V): cut V1 at the frame. */
export function addEdit(shots: readonly EditShot[], frame: number): EditResult {
  if (editPoints(shots).some(p => p.frame === frame)) return fail('There is already an edit at the playhead.')
  if (frame <= 0 || frame >= total(shots)) return fail('Move the playhead over a shot to cut it.')
  let start = 0
  for (const s of shots) { if (frame < start + s.duration_frames) { if (isGap(s)) return fail('That is a gap: there is no picture to cut.'); break } start += s.duration_frames }
  return check(splitAt(shots, frame), frame, `Cut V1 at ${frame}. ${AUDIO}`)
}

/** Roll (R) or Ripple (RR) trim by `delta` frames. Roll: both sides, cut moves, length unchanged.
 *  Ripple left: the left item's Out moves, later items follow. Ripple right: the right item's In moves, later items follow. */
export function trimEdit(shots: readonly EditShot[], point: EditPoint, delta: number, counts: FrameCounts): EditResult {
  const frame = editPointFrame(shots, point)
  if (frame === null) return fail('That edit point no longer exists.')
  if (!delta) return fail('Nothing to trim.')
  const next = shots.map(s => ({ ...s }))
  const li = next.findIndex(s => s.id === point.leftId), ri = next.findIndex(s => s.id === point.rightId)
  const left = li >= 0 ? next[li] : null, right = ri >= 0 ? next[ri] : null
  const side = point.side === 'both' && (!left || !right) ? (left ? 'left' : 'right') : point.side
  if (side === 'both') {
    left!.duration_frames += delta
    right!.duration_frames -= delta
    if (!isGap(right!)) right!.source_in_frame += delta
  } else if (side === 'left') {
    if (!left) return fail('There is nothing before this edit to trim.')
    left.duration_frames += delta
  } else {
    if (!right) return fail('There is nothing after this edit to trim.')
    right.duration_frames -= delta
    if (!isGap(right)) right.source_in_frame += delta
  }
  for (const s of [left, right]) {
    if (!s) continue
    if (s.duration_frames < 1) return fail(`A ${isGap(s) ? 'gap' : 'shot'} must keep at least one frame.`)
    const limit = sourceLimit(s, counts); if (limit) return fail(limit)
  }
  const kind = side === 'both' ? 'Rolled' : 'Rippled'
  const at = side === 'right' ? frame : frame + delta
  return check(next, at, `${kind} the edit ${delta > 0 ? 'later' : 'earlier'} by ${Math.abs(delta)} frame${Math.abs(delta) === 1 ? '' : 's'}${side === 'both' || (side === 'left' && !right) ? '' : `; later shots moved ${side === 'left' ? (delta > 0 ? 'later' : 'earlier') : (delta > 0 ? 'earlier' : 'later')}`}. ${AUDIO}`)
}

/** Slip (S): move the source range under a shot; position and length stay. */
export function slipEdit(shots: readonly EditShot[], id: string, delta: number, counts: FrameCounts): EditResult {
  const i = shots.findIndex(s => s.id === id)
  if (i < 0) return fail('That shot is no longer in the sequence.')
  const shot = shots[i]
  if (isGap(shot)) return fail('A gap has no source to slip.')
  const moved = { ...shot, source_in_frame: shot.source_in_frame + delta }
  const limit = sourceLimit(moved, counts); if (limit) return fail(limit)
  const next = shots.map(s => ({ ...s })); next[i] = moved
  let start = 0; for (let j = 0; j < i; j++) start += shots[j].duration_frames
  return check(next, start, `Slipped shot ${i + 1} ${delta > 0 ? 'later' : 'earlier'} in its take by ${Math.abs(delta)} frame${Math.abs(delta) === 1 ? '' : 's'} (source In ${moved.source_in_frame}). ${AUDIO}`)
}

/** Extend Edit (E): move the selected edit to the playhead (a roll, or a ripple when one side is selected). */
export function extendEdit(shots: readonly EditShot[], point: EditPoint, playhead: number, counts: FrameCounts): EditResult {
  const frame = editPointFrame(shots, point)
  if (frame === null) return fail('That edit point no longer exists.')
  if (playhead === frame) return fail('The playhead is already on this edit.')
  if (point.side === 'right' && point.leftId !== null) return fail('Extend Edit moves an Out or a whole edit. Press U to select the Out side or both sides, then E.')
  return trimEdit(shots, point, playhead - frame, counts)
}
/** After an edit changes the picture length: what the sequence's duration, markers and In/Out must become so the save validator accepts it.
 *  With no explicit duration, placed audio is kept whole by holding the length it needs. */
export interface FitInput { picture: number; explicit: number | undefined; audioEnd: number; markers: readonly { id: string; label: string; frame: number }[]; selection: { in_frame: number; out_frame: number } | null }
export function fitToPicture(f: FitInput) {
  const grow = f.explicit !== undefined && f.picture > f.explicit
  const hold = f.explicit === undefined && f.audioEnd > f.picture ? f.audioEnd : undefined
  const total = grow ? f.picture : f.explicit ?? hold ?? f.picture
  const markers = f.markers.filter(m => m.frame < total)
  const selection = f.selection && f.selection.in_frame < total ? { in_frame: f.selection.in_frame, out_frame: Math.min(f.selection.out_frame, total) } : null
  const dropped = f.markers.length - markers.length
  const notes = [grow ? 'Sequence duration extended to fit.' : '', hold !== undefined ? 'Sequence length held so placed audio is not cut.' : '', dropped ? `${dropped} marker(s) past the new end removed.` : '', f.selection && !selection ? 'In/Out past the new end cleared.' : ''].filter(Boolean)
  return { duration: grow ? f.picture : hold, markers, selection, note: notes.join(' ') }
}
// ---- Step 5: drag to move (4.2) and snapping (4.5)
/** Start frame of an item. */
export function itemStart(shots: readonly EditShot[], id: string): number | null {
  let start = 0
  for (const s of shots) { if (s.id === id) return start; start += s.duration_frames }
  return null
}
/** FCP7 drag move. 'overwrite' lifts the shot (leaving a gap) and overwrites it at `to`; 'insert' (Alt) closes up the origin
 *  and inserts the shot at `to`, which callers snap to a cut. The shot keeps its id and source range. Audio stays put. */
export function moveClip(shots: readonly EditShot[], id: string, to: number, mode: 'overwrite' | 'insert'): EditResult {
  const from = itemStart(shots, id)
  if (from === null) return fail('That shot is no longer in the sequence.')
  const shot = shots.find(s => s.id === id)!
  if (isGap(shot)) return fail('Gaps cannot be moved; move the shots around them.')
  if (to < 0) return fail('A shot cannot start before the sequence.')
  if (mode === 'overwrite' && to === from) return fail('The shot is already there.')
  let r: EditResult
  if (mode === 'overwrite') {
    const lifted = liftEdit(shots, id)
    if (!lifted.ok) return lifted
    r = overwriteEdit(lifted.shots, to, shot.asset_id, shot.source_in_frame, shot.duration_frames)
  } else {
    const removed = rippleDelete(shots, id)
    if (!removed.ok) return removed
    const at = to > from ? to - shot.duration_frames : to // the cut positions shift once the shot is out
    if (at === from) return fail('The shot is already there.')
    r = insertEdit(removed.shots, Math.max(0, at), shot.asset_id, shot.source_in_frame, shot.duration_frames)
  }
  if (!r.ok) return r
  // Give the moved shot back its id (selection and edit points follow it). Strip trailing gaps a move leaves behind.
  const placedAt = r.playhead - shot.duration_frames
  let start = 0
  const out = r.shots.map(s => { const here = start; start += s.duration_frames; return !isGap(s) && here === placedAt && s.asset_id === shot.asset_id && s.source_in_frame === shot.source_in_frame && s.duration_frames === shot.duration_frames ? { ...s, id } : s })
  // Drop a trailing gap only if this move created it; a deliberate one (e.g. after lifting the last shot) stays.
  const hadTrailingGap = shots.length > 0 && isGap(shots[shots.length - 1])
  if (!hadTrailingGap) while (out.length && isGap(out[out.length - 1])) out.pop()
  return check(out, placedAt, mode === 'overwrite'
    ? `Moved the shot from ${from} to ${placedAt}; a gap holds its old place and it covers what was there. Audio stays put.`
    : `Rearranged: the shot now starts at ${placedAt}; the shots in between closed up. Audio stays put.`)
}
/** Snap a frame to the nearest target within `tolerance` frames (FCP7 snapping, N). */
export function snapFrame(frame: number, targets: readonly number[], tolerance: number): { frame: number; snapped: boolean } {
  let best = frame, distance = tolerance + 1
  for (const t of targets) { const d = Math.abs(t - frame); if (d < distance) { distance = d; best = t } }
  return distance <= tolerance ? { frame: best, snapped: true } : { frame, snapped: false }
}
/** Nearest cut (start, cuts, end of picture) to a frame, ignoring the moving shot. Used to place a rearranged shot. */
export function nearestCut(shots: readonly EditShot[], frame: number): number {
  const cuts = [0]; let at = 0
  for (const s of shots) { at += s.duration_frames; cuts.push(at) }
  return cuts.reduce((b, c) => Math.abs(c - frame) < Math.abs(b - frame) ? c : b, 0)
}
// ---- Generate tab: where a requested take should go, and placing it (picture + its sound) with Insert.
/** Remembered in the editor when a take is requested. Clip ids, not frames, so later edits keep it pointing at the right place. */
export interface TakeSpot { sequence_id: string; kind: 'before' | 'after' | 'playhead' | 'end'; clipId?: string; frame?: number; clipLabel?: string }
export function resolveSpot(shots: readonly EditShot[], spot: TakeSpot, playhead: number): { frame: number; splits: boolean; note: string } | { error: string } {
  const picture = total(shots)
  let frame: number
  if (spot.kind === 'end') frame = picture
  else if (spot.kind === 'playhead') frame = Math.max(0, spot.frame ?? playhead)
  else {
    const start = itemStart(shots, spot.clipId ?? '')
    if (start === null) return { error: `The clip it was meant to go ${spot.kind} is no longer in the sequence. Choose a new spot.` }
    frame = spot.kind === 'before' ? start : start + shots.find(s => s.id === spot.clipId)!.duration_frames
  }
  let at = 0, splits = false
  for (const s of shots) { if (frame > at && frame < at + s.duration_frames && !isGap(s)) splits = true; at += s.duration_frames }
  const where = spot.kind === 'end' ? 'at the end of the picture' : spot.kind === 'playhead' ? `at frame ${frame}` : `${spot.kind} “${spot.clipLabel ?? 'the clip'}”`
  return { frame, splits, note: splits ? `${where} (inside a shot: Insert will split it)` : where }
}
export interface TakeMedia { videoAssetId: string; frames: number; audioAssetId?: string; audioFrames?: number }
export interface TrackLike { id: string; role: 'production' | 'music'; asset_id: string; start_frame: number; source_in_frame: number; duration_frames: number; gain_db: number; fade_in_frames: number; fade_out_frames: number; enabled: boolean }
/** Insert the take's picture at `at` and put its production sound on A1 at the same start (as the server's place route does).
 *  'ripple' pushes audio that starts at or after `at` later by the take's length; 'preserve' keeps all audio where it is. */
export function placeTake(shots: readonly EditShot[], tracks: readonly TrackLike[], at: number, take: TakeMedia, policy: 'preserve' | 'ripple'): (Extract<EditResult, { ok: true }> & { tracks: TrackLike[] }) | { ok: false; error: string } {
  if (take.frames < 1) return fail('The take has no frames to place.') as { ok: false; error: string }
  const r = insertEdit(shots, at, take.videoAssetId, 0, take.frames)
  if (!r.ok) return r
  const next = tracks.map(t => policy === 'ripple' && t.start_frame >= at ? { ...t, start_frame: t.start_frame + take.frames } : { ...t })
  if (take.audioAssetId) {
    const length = Math.min(take.frames, Math.max(0, take.audioFrames ?? take.frames))
    if (length < 1) return fail('The take’s sound is empty.') as { ok: false; error: string }
    next.push({ id: newId(), role: 'production', asset_id: take.audioAssetId, start_frame: at, source_in_frame: 0, duration_frames: length, gain_db: 0, fade_in_frames: 0, fade_out_frames: 0, enabled: true })
  }
  return { ...r, tracks: next, message: `Placed the take at ${at} (${take.frames} frames)${take.audioAssetId ? ' with its production sound on A1' : ''}; ${policy === 'ripple' ? 'later audio moved with it' : 'existing audio kept its timing'}.` }
}
// ---- Lift / Extract In to Out (Premiere ; and '): split shots at In and Out, then remove what lies between.
/** Remove [inF, outF) from every audio placement: A1 production sound and A2 music (Boden 2026-11-17: Lift / Extract cut music too).
 *  A placement crossing the range is split into the part before In and the part after Out.
 *  close=true (Extract) also moves later audio earlier by the range length. */
export function cutAudioRange<T extends TrackLike>(tracks: readonly T[], inF: number, outF: number, close: boolean): T[] {
  const len = outF - inF, out: T[] = []
  for (const t of tracks) {
    const end = t.start_frame + t.duration_frames
    if (end <= inF) { out.push({ ...t }); continue }
    if (t.start_frame >= outF) { out.push({ ...t, start_frame: close ? t.start_frame - len : t.start_frame }); continue }
    if (t.start_frame < inF) {
      const d = inF - t.start_frame, fadeIn = Math.min(t.fade_in_frames, d)
      out.push({ ...t, duration_frames: d, fade_in_frames: fadeIn, fade_out_frames: 0 })
    }
    if (end > outF) {
      const d = end - outF
      out.push({ ...t, id: newId(), start_frame: close ? inF : outF, source_in_frame: t.source_in_frame + (outF - t.start_frame), duration_frames: d, fade_in_frames: 0, fade_out_frames: Math.min(t.fade_out_frames, d) })
    }
  }
  return out
}
function rangeCheck(shots: readonly EditShot[], inF: number, outF: number): string | null {
  const picture = total(shots)
  if (!(outF > inF)) return 'Mark an In and an Out first (I and O), with the Out after the In.'
  if (inF >= picture) return 'The In point is past the end of the picture; there is nothing to remove.'
  return null
}
/** Lift (;): remove the In-to-Out range and leave a gap the same length; later shots stay put. */
export function liftRange(shots: readonly EditShot[], inF: number, outF: number): EditResult {
  const problem = rangeCheck(shots, inF, outF); if (problem) return fail(problem)
  const end = Math.min(outF, total(shots))
  const split = splitAt(splitAt(shots, inF), end)
  let at = 0
  const next = split.map(s => { const here = at; at += s.duration_frames; return here >= inF && here < end ? gap(s.duration_frames) : s })
  return check(mergeGaps(next), inF, `Lifted ${end - inF} frames (${inF}–${end}); a gap holds the place. Production sound and music in the range were removed too.`)
}
/** Extract ('): remove the In-to-Out range and close up; later shots move earlier. */
export function extractRange(shots: readonly EditShot[], inF: number, outF: number): EditResult {
  const problem = rangeCheck(shots, inF, outF); if (problem) return fail(problem)
  const end = Math.min(outF, total(shots))
  const split = splitAt(splitAt(shots, inF), end)
  let at = 0
  const next = split.filter(s => { const here = at; at += s.duration_frames; return !(here >= inF && here < end) })
  return check(mergeGaps(next), inF, `Extracted ${end - inF} frames (${inF}–${end}); later shots, production sound and music moved earlier.`)
}
// ---- Audition in context: what Place would produce, cut down to a window around the take. Nothing is written.
export type AuditionPart = 'outgoing' | 'take' | 'incoming'
export interface AuditionVideo { start: number; frames: number; assetId: string | null; sourceIn: number; part: AuditionPart }
export interface AuditionAudio { start: number; frames: number; assetId: string; sourceIn: number; gainDb: number; role: 'production' | 'music' }
export type AuditionWindow = { ok: true; video: AuditionVideo[]; audio: AuditionAudio[]; length: number; takeStart: number; takeFrames: number } | { ok: false; error: string }
/** Place the take on copies (same rules as Place), then keep [at - pad, at + take + pad). Times are relative to the window start. */
export function auditionWindow(shots: readonly EditShot[], tracks: readonly TrackLike[], at: number, take: TakeMedia, policy: 'preserve' | 'ripple', pad = 48): AuditionWindow {
  const r = placeTake(shots, tracks, at, take, policy)
  if (!r.ok) return r
  const from = Math.max(0, at - pad), to = Math.min(total(r.shots), at + take.frames + pad)
  const video: AuditionVideo[] = []
  let s0 = 0
  for (const s of r.shots) {
    const a = Math.max(s0, from), b = Math.min(s0 + s.duration_frames, to)
    if (b > a) video.push({ start: a - from, frames: b - a, assetId: isGap(s) ? null : s.asset_id, sourceIn: isGap(s) ? 0 : s.source_in_frame + (a - s0), part: a < at ? 'outgoing' : a < at + take.frames ? 'take' : 'incoming' })
    s0 += s.duration_frames
  }
  const audio: AuditionAudio[] = []
  for (const t of r.tracks) {
    if (!t.enabled) continue
    const a = Math.max(t.start_frame, from), b = Math.min(t.start_frame + t.duration_frames, to)
    if (b > a) audio.push({ start: a - from, frames: b - a, assetId: t.asset_id, sourceIn: t.source_in_frame + (a - t.start_frame), gainDb: t.gain_db, role: t.role })
  }
  return { ok: true, video, audio, length: to - from, takeStart: at - from, takeFrames: take.frames }
}