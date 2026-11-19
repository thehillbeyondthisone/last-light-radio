// Editor keyboard commands, Final Cut Pro 7 default bindings and keymap editing.
// Pure functions only (no DOM or React), so Node tests can import this file directly.

export type CommandGroup = 'Playback' | 'Navigation' | 'Marking' | 'Editing' | 'Timeline' | 'Windows'
export interface Command {
  id: string
  label: string
  short: string
  group: CommandGroup
  keys: readonly string[]
  /** fcp7: a Final Cut Pro 7 default. llr: a Last Light Radio command with no FCP7 equivalent. */
  origin: 'fcp7' | 'llr'
  /** Holding the key repeats the command (frame steps, nudges, shuttle speed). */
  repeat?: boolean
  /** Also works while typing in a text field (window switching, save, keyboard layout). */
  inText?: boolean
}
export type Keymap = Record<string, string[]>

export const GROUPS: readonly CommandGroup[] = ['Playback', 'Navigation', 'Marking', 'Editing', 'Timeline', 'Windows']

export const COMMANDS: readonly Command[] = [
  { id: 'play.toggle', label: 'Play / pause', short: 'Play', group: 'Playback', keys: ['Space'], origin: 'fcp7' },
  { id: 'play.reverse', label: 'Play reverse — press again for 2×, 4×, 8×', short: 'Rev', group: 'Playback', keys: ['J'], origin: 'fcp7', repeat: true },
  { id: 'play.stop', label: 'Stop — hold with J or L to step one frame', short: 'Stop', group: 'Playback', keys: ['K'], origin: 'fcp7' },
  { id: 'play.forward', label: 'Play forward — press again for 2×, 4×, 8×', short: 'Fwd', group: 'Playback', keys: ['L'], origin: 'fcp7', repeat: true },
  { id: 'play.inToOut', label: 'Play In to Out', short: 'In→Out', group: 'Playback', keys: ['Shift+\\'], origin: 'fcp7' },
  { id: 'play.around', label: 'Play around current frame (2 s each side)', short: 'Around', group: 'Playback', keys: ['\\'], origin: 'fcp7' },
  { id: 'play.loop', label: 'Loop playback on/off', short: 'Loop', group: 'Playback', keys: ['Ctrl+L'], origin: 'fcp7' },

  { id: 'nav.prevFrame', label: 'Previous frame', short: '−1f', group: 'Navigation', keys: ['Left'], origin: 'fcp7', repeat: true },
  { id: 'nav.nextFrame', label: 'Next frame', short: '+1f', group: 'Navigation', keys: ['Right'], origin: 'fcp7', repeat: true },
  { id: 'nav.back1s', label: 'Back one second', short: '−1s', group: 'Navigation', keys: ['Shift+Left'], origin: 'fcp7', repeat: true },
  { id: 'nav.fwd1s', label: 'Forward one second', short: '+1s', group: 'Navigation', keys: ['Shift+Right'], origin: 'fcp7', repeat: true },
  { id: 'nav.prevEdit', label: 'Previous edit', short: 'Prev edit', group: 'Navigation', keys: ['Up'], origin: 'fcp7', repeat: true },
  { id: 'nav.nextEdit', label: 'Next edit', short: 'Next edit', group: 'Navigation', keys: ['Down'], origin: 'fcp7', repeat: true },
  { id: 'nav.start', label: 'Go to start', short: 'Start', group: 'Navigation', keys: ['Home'], origin: 'fcp7' },
  { id: 'nav.end', label: 'Go to end', short: 'End', group: 'Navigation', keys: ['End'], origin: 'fcp7' },
  { id: 'nav.in', label: 'Go to In point', short: 'Go In', group: 'Navigation', keys: ['Shift+I'], origin: 'fcp7' },
  { id: 'nav.out', label: 'Go to Out point', short: 'Go Out', group: 'Navigation', keys: ['Shift+O'], origin: 'fcp7' },
  { id: 'nav.prevMarker', label: 'Previous marker', short: 'Prev mk', group: 'Navigation', keys: ['Shift+Up', 'Alt+M'], origin: 'fcp7', repeat: true },
  { id: 'nav.nextMarker', label: 'Next marker', short: 'Next mk', group: 'Navigation', keys: ['Shift+Down', 'Shift+M'], origin: 'fcp7', repeat: true },
  { id: 'nav.matchFrame', label: 'Match frame — open the take under the playhead in the Viewer', short: 'Match', group: 'Navigation', keys: ['F'], origin: 'fcp7' },
  { id: 'nav.prevTake', label: 'Previous take of this action', short: 'Prev take', group: 'Navigation', keys: ['PageUp'], origin: 'llr' },
  { id: 'nav.nextTake', label: 'Next take of this action', short: 'Next take', group: 'Navigation', keys: ['PageDown'], origin: 'llr' },

  { id: 'mark.in', label: 'Mark In', short: 'In', group: 'Marking', keys: ['I'], origin: 'fcp7' },
  { id: 'mark.out', label: 'Mark Out', short: 'Out', group: 'Marking', keys: ['O'], origin: 'fcp7' },
  { id: 'mark.clearIn', label: 'Clear In', short: 'Clr In', group: 'Marking', keys: ['Alt+I'], origin: 'fcp7' },
  { id: 'mark.clearOut', label: 'Clear Out', short: 'Clr Out', group: 'Marking', keys: ['Alt+O'], origin: 'fcp7' },
  { id: 'mark.clearBoth', label: 'Clear In and Out', short: 'Clr I/O', group: 'Marking', keys: ['Alt+X'], origin: 'fcp7' },
  { id: 'mark.clip', label: 'Mark clip — set In/Out around the segment under the playhead and select it', short: 'Mark clip', group: 'Marking', keys: ['X'], origin: 'fcp7' },
  { id: 'mark.add', label: 'Add marker', short: 'Marker', group: 'Marking', keys: ['M'], origin: 'fcp7' },
  { id: 'mark.delete', label: 'Delete marker at playhead', short: 'Del mk', group: 'Marking', keys: ['Ctrl+`'], origin: 'fcp7' },
  { id: 'mark.deleteAll', label: 'Delete all markers', short: 'Del all mk', group: 'Marking', keys: ['Ctrl+Shift+`'], origin: 'fcp7' },

  { id: 'edit.overwrite', label: 'Overwrite — place the Viewer take at In, or at the playhead', short: 'Overwrite', group: 'Editing', keys: ['F10'], origin: 'fcp7' },
  { id: 'edit.insert', label: 'Insert — splice the Viewer take in at In, or the playhead (Film editor)', short: 'Insert', group: 'Editing', keys: ['F9'], origin: 'fcp7' },
  { id: 'edit.replace', label: 'Replace — swap the shot under the playhead for the Viewer take (Film editor)', short: 'Replace', group: 'Editing', keys: ['F11'], origin: 'fcp7' },
  { id: 'edit.rippleDelete', label: 'Ripple delete — remove the selected shot and close the gap (Film editor)', short: 'Ripple del', group: 'Editing', keys: ['Shift+Delete'], origin: 'fcp7' },
  { id: 'edit.lift', label: 'Lift — remove the selected placed action', short: 'Lift', group: 'Editing', keys: ['Delete', 'Backspace'], origin: 'fcp7' },
  { id: 'edit.nudgeLeft', label: 'Nudge selected action one frame earlier', short: 'Nudge −1', group: 'Editing', keys: [','], origin: 'fcp7', repeat: true },
  { id: 'edit.nudgeRight', label: 'Nudge selected action one frame later', short: 'Nudge +1', group: 'Editing', keys: ['.'], origin: 'fcp7', repeat: true },
  { id: 'edit.nudgeLeftMulti', label: 'Nudge selected action five frames earlier', short: 'Nudge −5', group: 'Editing', keys: ['Shift+,'], origin: 'fcp7', repeat: true },
  { id: 'edit.nudgeRightMulti', label: 'Nudge selected action five frames later', short: 'Nudge +5', group: 'Editing', keys: ['Shift+.'], origin: 'fcp7', repeat: true },
  { id: 'tool.select', label: 'Selection tool (Film editor)', short: 'Select', group: 'Editing', keys: ['A'], origin: 'fcp7' },
  { id: 'tool.razor', label: 'Razor tool — click a clip to cut it (Film editor)', short: 'Razor', group: 'Editing', keys: ['B'], origin: 'fcp7' },
  { id: 'tool.roll', label: 'Roll tool; press again for Ripple (Film editor)', short: 'Roll/Ripple', group: 'Editing', keys: ['R'], origin: 'fcp7' },
  { id: 'tool.slip', label: 'Slip tool — [ and ] slip the selected shot (Film editor)', short: 'Slip', group: 'Editing', keys: ['S'], origin: 'fcp7' },
  { id: 'timeline.snap', label: 'Snapping on/off — clip drags snap to cuts, playhead, markers, In/Out (Film editor)', short: 'Snap', group: 'Editing', keys: ['N'], origin: 'fcp7' },
  { id: 'edit.selectEdit', label: 'Select the edit point nearest the playhead (Film editor)', short: 'Sel edit', group: 'Editing', keys: ['V'], origin: 'fcp7' },
  { id: 'edit.toggleSide', label: 'Toggle edit selection: Out side, both sides, In side (Film editor)', short: 'Edit side', group: 'Editing', keys: ['U'], origin: 'fcp7' },
  { id: 'edit.trimBack', label: 'Trim the selected edit (or slip) one frame earlier (Film editor)', short: 'Trim −1', group: 'Editing', keys: ['['], origin: 'fcp7', repeat: true },
  { id: 'edit.trimForward', label: 'Trim the selected edit (or slip) one frame later (Film editor)', short: 'Trim +1', group: 'Editing', keys: [']'], origin: 'fcp7', repeat: true },
  { id: 'edit.trimBackMulti', label: 'Trim the selected edit (or slip) five frames earlier (Film editor)', short: 'Trim −5', group: 'Editing', keys: ['Shift+['], origin: 'fcp7', repeat: true },
  { id: 'edit.trimForwardMulti', label: 'Trim the selected edit (or slip) five frames later (Film editor)', short: 'Trim +5', group: 'Editing', keys: ['Shift+]'], origin: 'fcp7', repeat: true },
  { id: 'edit.addEdit', label: 'Add edit — cut V1 at the playhead (Film editor)', short: 'Add edit', group: 'Editing', keys: ['Ctrl+V'], origin: 'fcp7' },
  { id: 'edit.extend', label: 'Extend edit — move the selected edit to the playhead (Film editor)', short: 'Extend', group: 'Editing', keys: ['E'], origin: 'fcp7' },
  { id: 'edit.liftRange', label: 'Lift In to Out: remove the marked range, leave a gap (Film editor)', short: 'Lift I/O', group: 'Editing', keys: [';'], origin: 'llr' },
  { id: 'edit.extractRange', label: 'Extract In to Out: remove the marked range and close the gap (Film editor)', short: 'Extract I/O', group: 'Editing', keys: ["'"], origin: 'llr' },
  { id: 'edit.deselect', label: 'Deselect all', short: 'Deselect', group: 'Editing', keys: ['Ctrl+Shift+A'], origin: 'fcp7' },
  { id: 'edit.undo', label: 'Undo', short: 'Undo', group: 'Editing', keys: ['Ctrl+Z'], origin: 'fcp7' },
  { id: 'edit.redo', label: 'Redo', short: 'Redo', group: 'Editing', keys: ['Ctrl+Shift+Z', 'Ctrl+Y'], origin: 'fcp7' },
  { id: 'edit.save', label: 'Save — apply settings or build the sequence', short: 'Save', group: 'Editing', keys: ['Ctrl+S'], origin: 'fcp7', inText: true },
  { id: 'edit.saveAll', label: 'Save all — every sequence with unsaved edits (Film editor)', short: 'Save all', group: 'Editing', keys: ['Ctrl+Alt+S'], origin: 'fcp7', inText: true },
  { id: 'edit.render', label: 'Render — build the review render of the saved sequence (Film editor)', short: 'Render', group: 'Editing', keys: ['Alt+R'], origin: 'fcp7' },
  { id: 'edit.newAction', label: 'Create action', short: 'New action', group: 'Editing', keys: [], origin: 'llr' },
  { id: 'edit.makeTake', label: 'Make another take of this action', short: 'Take', group: 'Editing', keys: [], origin: 'llr' },
  { id: 'edit.export', label: 'Export sequence', short: 'Export', group: 'Editing', keys: [], origin: 'llr' },

  { id: 'timeline.zoomIn', label: 'Zoom timeline in', short: 'Zoom +', group: 'Timeline', keys: ['Ctrl+=', 'Alt+='], origin: 'fcp7', repeat: true },
  { id: 'timeline.zoomOut', label: 'Zoom timeline out', short: 'Zoom −', group: 'Timeline', keys: ['Ctrl+-', 'Alt+-'], origin: 'fcp7', repeat: true },
  { id: 'timeline.fit', label: 'Fit sequence in window', short: 'Fit', group: 'Timeline', keys: ['Shift+Z'], origin: 'fcp7' },
  { id: 'timeline.trackSize', label: 'Cycle track height', short: 'Tracks', group: 'Timeline', keys: ['Shift+T'], origin: 'fcp7' },

  { id: 'window.viewer', label: 'Viewer', short: 'Viewer', group: 'Windows', keys: ['Ctrl+1'], origin: 'fcp7', inText: true },
  { id: 'window.canvas', label: 'Canvas', short: 'Canvas', group: 'Windows', keys: ['Ctrl+2'], origin: 'fcp7', inText: true },
  { id: 'window.timeline', label: 'Timeline', short: 'Timeline', group: 'Windows', keys: ['Ctrl+3'], origin: 'fcp7', inText: true },
  { id: 'window.browser', label: 'Browser', short: 'Browser', group: 'Windows', keys: ['Ctrl+4'], origin: 'fcp7', inText: true },
  { id: 'window.toggleMonitor', label: 'Switch between Viewer and Canvas', short: 'V↔C', group: 'Windows', keys: ['Q'], origin: 'fcp7' },
  { id: 'window.standard', label: 'Standard layout', short: 'Standard', group: 'Windows', keys: ['Ctrl+U'], origin: 'fcp7' },
  { id: 'window.allTracks', label: 'All tracks overview layout', short: 'All tracks', group: 'Windows', keys: ['Alt+U'], origin: 'fcp7' },
  { id: 'window.tools', label: 'Hide / show tools', short: 'Tools', group: 'Windows', keys: [], origin: 'llr' },
  { id: 'window.find', label: 'Find an action in the Browser', short: 'Find', group: 'Windows', keys: ['Ctrl+F'], origin: 'fcp7' },
  { id: 'window.import', label: 'Import scene', short: 'Import', group: 'Windows', keys: ['Ctrl+I'], origin: 'fcp7' },
  { id: 'window.keyboard', label: 'Keyboard layout', short: 'Keys', group: 'Windows', keys: ['Alt+H', 'Ctrl+/'], origin: 'fcp7', inText: true },
]

