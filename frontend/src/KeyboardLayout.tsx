import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import type { CommandGroup, Keymap } from './shortcuts'
import {
  BROWSER_RESERVED, COMMANDS, COMMAND_BY_ID, GROUPS, UNASSIGNABLE, UNSUPPORTED_FCP7, assignChord, changedCommands, chordFromEvent,
  chordIndex, chordParts, defaultKeymap, formatChord, parseKeymapFile, removeChord, resetCommand, sameKeys, serializeKeymap,
} from './shortcuts'
import './keyboardLayout.css'

type Props = { keymap: Keymap; onChange: (keymap: Keymap) => void; onClose: () => void }
type Capture = { mode: 'assign'; id: string } | { mode: 'find' }
type Modifier = '' | 'Shift' | 'Ctrl' | 'Alt' | 'Ctrl+Shift'

// US physical layout. Each entry is [key name, display label, width in key units].
type Cap = [string, string, number?]
const ROWS: Cap[][] = [
  [['Esc', 'Esc', 1.25], ...Array.from({ length: 12 }, (_, i): Cap => [`F${i + 1}`, `F${i + 1}`])],
  [['`', '`'], ...'1234567890'.split('').map((k): Cap => [k, k]), ['-', '−'], ['=', '='], ['Backspace', '⌫', 1.75]],
  [['Tab', 'Tab', 1.5], ...'QWERTYUIOP'.split('').map((k): Cap => [k, k]), ['[', '['], [']', ']'], ['\\', '\\', 1.25]],
  [['', 'Caps', 1.75], ...'ASDFGHJKL'.split('').map((k): Cap => [k, k]), [';', ';'], ["'", "'"], ['Enter', 'Enter', 2]],
  [['', 'Shift', 2.25], ...'ZXCVBNM'.split('').map((k): Cap => [k, k]), [',', ','], ['.', '.'], ['/', '/'], ['', 'Shift', 2.25]],
  [['', 'Ctrl', 1.5], ['', 'Alt', 1.25], ['Space', 'Space', 7], ['', 'Alt', 1.25], ['', 'Ctrl', 1.5]],
]
const NAV: Cap[][] = [
  [['Insert', 'Ins'], ['Home', 'Home'], ['PageUp', 'PgUp']],
  [['Delete', 'Del'], ['End', 'End'], ['PageDown', 'PgDn']],
  [['', ''], ['Up', '↑'], ['', '']],
  [['Left', '←'], ['Down', '↓'], ['Right', '→']],
]
const MODIFIER_TABS: Modifier[] = ['', 'Shift', 'Ctrl', 'Alt', 'Ctrl+Shift']
const GROUP_CLASS: Record<CommandGroup, string> = { Playback: 'play', Navigation: 'nav', Marking: 'mark', Editing: 'edit', Timeline: 'time', Windows: 'win' }

function Keycaps({ chord }: { chord: string }) {
  return <span className="kl-chord">{chordParts(chord).map((part, i) => <Fragment key={i}>{i ? <span className="kl-plus">+</span> : null}<kbd>{part}</kbd></Fragment>)}</span>
}

