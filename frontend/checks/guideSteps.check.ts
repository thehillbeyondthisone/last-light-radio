// Run: node frontend/checks/guideSteps.check.ts
import assert from 'node:assert/strict'
import { guideSteps } from '../src/guideSteps.ts'
import type { GuideInput } from '../src/guideSteps.ts'
import type { GenerationPlacement } from '../src/GenerationFlow'

const take = (stage: string, extra: Partial<GenerationPlacement> = {}, job: Partial<GenerationPlacement['job']> = {}): GenerationPlacement =>
  ({ job_id: 'j1', job: { id: 'j1', label: 'Take', status: stage, ...job }, stage, placed_revision: null, destination: { sequence_id: 's1', expected_revision: 0, track: 'V1' }, ...extra })
const current = (i: GuideInput) => guideSteps(i).find(s => s.status === 'current')?.id ?? 'all-done'
const ids = (i: GuideInput) => guideSteps(i).map(s => s.id).join(',')
let n = 0
const is = (i: GuideInput, want: string, why: string) => { assert.equal(current(i), want, why); n++ }

// A new take: brief, then where, then generate; typing a brief alone does not jump ahead.
is({ placement: null, hasBrief: false }, 'brief', 'new take starts at the brief')
is({ placement: null, hasBrief: true }, 'brief', 'a brief needs Next before moving on')
is({ placement: null, hasBrief: true, briefConfirmed: true }, 'destination', 'brief confirmed')
is({ placement: null, hasBrief: false, briefConfirmed: true }, 'brief', 'clearing the brief goes back')
is({ placement: null, hasBrief: true, briefConfirmed: true, whereConfirmed: true }, 'generate', 'ready to generate')
assert.equal(ids({ placement: null, hasBrief: false }), 'brief,destination,generate,job,import,place,save', 'no review step (2026-11-19)'); n++
assert.equal(ids({ placement: null, hasBrief: false, client: false }), 'brief,destination,generate,job,import,place', 'a new continuation take has no Save step'); n++
// Requested, running, failed, unknown.
is({ placement: take('queued'), hasBrief: false, client: true }, 'job', 'requested: brief and spot count as done')
is({ placement: take('running'), hasBrief: false, client: true }, 'job', 'running')
{ const s = guideSteps({ placement: take('failed'), hasBrief: false, client: true }).find(x => x.id === 'job')!; assert.equal(s.status, 'current'); assert.match(s.note ?? '', /did not finish/); n++ }
{ const s = guideSteps({ placement: take('submission_unknown'), hasBrief: false, client: true }).find(x => x.id === 'job')!; assert.equal(s.status, 'current'); assert.match(s.note ?? '', /unknown/); n++ }
// Finished, imported (no review step: imported means it can be placed).
is({ placement: take('awaiting_import', {}, { ready_to_import: true }), hasBrief: false, client: true }, 'import', 'finished, import failed or pending')
const imported = take('ready_to_place', { video_asset_id: 'v1', audio_asset_id: 'a1' })
is({ placement: imported, hasBrief: false, client: true }, 'place', 'imported: place next')
is({ placement: take('ready_to_place', { video_asset_id: 'v1' }), hasBrief: false, client: true }, 'place', 'picture-only take')
// Client take: placed (unsaved) then saved.
is({ placement: imported, hasBrief: false, client: true, inTimeline: true }, 'save', 'placed, not saved')
{ const s = guideSteps({ placement: imported, hasBrief: false, client: true, inTimeline: true }).find(x => x.id === 'save')!; assert.match(s.note ?? '', /not saved/); n++ }
is({ placement: imported, hasBrief: false, client: true, inTimeline: true, savedPlaced: true }, 'all-done', 'saved: all done')
// Server-reserved take: no Save step (Place saves a revision); conflict note; placed_revision finishes it.
const server = take('ready_to_place', { video_asset_id: 'v1', audio_asset_id: 'a1' })
assert.equal(ids({ placement: server, hasBrief: true }), 'brief,destination,generate,job,import,place'); n++
is({ placement: server, hasBrief: true }, 'place', 'server take ready to place')
assert.match(guideSteps({ placement: server, hasBrief: true }).find(x => x.id === 'place')!.what, /reserved spot/); n++
assert.match(guideSteps({ placement: take('conflict', { video_asset_id: 'v1' }), hasBrief: true }).find(x => x.id === 'place')!.note ?? '', /changed/); n++
is({ placement: { ...server, placed_revision: 4 }, hasBrief: true }, 'all-done', 'server placement done')
console.log(`guideSteps: ${n} checks passed`)