export const COMMAND_BY_ID: ReadonlyMap<string, Command> = new Map(COMMANDS.map(c => [c.id, c]))

/** FCP7 commands that this editor deliberately does not offer: takes are never trimmed or retimed, and audio is pending. */
// Insert, Replace and Ripple delete now exist in the Film editor only; Scene animation still ignores them.
export const UNSUPPORTED_FCP7 = ['Insert / Replace / Ripple delete / Render / Save all / trim tools in Scene animation', 'Slide (SS)', 'Dragging audio clips', 'Linked selection (Shift+L)', 'Audio levels']

const CODE_NAMES: Record<string, string> = {
  Space: 'Space', Enter: 'Enter', NumpadEnter: 'Enter', Escape: 'Esc', Backspace: 'Backspace', Delete: 'Delete', Tab: 'Tab',
  Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown', Insert: 'Insert',
  ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down',
  Comma: ',', Period: '.', Slash: '/', Backslash: '\\', IntlBackslash: '\\', Semicolon: ';', Quote: "'",
  BracketLeft: '[', BracketRight: ']', Minus: '-', Equal: '=', Backquote: '`',
  NumpadAdd: 'NumPlus', NumpadSubtract: 'NumMinus', NumpadMultiply: 'NumStar', NumpadDivide: 'NumSlash', NumpadDecimal: 'NumDot',
}
const MODIFIERS = ['Ctrl', 'Alt', 'Shift'] as const
const KEY_NAMES = new Set<string>([
  ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split(''),
  ...Array.from({ length: 10 }, (_, i) => `Num${i}`),
  ...Array.from({ length: 24 }, (_, i) => `F${i + 1}`),
  ...Object.values(CODE_NAMES),
])
/** Keys that move focus or close windows; they cannot be assigned. */
export const UNASSIGNABLE = new Set(['Tab', 'Shift+Tab', 'Esc'])
/** Chords the web browser usually keeps for itself. They can be assigned but may never reach the editor. */
export const BROWSER_RESERVED = new Set(['Ctrl+N', 'Ctrl+T', 'Ctrl+W', 'Ctrl+Shift+N', 'Ctrl+Shift+T', 'Ctrl+Shift+W', 'Ctrl+Tab', 'Ctrl+Shift+Tab', 'Ctrl+Shift+Q', 'Alt+F4', 'F11'])

