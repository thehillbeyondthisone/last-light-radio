// Run: node frontend/checks/clipLength.check.ts
import assert from 'node:assert/strict'
import { framesFor, framesForInterval, lengthNote, limitOf, rulesOf } from '../src/clipLength.ts'

let n = 0
const ok = (cond: unknown, why: string) => { assert.ok(cond, why); n++ }
const h3 = rulesOf({ frames: 124, fps: 24, min_frames: 48, max_frames: 240, frame_step: 4, proven_frames: [124] })
const old = rulesOf({ frames: 124, fps: 24 })

ok(h3.adjustable && !old.adjustable, 'older server recipe has a fixed length')
assert.equal(limitOf(h3, null), 124, 'default limit is the proven length'); n++
assert.equal(limitOf(h3, 1000), 240, 'limit never exceeds the server ceiling'); n++
assert.equal(limitOf(h3, 10), 48, 'limit never below the minimum'); n++
assert.equal(limitOf(h3, 150), 152, 'limit snaps to the frame step'); n++
const lim = limitOf(h3, null)
assert.equal(framesFor(5, h3, lim), 120, '5 s → 120 frames'); n++
assert.equal(framesFor(5.17, h3, lim), 124, '5.17 s → 124 frames'); n++
assert.equal(framesFor(8, h3, lim), 124, 'longer than the limit is capped'); n++
assert.equal(framesFor(8, h3, 192), 192, 'a raised limit allows 8 s'); n++
assert.equal(framesFor(1, h3, lim), 48, 'shorter than the minimum is raised'); n++
assert.equal(framesFor(NaN, h3, lim), 124, 'bad input falls back to the recipe length'); n++
assert.equal(framesFor(3, old, limitOf(old, null)), 124, 'fixed recipe always 124'); n++
assert.equal(framesForInterval(100, h3, lim), 100, 'interval already on the step'); n++
assert.equal(framesForInterval(101, h3, lim), 104, 'interval rounds up to cover it'); n++
assert.equal(framesForInterval(20, h3, lim), 48, 'short interval uses the minimum'); n++
assert.equal(framesForInterval(130, h3, lim), null, 'interval past the limit cannot be made'); n++
for (const s of [2, 3.3, 4, 5, 6.1]) { const f = framesFor(s, h3, lim); ok(f % 4 === 0 && f >= 48 && f <= lim, `legal frames for ${s}s`) }
assert.equal(lengthNote(124, h3), null, 'proven length has no note'); n++
assert.match(lengthNote(96, h3) ?? '', /not been tested/); n++
console.log(`clipLength: ${n} checks passed`)
