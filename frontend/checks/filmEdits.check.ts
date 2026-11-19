// Run: node frontend/checks/filmEdits.check.ts   (Node 22.6+ strips the types; outside tsconfig "include", so the build ignores it)
import assert from 'node:assert/strict'
import { addEdit, auditionWindow, cutAudioRange, editPointFrame, extendEdit, extractRange, fitToPicture, gap, liftRange, moveClip, nearestCut, placeTake, resolveSpot, snapFrame, insertEdit, isGap, liftEdit, mergeGaps, nearestEditPoint, overwriteEdit, replaceEdit, rippleDelete, slipEdit, splitAt, trimEdit } from '../src/filmEdits.ts'
import type { EditResult, EditShot } from '../src/filmEdits.ts'

const v = (id: string, len: number, sourceIn = 0, asset = 'A'): EditShot => ({ id, asset_id: asset, source_in_frame: sourceIn, duration_frames: len })
const ok = (r: EditResult) => { assert.ok(r.ok, r.ok ? '' : r.error); return r as Extract<EditResult, { ok: true }> }
const len = (s: readonly EditShot[]) => s.reduce((n, x) => n + x.duration_frames, 0)
/** What the server accepts: gaps carry only id/kind/duration; every item >= 1 frame. */
function wellFormed(shots: readonly EditShot[]) {
  for (const s of shots) {
    assert.ok(Number.isInteger(s.duration_frames) && s.duration_frames >= 1, `bad duration ${JSON.stringify(s)}`)
    if (isGap(s)) assert.deepEqual(Object.keys(s).sort(), ['duration_frames', 'id', 'kind'])
    else assert.ok(Number.isInteger(s.source_in_frame) && s.source_in_frame >= 0)
  }
  assert.equal(new Set(shots.map(s => s.id)).size, shots.length, 'ids unique')
}
let n = 0; const test = (name: string, fn: () => void) => { fn(); n++; console.log('ok', name) }