export interface KeyLike { code: string; key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }

/** Physical-key name, so FCP7's J/K/L and I/O stay in place on any keyboard layout. */
export function keyName(event: Pick<KeyLike, 'code' | 'key'>): string | null {
  const { code, key } = event
  if (/^(Shift|Control|Alt|Meta|OS)(Left|Right)?$|^(CapsLock|NumLock|ScrollLock|Fn|ContextMenu)$/.test(code) || ['Shift', 'Control', 'Alt', 'Meta', 'AltGraph'].includes(key)) return null
  if (/^Key[A-Z]$/.test(code)) return code.slice(3)
  if (/^Digit\d$/.test(code)) return code.slice(5)
  if (/^Numpad\d$/.test(code)) return `Num${code.slice(6)}`
  if (/^F([1-9]|1\d|2[0-4])$/.test(code)) return code
  if (CODE_NAMES[code]) return CODE_NAMES[code]
  if (key && key.length === 1 && key !== '+' && key !== ' ') { const upper = key.toUpperCase(); return KEY_NAMES.has(upper) ? upper : null }
  return null
}

/** Canonical chord such as "Ctrl+Shift+Z". Cmd on a Mac counts as Ctrl. */
export function chordFromEvent(event: KeyLike): string | null {
  const name = keyName(event)
  if (!name) return null
  return [event.ctrlKey || event.metaKey ? 'Ctrl' : '', event.altKey ? 'Alt' : '', event.shiftKey ? 'Shift' : '', name].filter(Boolean).join('+')
}

