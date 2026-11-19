// Run: node frontend/checks/shortcuts.check.ts
import assert from 'node:assert/strict'
import { COMMANDS, parseKeymapFile, serializeKeymap, defaultKeymap } from '../src/shortcuts.ts'

const file = (bindings: Record<string, string[]>, rev?: number) => JSON.stringify({ format: 'last-light-radio-keymap', version: 1, base: 'fcp7', ...(rev ? { defaults_rev: rev } : {}), bindings })
// Every command present, as a layout file of that time would have it.
const saved = (edit: Record<string, string[]> = {}): Record<string, string[]> => ({ ...Object.fromEntries(COMMANDS.filter(c => !c.id.endsWith('Range')).map(c => [c.id, [...c.keys]])), 'nav.prevEdit': ['Up'], 'nav.nextEdit': ['Down'], ...edit })

let n = 0
// Defaults: ; lifts, ' extracts; Up/Down are previous/next edit only.
{ const k = defaultKeymap(); assert.deepEqual(k['edit.liftRange'], [';']); assert.deepEqual(k['edit.extractRange'], ["'"]); assert.deepEqual(k['nav.prevEdit'], ['Up']); assert.deepEqual(k['nav.nextEdit'], ['Down']); n++ }
// A layout from before ; and ' existed (no defaults_rev) gets Lift / Extract.
{ const { keymap } = parseKeymapFile(file(saved())); assert.deepEqual(keymap['edit.liftRange'], [';']); assert.deepEqual(keymap['edit.extractRange'], ["'"]); n++ }
// A layout saved while ; and ' were previous/next edit (rev 2) is moved over.
{ const { keymap } = parseKeymapFile(file(saved({ 'nav.prevEdit': ['Up', ';'], 'nav.nextEdit': ['Down', "'"] }), 2))
  assert.deepEqual(keymap['nav.prevEdit'], ['Up']); assert.deepEqual(keymap['nav.nextEdit'], ['Down']); assert.deepEqual(keymap['edit.liftRange'], [';']); assert.deepEqual(keymap['edit.extractRange'], ["'"]); n++ }
// If the user gave ; to something else, it stays theirs.
{ const { keymap } = parseKeymapFile(file(saved({ 'mark.add': ['M', ';'] }))); assert.ok(keymap['mark.add'].includes(';')); assert.deepEqual(keymap['edit.liftRange'], []); n++ }
// A layout saved now is respected exactly (removing ' from Extract stays removed).
{ const k = defaultKeymap(); k['edit.extractRange'] = []; const { keymap } = parseKeymapFile(serializeKeymap(k)); assert.deepEqual(keymap['edit.extractRange'], []); n++ }
console.log(`${n} shortcut checks passed`)
