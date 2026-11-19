import type { GenerationPlacement } from './GenerationFlow'

/** Steps of the generation guide, worked out from the take's real state (pure; checked by checks/guideSteps.check.ts).
 *  No review step since 2026-11-19 (Boden): a finished take imports by itself and can go straight on the timeline. */
export type GuideTarget = 'brief' | 'destination' | 'generate' | 'job' | 'import' | 'place' | 'save'
export type GuideStatus = 'done' | 'current' | 'todo'
export interface GuideStep { id: GuideTarget; title: string; what: string; status: GuideStatus; note?: string }

export interface GuideInput {
  placement: GenerationPlacement | null
  /** The Generate form has a brief. */
  hasBrief: boolean
  /** The user pressed Next on the brief / destination steps (only matters before the take is requested). */
  briefConfirmed?: boolean
  whereConfirmed?: boolean
  /** A Generate-tab take placed by the editor (Insert, then Save) rather than through a server reservation. */
  client?: boolean
  /** Its picture is in the open sequence (saved or not). */
  inTimeline?: boolean
  /** Its picture is in a saved sequence. */
  savedPlaced?: boolean
}

const ACTIVE = ['pending', 'submitting', 'queued', 'running', 'polling', 'importing']
const FAILED = ['failed', 'canceled']
const UNKNOWN = ['unknown', 'submission_unknown', 'result_unconfirmed']

const TEXT: Record<GuideTarget, [string, string]> = {
  brief: ['Describe the shot', 'Write what happens, how the camera sees it, and what it sounds like, and set its length. This is the same brief as in the Generate tab; reference frames are added there.'],
  destination: ['Say where it should go', 'Choose the spot. A small flag marks it on V1. Nothing goes on the timeline until you place the clip.'],
  generate: ['Generate', 'This checks the worker first and sends the request only if the check passes. If the check shows warnings, read them; a second click sends it anyway.'],
  job: ['Wait for the worker', 'The take renders on your ComfyUI worker (a few minutes). Keep editing; this step ticks itself when the worker finishes.'],
  import: ['It appears in the Browser', 'A finished take copies itself (picture and its sound) into the Browser. If that failed, its card in the Queue tab says why and offers Import.'],
  place: ['Place it on the timeline', 'Drag it from the Browser onto the timeline, or use Insert (F9). Picture and its sound go in together as an unsaved edit. Ctrl+Z undoes it.'],
  save: ['Save the sequence', 'Saving keeps the take in the sequence. It saves every unsaved edit in this sequence, not only this one.'],
}
const SERVER_PLACE = 'This take has a reserved spot. On its card in the Queue tab, confirm the position and click Place clip; that saves a new revision.'

export function guideSteps(i: GuideInput): GuideStep[] {
  const p = i.placement
  const stage = p?.stage ?? 'new'
  const generated = !!p
  const failed = generated && FAILED.includes(stage)
  const lost = generated && UNKNOWN.includes(stage)
  const finished = generated && !ACTIVE.includes(stage) && !failed && !lost
  const imported = !!(p?.video_asset_id ?? p?.job.video_asset_id)
  const serverPlaced = p?.placed_revision !== null && p?.placed_revision !== undefined
  const client = p ? !!i.client : i.client !== false // a new take is placed by the editor unless it is a continuation / planned take
  const saved = client ? !!i.savedPlaced : serverPlaced
  const placed = client ? saved || !!i.inTimeline : serverPlaced
  const order: [GuideTarget, boolean][] = [
    ['brief', generated || i.hasBrief && !!i.briefConfirmed],
    ['destination', generated || !!i.whereConfirmed],
    ['generate', generated],
    ['job', finished || imported],
    ['import', imported],
    ['place', placed],
  ]
  if (client) order.push(['save', saved])
  const firstOpen = order.findIndex(([, done]) => !done)
  return order.map(([id, done], n) => {
    const status: GuideStatus = done ? 'done' : n === firstOpen ? 'current' : 'todo'
    let note: string | undefined
    if (id === 'job' && failed) note = 'This request did not finish. Change the brief or seed and generate again.'
    if (id === 'job' && lost) note = 'The worker’s state for this request is unknown. Check the existing job (it does not resubmit).'
    if (id === 'place' && stage === 'conflict') note = 'The sequence changed since you asked. On the card, confirm the new position before placing.'
    if (id === 'save' && !done && i.inTimeline) note = 'Placed, not saved yet.'
    const what = id === 'place' && !client ? SERVER_PLACE : TEXT[id][1]
    return { id, title: TEXT[id][0], what, status, note }
  })
}