/** Normalize user/imported text ("cmd+shift+z") to a canonical chord, or null if invalid. */
export function normalizeChord(text: string): string | null {
  if (typeof text !== 'string' || !text.trim()) return null
  const parts = text.trim().split('+')
  let name = parts.pop() ?? ''
  if (name === '' && parts.at(-1) === '') return null // "+" is not a key name; use "=" or "NumPlus".
  const upper = name.length === 1 ? name.toUpperCase() : name
  name = [...KEY_NAMES].find(k => k.toLowerCase() === upper.toLowerCase()) ?? ''
  if (!name) return null
  const mods = new Set<string>()
  for (const part of parts) {
    const p = part.trim().toLowerCase()
    const mod = p === 'ctrl' || p === 'control' || p === 'cmd' || p === 'command' || p === 'meta' ? 'Ctrl' : p === 'alt' || p === 'option' || p === 'opt' ? 'Alt' : p === 'shift' ? 'Shift' : null
    if (!mod || mods.has(mod)) return null
    mods.add(mod)
  }
  return [...MODIFIERS.filter(m => mods.has(m)), name].join('+')
}

const DISPLAY: Record<string, string> = { Left: '←', Right: '→', Up: '↑', Down: '↓', PageUp: 'Page Up', PageDown: 'Page Down', Backspace: 'Backspace', NumPlus: 'Num +', NumMinus: 'Num −', NumStar: 'Num *', NumSlash: 'Num /', NumDot: 'Num .' }
/** Keycap labels for display, e.g. ["Ctrl", "Shift", "Z"]. */
export function chordParts(chord: string): string[] {
  return chord.split('+').map(part => DISPLAY[part] ?? (/^Num\d$/.test(part) ? `Num ${part.slice(3)}` : part))
}
export function formatChord(chord: string) { return chordParts(chord).join('+') }