export default function KeyboardLayout({ keymap, onChange, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [keyFilter, setKeyFilter] = useState('')
  const [onlyChanged, setOnlyChanged] = useState(false)
  const [modifier, setModifier] = useState<Modifier>('')
  const [capture, setCapture] = useState<Capture | null>(null)
  const [conflict, setConflict] = useState<{ id: string; chord: string; owner: string } | null>(null)
  const [notice, setNotice] = useState('')
  const index = useMemo(() => chordIndex(keymap), [keymap])
  const changed = useMemo(() => new Set(changedCommands(keymap)), [keymap])

  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
    return () => { if (element?.open) element.close() }
  }, [])

  // While capturing, the next key press (with modifiers) becomes the binding. Esc cancels; Tab keeps moving focus.
  useEffect(() => {
    if (!capture) return
    function down(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setCapture(null); setNotice('Cancelled.'); return }
      if (event.key === 'Tab') { setCapture(null); return }
      const chord = chordFromEvent(event)
      if (!chord) return // A modifier on its own: keep waiting for the key.
      event.preventDefault(); event.stopPropagation()
      setCapture(null)
      if (capture!.mode === 'find') { setKeyFilter(chord); setQuery(''); setNotice(`Showing ${formatChord(chord)}.`); return }
      assign(capture!.id, chord)
    }
    window.addEventListener('keydown', down, true)
    return () => window.removeEventListener('keydown', down, true)
    // assign reads the latest keymap through this render's closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capture, keymap])

  function assign(id: string, chord: string, confirmed = false) {
    const label = COMMAND_BY_ID.get(id)!.label
    if (UNASSIGNABLE.has(chord)) { setNotice(`${formatChord(chord)} is kept for moving focus and closing windows.`); return }
    if ((keymap[id] ?? []).includes(chord)) { setNotice(`${formatChord(chord)} already runs ${label}.`); return }
    const owner = index.get(chord)
    if (owner && owner !== id && !confirmed) { setConflict({ id, chord, owner }); return }
    onChange(assignChord(keymap, id, chord)); setConflict(null)
    const reserved = BROWSER_RESERVED.has(chord) ? ' Your web browser may keep this key for itself.' : ''
    setNotice(`${formatChord(chord)} → ${label}${owner && owner !== id ? ` (removed from ${COMMAND_BY_ID.get(owner)!.label})` : ''}.${reserved}`)
  }
  function exportLayout() {
    const url = URL.createObjectURL(new Blob([serializeKeymap(keymap)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = 'last-light-radio-keyboard.json'; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    setNotice('Keyboard layout exported.')
  }
  async function importLayout(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const result = parseKeymapFile(await file.text())
      onChange(result.keymap)
      setNotice(`Imported ${file.name}.${result.warnings.length ? ` ${result.warnings.join(' ')}` : ''}`)
    } catch (problem) { setNotice(`Could not import ${file.name}: ${problem instanceof Error ? problem.message : 'unknown error'}`) }
  }

  const words = query.trim().toLowerCase()
  const visible = COMMANDS.filter(command => {
    const keys = keymap[command.id] ?? []
    if (onlyChanged && !changed.has(command.id)) return false
    if (keyFilter) return keys.includes(keyFilter)
    if (!words) return true
    return `${command.label} ${command.group} ${keys.map(formatChord).join(' ')} ${keys.join(' ')}`.toLowerCase().includes(words)
  })
  const summary = changed.size ? `Customized · ${changed.size} change${changed.size === 1 ? '' : 's'} from Final Cut Pro 7` : 'Final Cut Pro 7 defaults'

  function keycap([name, label, width = 1]: Cap, i: number) {
    if (!name) return <span key={i} className={`kl-key kl-key-blank ${label ? 'kl-key-mod' : ''}`} style={{ flexGrow: width }} aria-hidden="true">{label}</span>
    const chord = modifier ? `${modifier}+${name}` : name
    const id = index.get(chord)
    const command = id ? COMMAND_BY_ID.get(id) : undefined
    return <button key={i} type="button" className={`kl-key ${command ? `kl-${GROUP_CLASS[command.group]}` : ''} ${keyFilter === chord ? 'selected' : ''} ${UNASSIGNABLE.has(chord) ? 'kl-key-fixed' : ''}`}
      style={{ flexGrow: width }} title={command ? `${formatChord(chord)}: ${command.label}` : `${formatChord(chord)}: unassigned`}
      aria-label={`${formatChord(chord)}: ${command?.label ?? 'unassigned'}`} aria-pressed={keyFilter === chord}
      onClick={() => { setKeyFilter(current => current === chord ? '' : chord); setQuery('') }}>
      <span className="kl-key-name">{label}</span>{command ? <span className="kl-key-command">{command.short}</span> : null}
    </button>
  }

  return <dialog ref={dialog} className="kl-dialog" aria-labelledby="kl-title"
    onCancel={event => { event.preventDefault(); if (capture) setCapture(null); else if (conflict) setConflict(null); else onClose() }}
    onClose={onClose}>
    <header className="kl-titlebar"><strong id="kl-title">Keyboard Layout</strong><span>{summary}</span><button type="button" aria-label="Close keyboard layout" onClick={onClose}>×</button></header>
    <div className="kl-toolbar">
      <label className="kl-search"><span className="sr-only">Search commands or keys</span><input type="search" placeholder="Search commands or keys…" value={query} onChange={e => { setQuery(e.target.value); setKeyFilter('') }} /></label>
      <button type="button" aria-pressed={capture?.mode === 'find'} onClick={() => setCapture(capture?.mode === 'find' ? null : { mode: 'find' })}>{capture?.mode === 'find' ? 'Press a key…' : 'Find by key press'}</button>
      {keyFilter ? <button type="button" className="kl-filter-chip" onClick={() => setKeyFilter('')} aria-label={`Clear filter ${formatChord(keyFilter)}`}><Keycaps chord={keyFilter} /> ×</button> : null}
      <label className="kl-check"><input type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)} />Changed only</label>
    </div>
    <section className="kl-board" aria-label="Keyboard map">
      <div className="kl-mods" role="group" aria-label="Show keys with modifier">{MODIFIER_TABS.map(mod => <button type="button" key={mod || 'none'} aria-pressed={modifier === mod} onClick={() => setModifier(mod)}>{mod || 'No modifier'}</button>)}</div>
      <div className="kl-keys">
        <div className="kl-main">{ROWS.map((row, r) => <div className="kl-row" key={r}>{row.map(keycap)}</div>)}</div>
        <div className="kl-navpad">{NAV.map((row, r) => <div className="kl-row" key={r}>{row.map(keycap)}</div>)}</div>
      </div>
      <div className="kl-legend" aria-hidden="true">{GROUPS.map(group => <span key={group} className={`kl-${GROUP_CLASS[group]}`}>{group}</span>)}</div>
    </section>
    <p className="kl-notice" role="status" aria-live="polite">{capture?.mode === 'assign' ? `Press the new key for ${COMMAND_BY_ID.get(capture.id)!.label}. Esc cancels.` : notice || 'Click + to add a key, × to remove one. Changes apply immediately.'}</p>
    {conflict ? <div className="kl-conflict" role="alertdialog" aria-label="Key already assigned">
      <span><Keycaps chord={conflict.chord} /> already runs <strong>{COMMAND_BY_ID.get(conflict.owner)!.label}</strong>. Reassign it to <strong>{COMMAND_BY_ID.get(conflict.id)!.label}</strong>?</span>
      <button type="button" className="kl-primary" autoFocus onClick={() => assign(conflict.id, conflict.chord, true)}>Reassign</button><button type="button" onClick={() => setConflict(null)}>Cancel</button>
    </div> : null}
    <div className="kl-list">
      {GROUPS.map(group => {
        const rows = visible.filter(c => c.group === group)
        if (!rows.length) return null
        return <section key={group} className="kl-group"><h3><i className={`kl-swatch kl-${GROUP_CLASS[group]}`} />{group}</h3>
          {rows.map(command => {
            const keys = keymap[command.id] ?? []
            const capturing = capture?.mode === 'assign' && capture.id === command.id
            return <div className={`kl-command ${changed.has(command.id) ? 'changed' : ''}`} key={command.id}>
              <span className="kl-label">{command.label}{command.origin === 'llr' ? <small title="No Final Cut Pro 7 equivalent">Last Light Radio</small> : null}</span>
              <span className="kl-bindings">
                {keys.map(chord => <span className="kl-binding" key={chord} title={BROWSER_RESERVED.has(chord) ? 'Your web browser may keep this key for itself.' : undefined}>
                  <Keycaps chord={chord} />{BROWSER_RESERVED.has(chord) ? <span className="kl-warn" aria-label="may be reserved by the browser">!</span> : null}
                  <button type="button" aria-label={`Remove ${formatChord(chord)} from ${command.label}`} onClick={() => { onChange(removeChord(keymap, command.id, chord)); setNotice(`Removed ${formatChord(chord)} from ${command.label}.`) }}>×</button></span>)}
                {capturing ? <span className="kl-capture">Press a key…</span> : null}
                {!keys.length && !capturing ? <span className="kl-none">Unassigned</span> : null}
                <button type="button" className="kl-add" aria-label={`Add a key for ${command.label}`} aria-pressed={capturing} onClick={() => { setConflict(null); setCapture(capturing ? null : { mode: 'assign', id: command.id }) }}>+</button>
              </span>
              <button type="button" className="kl-reset" disabled={sameKeys(keys, command.keys)} title={command.keys.length ? `Default: ${command.keys.map(formatChord).join(', ')}` : 'Default: unassigned'} onClick={() => { onChange(resetCommand(keymap, command.id)); setNotice(`${command.label} restored to its default.`) }}>Default</button>
            </div>
          })}
        </section>
      })}
      {!visible.length ? <p className="kl-empty">{keyFilter ? `${formatChord(keyFilter)} is unassigned. Choose + on a command, then press it.` : 'No matching commands.'}</p> : null}
      <p className="kl-unsupported">Not available in this editor (takes are never trimmed or retimed; audio is pending): {UNSUPPORTED_FCP7.join(' · ')}.</p>
    </div>
    <footer className="kl-footer">
      <button type="button" disabled={!changed.size} onClick={() => { onChange(defaultKeymap()); setNotice('Restored every Final Cut Pro 7 default.') }}>Restore Final Cut Pro 7 defaults</button>
      <button type="button" onClick={exportLayout}>Export…</button>
      <button type="button" onClick={() => fileInput.current?.click()}>Import…</button>
      <input ref={fileInput} type="file" accept="application/json,.json" hidden onChange={e => void importLayout(e)} />
      <span className="kl-spacer" />
      <button type="button" className="kl-primary" onClick={onClose}>Done</button>
    </footer>
  </dialog>
}