test('split a gap gives two clean gaps', () => {
  const out = splitAt([v('a', 10), gap(20, 'g'), v('b', 5)], 18)
  wellFormed(out)
  assert.deepEqual(out.map(s => [s.kind ?? 'video', s.duration_frames]), [['video', 10], ['gap', 8], ['gap', 12], ['video', 5]])
  assert.equal(out[1].id, 'g')
})
test('lift leaves a same-length gap and keeps later shots in place', () => {
  const r = ok(liftEdit([v('a', 10), v('b', 6), v('c', 4)], 'b'))
  wellFormed(r.shots); assert.equal(len(r.shots), 20)
  assert.deepEqual(r.shots.map(s => s.kind ?? s.id), ['a', 'gap', 'c']); assert.equal(r.playhead, 10)
})
test('lift next to a gap merges the gaps', () => {
  const r = ok(liftEdit([v('a', 10), gap(3, 'g'), v('b', 6), v('c', 4)], 'b'))
  wellFormed(r.shots); assert.deepEqual(r.shots.map(s => [s.kind ?? 'video', s.duration_frames]), [['video', 10], ['gap', 9], ['video', 4]])
})
test('lift on a gap is refused', () => { assert.equal(liftEdit([gap(3, 'g')], 'g').ok, false) })
test('overwrite past the end pads with a gap', () => {
  const r = ok(overwriteEdit([v('a', 10)], 15, 'B', 2, 6))
  wellFormed(r.shots); assert.deepEqual(r.shots.map(s => [s.kind ?? 'video', s.duration_frames]), [['video', 10], ['gap', 5], ['video', 6]]); assert.equal(r.playhead, 21)
})
test('insert past the end pads with a gap', () => {
  const r = ok(insertEdit([v('a', 10)], 12, 'B', 0, 4))
  wellFormed(r.shots); assert.equal(len(r.shots), 16); assert.equal(r.shots[1].kind, 'gap')
})
test('insert in the middle of a gap splits it and ripples', () => {
  const r = ok(insertEdit([v('a', 10), gap(10, 'g'), v('b', 5)], 14, 'B', 0, 3))
  wellFormed(r.shots); assert.deepEqual(r.shots.map(s => [s.kind ?? 'video', s.duration_frames]), [['video', 10], ['gap', 4], ['video', 3], ['gap', 6], ['video', 5]])
})
test('overwrite exactly over a gap fills it', () => {
  const r = ok(overwriteEdit([v('a', 10), gap(5, 'g'), v('b', 5)], 10, 'B', 0, 5))
  wellFormed(r.shots); assert.ok(!r.shots.some(isGap)); assert.equal(len(r.shots), 20)
})
test('overwrite part of a gap keeps the rest', () => {
  const r = ok(overwriteEdit([v('a', 10), gap(8, 'g'), v('b', 5)], 12, 'B', 0, 3))
  wellFormed(r.shots); assert.deepEqual(r.shots.map(s => [s.kind ?? 'video', s.duration_frames]), [['video', 10], ['gap', 2], ['video', 3], ['gap', 3], ['video', 5]])
})
test('replace over a gap is refused', () => {
  assert.equal(replaceEdit([v('a', 10), gap(5, 'g')], 12, { id: 'B', status: 'approved', frame_count: 100 }, 20).ok, false)
})
test('ripple delete of a gap closes up and merges neighbours', () => {
  const r = ok(rippleDelete([gap(2, 'g1'), v('a', 4), gap(3, 'g2')], 'a'))
  wellFormed(r.shots); assert.deepEqual(r.shots.map(s => [s.kind, s.duration_frames]), [['gap', 5]])
})
test('mergeGaps drops zero-length items', () => {
  assert.deepEqual(mergeGaps([gap(0, 'x'), v('a', 2)]).map(s => s.id), ['a'])
})
// ---- slice B: trims
const counts = (id: string) => ({ A: 100, B: 50 } as Record<string, number>)[id]
const base = (): EditShot[] => [v('a', 20, 10, 'A'), v('b', 20, 5, 'B'), gap(10, 'g'), v('c', 15, 0, 'A')]
const shape = (s: readonly EditShot[]) => s.map(x => isGap(x) ? `g${x.duration_frames}` : `${x.id}${x.source_in_frame}+${x.duration_frames}`).join(' ')
test('razor cuts at the playhead and refuses an existing cut', () => {
  const r = ok(addEdit(base(), 30)); wellFormed(r.shots); assert.equal(r.shots.length, 5); assert.equal(len(r.shots), 65)
  assert.equal(addEdit(base(), 20).ok, false); assert.equal(addEdit(base(), 0).ok, false); assert.equal(addEdit(base(), 65).ok, false)
})
test('razor in a gap is refused (no picture to cut)', () => { assert.equal(addEdit(base(), 45).ok, false) })
test('extend edit refuses an In-side selection', () => {
  assert.equal(extendEdit(base(), { leftId: 'a', rightId: 'b', side: 'right' }, 26, counts).ok, false)
  const r = ok(extendEdit(base(), { leftId: 'a', rightId: 'b', side: 'left' }, 26, counts)); assert.equal(len(r.shots), 71)
})
test('fit: shorter picture with no fixed duration drops markers past the end and clamps In/Out', () => {
  const f = fitToPicture({ picture: 114, explicit: undefined, audioEnd: 0, markers: [{ id: 'm1', label: 'a', frame: 50 }, { id: 'm2', label: 'b', frame: 120 }], selection: { in_frame: 100, out_frame: 124 } })
  assert.equal(f.duration, undefined); assert.deepEqual(f.markers.map(m => m.id), ['m1']); assert.deepEqual(f.selection, { in_frame: 100, out_frame: 114 }); assert.match(f.note, /1 marker/)
})
test('fit: In past the new end clears the selection', () => {
  assert.equal(fitToPicture({ picture: 90, explicit: undefined, audioEnd: 0, markers: [], selection: { in_frame: 100, out_frame: 124 } }).selection, null)
})
test('fit: placed audio past the end holds the length', () => {
  const f = fitToPicture({ picture: 90, explicit: undefined, audioEnd: 120, markers: [{ id: 'm', label: 'x', frame: 110 }], selection: null })
  assert.equal(f.duration, 120); assert.equal(f.markers.length, 1); assert.match(f.note, /audio/)
})
test('fit: a fixed duration is left alone; a longer picture extends it', () => {
  const same = fitToPicture({ picture: 90, explicit: 352, audioEnd: 0, markers: [{ id: 'm', label: 'x', frame: 300 }], selection: null })
  assert.equal(same.duration, undefined); assert.equal(same.markers.length, 1)
  assert.equal(fitToPicture({ picture: 400, explicit: 352, audioEnd: 0, markers: [], selection: null }).duration, 400)
})
test('roll moves the cut, keeps length, moves source of the right shot', () => {
  const r = ok(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'both' }, 3, counts))
  assert.equal(shape(r.shots), 'a10+23 b8+17 g10 c0+15'); assert.equal(len(r.shots), 65); assert.equal(r.playhead, 23)
})
test('roll is refused past the end of a take', () => {
  assert.equal(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'both' }, -6, counts).ok, false) // b would need source In -1
  assert.equal(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'both' }, 71, counts).ok, false)
})
test('roll into a gap changes only the gap length', () => {
  const r = ok(trimEdit(base(), { leftId: 'b', rightId: 'g', side: 'both' }, 4, counts)); assert.equal(shape(r.shots), 'a10+20 b5+24 g6 c0+15')
})
test('roll refuses to shrink a gap to nothing', () => { assert.equal(trimEdit(base(), { leftId: 'b', rightId: 'g', side: 'both' }, 10, counts).ok, false) })
test('ripple left changes total by delta', () => {
  const r = ok(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'left' }, -5, counts)); assert.equal(shape(r.shots), 'a10+15 b5+20 g10 c0+15'); assert.equal(len(r.shots), 60); assert.equal(r.playhead, 15)
})
test('ripple right moves the In and keeps the cut frame', () => {
  const r = ok(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'right' }, 4, counts)); assert.equal(shape(r.shots), 'a10+20 b9+16 g10 c0+15'); assert.equal(r.playhead, 20)
  assert.equal(trimEdit(base(), { leftId: 'a', rightId: 'b', side: 'right' }, -6, counts).ok, false)
})
test('ripple the end of the picture', () => {
  const r = ok(trimEdit(base(), { leftId: 'c', rightId: null, side: 'left' }, 10, counts)); assert.equal(len(r.shots), 75)
  assert.equal(trimEdit(base(), { leftId: 'c', rightId: null, side: 'left' }, -15, counts).ok, false)
})
test('slip moves the source range only', () => {
  const r = ok(slipEdit(base(), 'b', 25, counts)); assert.equal(shape(r.shots), 'a10+20 b30+20 g10 c0+15')
  assert.equal(slipEdit(base(), 'b', 26, counts).ok, false); assert.equal(slipEdit(base(), 'b', -6, counts).ok, false); assert.equal(slipEdit(base(), 'g', 1, counts).ok, false)
})
test('select edit and extend edit', () => {
  const p = nearestEditPoint(base(), 22)!; assert.deepEqual(p, { leftId: 'a', rightId: 'b', side: 'both' })
  assert.deepEqual(nearestEditPoint(base(), 1)!.side, 'right')
  const r = ok(extendEdit(base(), p, 26, counts)); assert.equal(editPointFrame(r.shots, p), 26); assert.equal(len(r.shots), 65)
})
test('random mixed edits stay well formed (seeded)', () => {
  let seed = 271828; const rnd = (m: number) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % m }
  let shots = base(); let applied = 0
  for (let i = 0; i < 600; i++) {
    const before = len(shots), op = rnd(6), k = rnd(shots.length + 1)
    const point = { leftId: shots[k - 1]?.id ?? null, rightId: shots[k]?.id ?? null, side: (['left', 'both', 'right'] as const)[rnd(3)] }
    const delta = rnd(21) - 10, target = shots[rnd(shots.length)]
    const r = op === 0 ? addEdit(shots, rnd(before + 1)) : op === 1 ? slipEdit(shots, target.id, delta, counts) : op === 5 ? liftEdit(shots, target.id) : trimEdit(shots, point, delta, counts)
    if (!r.ok) continue
    wellFormed(r.shots)
    for (const s of r.shots) if (!isGap(s)) assert.ok(s.source_in_frame + s.duration_frames <= counts(s.asset_id)!, 'source bound')
    const effectiveSide = point.side === 'both' && (!point.leftId || !point.rightId) ? (point.leftId ? 'left' : 'right') : point.side
    if (op === 1 || op === 5 || (op >= 2 && op <= 4 && effectiveSide === 'both')) assert.equal(len(r.shots), before, `length kept by op ${op}`)
    if (op >= 2 && op <= 4 && effectiveSide !== 'both') assert.equal(len(r.shots), before + (effectiveSide === 'left' ? delta : -delta), 'ripple delta')
    shots = r.shots; applied++
    if (shots.length > 40) shots = base()
  }
  assert.ok(applied > 150, `only ${applied} edits applied`)
})
// ---- drag to move + snapping
const row = (): EditShot[] => [v('a', 10, 0, 'A'), v('b', 20, 0, 'B'), v('c', 15, 0, 'A')]
test('overwrite move leaves a gap and covers the destination; id kept', () => {
  const r = ok(moveClip(row(), 'a', 30, 'overwrite')); wellFormed(r.shots)
  assert.match(shape(r.shots), /^g10 b0\+20 a0\+10 \S+10\+5$/); assert.equal(r.playhead, 30); assert.equal(len(r.shots), 45)
})
test('overwrite move past the end pads with a gap and drops trailing gaps', () => {
  const r = ok(moveClip(row(), 'c', 50, 'overwrite')); wellFormed(r.shots); assert.equal(shape(r.shots), 'a0+10 b0+20 g20 c0+15')
  const back = ok(moveClip(r.shots, 'c', 30, 'overwrite')); assert.equal(shape(back.shots), 'a0+10 b0+20 c0+15')
})
test('rearrange (insert move) closes up and keeps length', () => {
  const r = ok(moveClip(row(), 'a', 30, 'insert')); wellFormed(r.shots); assert.equal(shape(r.shots), 'b0+20 a0+10 c0+15'); assert.equal(len(r.shots), 45)
  const r2 = ok(moveClip(row(), 'c', 0, 'insert')); assert.equal(shape(r2.shots), 'c0+15 a0+10 b0+20')
  assert.equal(moveClip(row(), 'a', 10, 'insert').ok, false)
})
test('a deliberate trailing gap survives a move', () => {
  const r = ok(moveClip([v('a', 10, 0, 'A'), v('b', 20, 0, 'B'), gap(8, 'tail')], 'a', 30, 'insert')); assert.equal(shape(r.shots), 'b0+20 a0+10 g8')
})
test('gaps cannot be dragged; negative start refused', () => {
  assert.equal(moveClip([v('a', 5), gap(5, 'g')], 'g', 0, 'overwrite').ok, false); assert.equal(moveClip(row(), 'b', -1, 'overwrite').ok, false)
})
test('snapping picks the nearest target within tolerance', () => {
  assert.deepEqual(snapFrame(28, [0, 10, 30, 45], 3), { frame: 30, snapped: true }); assert.deepEqual(snapFrame(20, [0, 10, 30], 3), { frame: 20, snapped: false })
  assert.equal(nearestCut(row(), 26), 30); assert.equal(nearestCut(row(), 4), 0)
})
test('random moves stay well formed and keep sources', () => {
  let seed = 31337; const rnd = (m: number) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % m }
  let shots = row()
  for (let i = 0; i < 300; i++) {
    const vids = shots.filter(s => !isGap(s)); const s = vids[rnd(vids.length)] as Extract<EditShot, { asset_id: string }>
    const mode = rnd(2) ? 'overwrite' : 'insert', to = mode === 'insert' ? nearestCut(shots, rnd(len(shots) + 20)) : rnd(len(shots) + 20)
    const r = moveClip(shots, s.id, to, mode); if (!r.ok) continue
    wellFormed(r.shots); const moved = r.shots.find(x => x.id === s.id)
    assert.ok(moved && !isGap(moved) && moved.source_in_frame === s.source_in_frame && moved.duration_frames === s.duration_frames, 'moved shot keeps id and source')
    if (mode === 'insert') assert.ok(len(r.shots) <= len(shots), 'a rearrange never lengthens the picture')
    shots = r.shots
  }
})
// ---- Generate tab: spots and placing a take
const seqShots = (): EditShot[] => [v('a', 10, 0, 'A'), v('b', 20, 0, 'B'), gap(5, 'g'), v('c', 15, 0, 'A')]
const trk = (id: string, start: number, len: number, role: 'production' | 'music' = 'music') => ({ id, role, asset_id: 'M', start_frame: start, source_in_frame: 0, duration_frames: len, gain_db: 0, fade_in_frames: 0, fade_out_frames: 0, enabled: true })
test('spots resolve from clip ids, playhead and end', () => {
  const s = (o: Partial<Parameters<typeof resolveSpot>[1]>) => resolveSpot(seqShots(), { sequence_id: 'q', kind: 'end', ...o }, 7)
  assert.deepEqual(s({ kind: 'before', clipId: 'b' }), { frame: 10, splits: false, note: 'before “the clip”' })
  assert.equal((s({ kind: 'after', clipId: 'b' }) as { frame: number }).frame, 30)
  assert.equal((s({ kind: 'end' }) as { frame: number }).frame, 50)
  const p = s({ kind: 'playhead', frame: 15 }) as { frame: number; splits: boolean }; assert.equal(p.frame, 15); assert.equal(p.splits, true)
  assert.equal((s({ kind: 'playhead', frame: 32 }) as { splits: boolean }).splits, false) // in a gap: no shot is split
  assert.ok('error' in s({ kind: 'after', clipId: 'gone' }))
})
test('placing a take inserts picture and its sound together; ripple moves later audio', () => {
  const r = placeTake(seqShots(), [trk('m1', 5, 40), trk('m2', 30, 10)], 30, { videoAssetId: 'T', frames: 24, audioAssetId: 'S', audioFrames: 30 }, 'ripple')
  assert.ok(r.ok); if (!r.ok) return
  wellFormed(r.shots); assert.equal(len(r.shots), 74)
  assert.deepEqual(r.tracks.map(t => [t.id.length > 8 ? 'new' : t.id, t.start_frame, t.duration_frames]), [['m1', 5, 40], ['m2', 54, 10], ['new', 30, 24]])
  assert.equal(r.tracks.at(-1)!.role, 'production')
  const keep = placeTake(seqShots(), [trk('m2', 30, 10)], 30, { videoAssetId: 'T', frames: 24, audioAssetId: 'S', audioFrames: 12 }, 'preserve')
  assert.ok(keep.ok); if (!keep.ok) return
  assert.deepEqual(keep.tracks.map(t => [t.start_frame, t.duration_frames]), [[30, 10], [30, 12]]) // sound shorter than picture: placed at its own length
})
test('placing a take mid-shot splits the shot; past the end pads with a gap', () => {
  const mid = placeTake(seqShots(), [], 15, { videoAssetId: 'T', frames: 6 }, 'preserve'); assert.ok(mid.ok); if (!mid.ok) return
  assert.match(shape(mid.shots), /^a0\+10 b0\+5 \S+0\+6 \S+5\+15 g5 c0\+15$/)
  const past = placeTake(seqShots(), [], 60, { videoAssetId: 'T', frames: 6 }, 'preserve'); assert.ok(past.ok); if (!past.ok) return
  assert.match(shape(past.shots), /g10 \S+0\+6$/)
})
// ---- Lift (;) / Extract (') In to Out
test('lift splits shots at In and Out and leaves a gap', () => {
  const r = ok(liftRange(seqShots(), 5, 20)); wellFormed(r.shots)
  assert.match(shape(r.shots), /^a0\+5 g15 \S+10\+10 g5 c0\+15$/); assert.equal(len(r.shots), 50); assert.equal(r.playhead, 5)
})
test('extract splits and closes up', () => {
  const r = ok(extractRange(seqShots(), 5, 20)); wellFormed(r.shots)
  assert.match(shape(r.shots), /^a0\+5 \S+10\+10 g5 c0\+15$/); assert.equal(len(r.shots), 35)
})
test('range across a gap and the end; refusals', () => {
  const r = ok(extractRange(seqShots(), 28, 60)); assert.match(shape(r.shots), /^a0\+10 b0\+18$/)
  assert.equal(liftRange(seqShots(), 20, 20).ok, false); assert.equal(extractRange(seqShots(), 50, 60).ok, false)
})
test('production sound and music are cut with the range', () => {
  const tracks = [trk('p1', 0, 30, 'production'), trk('p2', 40, 10, 'production'), trk('m', 0, 50), trk('m2', 10, 5)]
  const lift = cutAudioRange(tracks, 5, 20, false)
  assert.deepEqual(lift.map(t => [t.role[0], t.start_frame, t.source_in_frame, t.duration_frames]), [['p', 0, 0, 5], ['p', 20, 20, 10], ['p', 40, 0, 10], ['m', 0, 0, 5], ['m', 20, 20, 30]])
  const ext = cutAudioRange(tracks, 5, 20, true)
  assert.deepEqual(ext.map(t => [t.role[0], t.start_frame, t.source_in_frame, t.duration_frames]), [['p', 0, 0, 5], ['p', 5, 20, 10], ['p', 25, 0, 10], ['m', 0, 0, 5], ['m', 5, 20, 30]])
  const faded = cutAudioRange([{ ...trk('f', 0, 30, 'production'), fade_in_frames: 8, fade_out_frames: 12 }], 5, 25, false)
  for (const t of faded) assert.ok(t.fade_in_frames + t.fade_out_frames <= t.duration_frames, 'fades fit')
})
// ---- Audition in context
test('audition: take placed mid-shot, 2 s either side, sources continue across the split', () => {
  const shots = [v('a', 100, 0, 'A'), v('b', 100, 0, 'B')]
  const w = auditionWindow(shots, [trk('m', 0, 200)], 60, { videoAssetId: 'T', frames: 24, audioAssetId: 'S', audioFrames: 24 }, 'ripple')
  assert.ok(w.ok); if (!w.ok) return
  assert.deepEqual(w.video.map(x => [x.start, x.frames, x.assetId, x.sourceIn, x.part]), [[0, 48, 'A', 12, 'outgoing'], [48, 24, 'T', 0, 'take'], [72, 40, 'A', 60, 'incoming'], [112, 8, 'B', 0, 'incoming']])
  assert.equal(w.length, 120); assert.equal(w.takeStart, 48)
  assert.deepEqual(w.audio.map(x => [x.start, x.frames, x.assetId, x.sourceIn]), [[0, 120, 'M', 12], [48, 24, 'S', 0]]) // a music bed already playing carries on under the take, as Place does
})
test('audition at the very start and across a gap', () => {
  const w = auditionWindow(seqShots(), [], 0, { videoAssetId: 'T', frames: 10 }, 'preserve'); assert.ok(w.ok); if (!w.ok) return
  assert.equal(w.video[0].part, 'take'); assert.equal(w.takeStart, 0)
  const g = auditionWindow(seqShots(), [], 30, { videoAssetId: 'T', frames: 10 }, 'preserve'); assert.ok(g.ok); if (!g.ok) return
  assert.deepEqual(g.video.map(x => [x.assetId, x.frames, x.part]), [['A', 10, 'outgoing'], ['B', 20, 'outgoing'], ['T', 10, 'take'], [null, 5, 'incoming'], ['A', 15, 'incoming']])
})
console.log(`${n} checks passed`)