export function defaultKeymap(): Keymap {
  return Object.fromEntries(COMMANDS.map(c => [c.id, [...c.keys]]))
}

/** Which command a chord runs. Later duplicates are ignored (resolveKeymap prevents them). */
export function chordIndex(keymap: Keymap): Map<string, string> {
  const index = new Map<string, string>()
  for (const command of COMMANDS) for (const chord of keymap[command.id] ?? []) if (!index.has(chord)) index.set(chord, command.id)
  return index
}

export function sameKeys(a: readonly string[], b: readonly string[]) {
  return a.length === b.length && a.every(k => b.includes(k))
}
export function changedCommands(keymap: Keymap): string[] {
  return COMMANDS.filter(c => !sameKeys(keymap[c.id] ?? [], c.keys)).map(c => c.id)
}

/** Give a chord to one command, removing it from any other command. */
export function assignChord(keymap: Keymap, id: string, chord: string): Keymap {
  if (!COMMAND_BY_ID.has(id)) throw new Error(`Unknown keyboard command: ${id}`)
  const normal = normalizeChord(chord)
  if (!normal || UNASSIGNABLE.has(normal)) throw new Error(`${chord} cannot be assigned`)
  const next: Keymap = {}
  for (const command of COMMANDS) next[command.id] = (keymap[command.id] ?? []).filter(k => k !== normal)
  next[id] = [...next[id], normal]
  return next
}
export function removeChord(keymap: Keymap, id: string, chord: string): Keymap {
  return { ...keymap, [id]: (keymap[id] ?? []).filter(k => k !== chord) }
}
/** Restore one command's FCP7 defaults, taking those keys back from other commands. */
export function resetCommand(keymap: Keymap, id: string): Keymap {
  const command = COMMAND_BY_ID.get(id)
  if (!command) return keymap
  let next: Keymap = { ...keymap, [id]: [] }
  for (const chord of command.keys) next = assignChord(next, id, chord)
  return next
}

