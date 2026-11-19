// Clip length for a generated take (Boden, 2026-11-19). Pure; checked by checks/clipLength.check.ts.
// The server (h3_joint_av_recipe.frames) accepts min_frames..max_frames in steps of frame_step. Long AI clips drift and lose
// coherence, so the creator sets a lower "longest clip" limit in Generate › Settings (browser-local; default = the proven length).

export interface LengthRecipe { frames: number; fps: number; min_frames?: number; max_frames?: number; frame_step?: number; proven_frames?: number[] }
export interface LengthRules { min: number; max: number; step: number; fps: number; proven: number[]; fallback: number; adjustable: boolean }

export const LIMIT_KEY = 'llr.film.generation.lengthLimit.v1'

/** An older server without length support has a fixed length: the form then sends no length at all. */
export function rulesOf(r: LengthRecipe): LengthRules {
  const adjustable = typeof r.min_frames === 'number' && typeof r.max_frames === 'number'
  const step = adjustable && r.frame_step && r.frame_step > 0 ? r.frame_step : 1
  return { min: adjustable ? r.min_frames! : r.frames, max: adjustable ? r.max_frames! : r.frames, step, fps: r.fps, proven: r.proven_frames ?? [r.frames], fallback: r.frames, adjustable }
}
/** The creator's limit, snapped into the server's range (null/invalid = the longest proven length). */
export function limitOf(rules: LengthRules, stored: number | null): number {
  const proven = Math.max(...rules.proven)
  const v = stored !== null && Number.isFinite(stored) ? stored : proven
  return clampStep(v, rules, rules.max)
}
function clampStep(frames: number, rules: LengthRules, cap: number): number {
  const top = Math.max(rules.min, Math.min(cap, rules.max))
  const snapped = Math.round(frames / rules.step) * rules.step
  return Math.max(rules.min, Math.min(top - (top - rules.min) % rules.step, snapped))
}
/** Seconds typed or slid by the creator → a legal frame count no longer than the limit. */
export function framesFor(seconds: number, rules: LengthRules, limit: number): number {
  return clampStep(Number.isFinite(seconds) ? seconds * rules.fps : rules.fallback, rules, limit)
}
/** Shortest legal length that still covers a planned interval (null when it cannot within the limit). */
export function framesForInterval(interval: number, rules: LengthRules, limit: number): number | null {
  const need = Math.max(rules.min, Math.ceil(interval / rules.step) * rules.step)
  return need <= Math.min(limit, rules.max) ? need : null
}
/** A short honest note about the chosen length. */
export function lengthNote(frames: number, rules: LengthRules): string | null {
  if (rules.proven.includes(frames)) return null
  return `${frames} frames has not been tested with this recipe yet (${rules.proven.map(f => `${(f / rules.fps).toFixed(2)} s`).join(', ')} has). Check the result before relying on it.`
}