/** Build a complete keymap from saved/imported bindings over the FCP7 defaults. */
/** Default keys added after layouts could be saved. A layout saved before `rev` gets them added once (only if the user has not
 *  used that key for something else), so new FCP7 keys reach people who saved a custom layout earlier. */
export const DEFAULTS_REV = 3
export const ADDED_DEFAULTS: { rev: number; id: string; chord: string }[] = [
  { rev: 3, id: 'edit.liftRange', chord: ';' }, { rev: 3, id: 'edit.extractRange', chord: "'" },
]
/** Default keys withdrawn at ev: removed from layouts saved before it (rev 2 briefly put ; and ' on previous/next edit). */
export const REMOVED_DEFAULTS: { rev: number; id: string; chord: string }[] = [
  { rev: 3, id: 'nav.prevEdit', chord: ';' }, { rev: 3, id: 'nav.nextEdit', chord: "'" },
]
export function resolveKeymap(bindings: unknown, savedRev = DEFAULTS_REV): { keymap: Keymap; warnings: string[] } {
  const warnings: string[] = []
  let keymap = defaultKeymap()
  if (!bindings || typeof bindings !== 'object' || Array.isArray(bindings)) return { keymap, warnings: bindings == null ? [] : ['Keyboard bindings were not an object; using Final Cut Pro 7 defaults.'] }
  const claimed = new Map<string, string>()
  for (const [id, value] of Object.entries(bindings as Record<string, unknown>)) {
    if (!COMMAND_BY_ID.has(id)) { warnings.push(`Ignored unknown command “${id}”.`); continue }
    if (!Array.isArray(value)) { warnings.push(`Ignored bindings for ${id}: expected a list of keys.`); continue }
    const keys: string[] = []
    for (const raw of value) {
      const chord = typeof raw === 'string' ? normalizeChord(raw) : null
      if (!chord || UNASSIGNABLE.has(chord)) { warnings.push(`Ignored invalid key “${String(raw)}” for ${COMMAND_BY_ID.get(id)!.label}.`); continue }
      const owner = claimed.get(chord)
      if (owner && owner !== id) { warnings.push(`${formatChord(chord)} is listed twice; kept it for ${COMMAND_BY_ID.get(owner)!.label}.`); continue }
      if (!keys.includes(chord)) keys.push(chord)
      claimed.set(chord, id)
    }
    keymap[id] = keys
  }
  // Defaults withdrawn since this layout was saved: take them back off, so the key is free for its new command.
  for (const removed of REMOVED_DEFAULTS) {
    if (removed.rev <= savedRev || !(keymap[removed.id] ?? []).includes(removed.chord)) continue
    keymap = { ...keymap, [removed.id]: keymap[removed.id].filter(c => c !== removed.chord) }
    if (claimed.get(removed.chord) === removed.id) claimed.delete(removed.chord)
  }
  // Defaults added since this layout was saved: add each unless the user already uses that key.
  for (const added of ADDED_DEFAULTS) {
    if (added.rev <= savedRev || !Object.hasOwn(bindings as object, added.id) || claimed.has(added.chord) || !COMMAND_BY_ID.has(added.id)) continue
    keymap = { ...keymap, [added.id]: [...(keymap[added.id] ?? []), added.chord] }
    claimed.set(added.chord, added.id)
  }
  // Saved choices win over defaults that use the same key.
  for (const command of COMMANDS) {
    if (Object.hasOwn(bindings as object, command.id)) continue
    keymap = { ...keymap, [command.id]: keymap[command.id].filter(chord => !claimed.has(chord)) }
  }
  return { keymap, warnings }
}

export const KEYMAP_FORMAT = 'last-light-radio-keymap'
export function serializeKeymap(keymap: Keymap): string {
  const bindings = Object.fromEntries(COMMANDS.map(c => [c.id, keymap[c.id] ?? []]))
  return JSON.stringify({ format: KEYMAP_FORMAT, version: 1, base: 'fcp7', defaults_rev: DEFAULTS_REV, bindings }, null, 2)
}
export function parseKeymapFile(text: string): { keymap: Keymap; warnings: string[] } {
  let data: unknown
  try { data = JSON.parse(text) } catch { throw new Error('This file is not valid JSON.') }
  if (!data || typeof data !== 'object' || (data as { format?: unknown }).format !== KEYMAP_FORMAT) throw new Error('This is not a Last Light Radio keyboard layout file.')
  if ((data as { version?: unknown }).version !== 1) throw new Error('This keyboard layout was saved by an unsupported version.')
  const rev = (data as { defaults_rev?: unknown }).defaults_rev
  return resolveKeymap((data as { bindings?: unknown }).bindings, typeof rev === 'number' ? rev : 1)
}

/** Read the saved layout; any storage failure falls back to the FCP7 defaults. */
export function loadStoredKeymap(storage: Pick<Storage, 'getItem'> | undefined, key: string): { keymap: Keymap; warnings: string[] } {
  try {
    const raw = storage?.getItem(key)
    return raw ? parseKeymapFile(raw) : { keymap: defaultKeymap(), warnings: [] }
  } catch (problem) {
    return { keymap: defaultKeymap(), warnings: [`Saved keyboard layout could not be read (${problem instanceof Error ? problem.message : 'unknown error'}); using Final Cut Pro 7 defaults.`] }
  }
}

/** FCP7 shuttle: same direction speeds up 1×→2×→4×→8×; the other direction (or stopped) starts at 1×. */
const SHUTTLE = [1, 2, 4, 8]
export function shuttleRate(current: number, direction: 1 | -1): number {
  if (Math.sign(current) !== direction) return direction
  const index = SHUTTLE.indexOf(Math.abs(current))
  return direction * SHUTTLE[Math.min(SHUTTLE.length - 1, index + 1)]
}

/**
 * Typed timecode, FCP7 style. Digits fill from the right (HH:MM:SS:FF); "." stands for "00";
 * a leading + or - moves relative to the current frame. Frame values above the rate carry over.
 * Returns the target frame, or null if the text is not a timecode.
 */
export function parseTimecodeEntry(text: string, current: number, fps = 24): number | null {
  const match = /^([+-]?)([\d.:;]+)$/.exec(text.trim())
  if (!match) return null
  let fields: number[]
  if (/[:;]/.test(match[2])) {
    const raw = match[2].split(/[:;]/)
    if (raw.length > 4 || raw.some(f => !/^\d*$/.test(f))) return null
    fields = raw.map(f => Number(f || 0))
  } else {
    const digits = match[2].replace(/\./g, '00')
    if (digits.length > 8) return null
    const padded = digits.padStart(Math.ceil(digits.length / 2) * 2, '0')
    fields = padded.match(/\d\d/g)!.map(Number)
  }
  const [ff = 0, ss = 0, mm = 0, hh = 0] = fields.reverse()
  const total = ((hh * 60 + mm) * 60 + ss) * fps + ff
  return match[1] === '+' ? current + total : match[1] === '-' ? current - total : total
}

/** Sorted edit points (cuts) inside [start, end), including the first and last frame. */
export function editPoints(events: readonly { start_frame: number; end_frame: number }[], start: number, end: number): number[] {
  const last = Math.max(start, end - 1)
  const points = new Set<number>([start, last])
  for (const event of events) {
    if (event.start_frame > start && event.start_frame < last) points.add(event.start_frame)
    if (event.end_frame > start && event.end_frame < last) points.add(event.end_frame)
  }
  return [...points].sort((a, b) => a - b)
}
/** The nearest point strictly after (1) or before (-1) the frame. */
export function stepPoint(points: readonly number[], frame: number, direction: 1 | -1): number | undefined {
  const sorted = [...points].sort((a, b) => a - b)
  return direction > 0 ? sorted.find(p => p > frame) : sorted.reverse().find(p => p < frame)
}

export const ZOOM_LEVELS = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]
export function zoomStep(scale: number, direction: 1 | -1): number {
  return direction > 0
    ? ZOOM_LEVELS.find(z => z > scale * 1.001) ?? ZOOM_LEVELS.at(-1)!
    : [...ZOOM_LEVELS].reverse().find(z => z < scale / 1.001) ?? ZOOM_LEVELS[0]
}
