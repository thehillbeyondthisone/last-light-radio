import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { CSSProperties, DragEvent, ReactNode } from 'react'
import Thumb from './Thumb'
import { emptyBrowserSelection, selectBrowserItem, visibleSourceKeys } from './browserSelection'
import type { BrowserSelection } from './browserSelection'

/** One row in the FCP7-style Browser: a video take, an audio source or a reference still. */
export type BinKind = 'video' | 'audio' | 'still'
export interface BinItem {
  kind: BinKind; id: string; label: string; status: string; version?: number
  seconds: number | null; width?: number; height?: number; created?: string
  seed?: number | string; model?: string; note?: string
  /** For the poster frame: a video's media (captured at thumbFrame) or a still's image. */
  media?: string; thumbFrame?: number
}
type Bin = 'video' | 'audio' | 'still' | 'all' | 'sequence' | 'unused'
type SortKey = 'label' | 'kind' | 'status' | 'seconds' | 'size' | 'created' | 'used' | 'seed' | 'model'
type GroupBy = 'bins' | 'type' | 'status' | 'none'
type View = 'list' | 'grid' | 'details'

const BINS: { id: Bin; label: string; title: string }[] = [
  { id: 'video', label: 'Video', title: 'Video takes' },
  { id: 'audio', label: 'Audio', title: 'Audio sources' },
  { id: 'still', label: 'Stills', title: 'Reference stills (conditioning only; not placed on the timeline)' },
  { id: 'all', label: 'All', title: 'Every source' },
  { id: 'sequence', label: 'In sequence', title: 'Used by the open sequence, including unsaved edits' },
  { id: 'unused', label: 'Unused', title: 'Video or audio not used by any saved sequence' },
]
const KIND_MARK: Record<BinKind, string> = { video: '▶', audio: '♪', still: '▣' }
const KIND_LABEL: Record<BinKind, string> = { video: 'Video', audio: 'Audio', still: 'Still' }
/** No approve/reject (Boden, 2026-11-19): a clip's state is where it is used. */
type UseState = 'in sequence' | 'used' | 'unused' | 'reference'
const STATUS_MARK: Record<UseState, string> = { 'in sequence': '●', used: '◐', unused: '○', reference: '·' }
const STATUS_ORDER: UseState[] = ['in sequence', 'used', 'unused', 'reference']
const STATUS_LABEL: Record<UseState, string> = { 'in sequence': 'In this sequence', used: 'Used in saved sequences', unused: 'Unused', reference: 'Reference stills' }
const SORTS: { id: string; label: string; key: SortKey | null; dir: 1 | -1 }[] = [
  { id: 'created:-1', label: 'Newest', key: 'created', dir: -1 },
  { id: 'created:1', label: 'Oldest', key: 'created', dir: 1 },
  { id: 'label:1', label: 'A–Z', key: 'label', dir: 1 },
  { id: 'label:-1', label: 'Z–A', key: 'label', dir: -1 },
  { id: 'seconds:-1', label: 'Longest', key: 'seconds', dir: -1 },
  { id: 'seconds:1', label: 'Shortest', key: 'seconds', dir: 1 },
  { id: 'used:-1', label: 'Most used', key: 'used', dir: -1 },
  { id: 'status:1', label: 'Use', key: 'status', dir: 1 },
  { id: 'kind:1', label: 'Type', key: 'kind', dir: 1 },
  { id: 'none', label: 'Library', key: null, dir: 1 },
]
/** User bin colours: a swatch on the bin header only; kinds keep their own colours. */
const BIN_COLOURS = ['#c2703d', '#7a5aa6', '#2f8a7e', '#b0457a', '#6b7d2a', '#3d6fb0']

/** Custom bins are browser-local (no server route yet): they don't follow the library to another browser. */
export interface UserBin { id: string; name: string; colour: string }
export interface UserBins { bins: UserBin[]; member: Record<string, string> }
interface Prefs { group: GroupBy; view: View; sort: string; folded: string[] }

const PREFS_KEY = 'llr.film.browser.v1'
const USER_BINS_KEY = 'llr.film.userBins.v1'
const UNSORTED = '__unsorted'
const DRAG_TYPE = 'application/x-llr-source'
const MULTI_DRAG_TYPE = 'application/x-llr-sources'
const itemKey = (item: BinItem) => sourceKey(item.kind, item.id)
/** Bin membership key for a source (same for the Browser rows and the right-click menu). */
export const sourceKey = (kind: BinKind, id: string) => `${kind}:${id}`

function readJson<T>(key: string, fallback: T): T { try { const v = localStorage.getItem(key); return v ? { ...fallback, ...JSON.parse(v) } : fallback } catch { return fallback } }
function writeJson(key: string, value: unknown) { try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* optional preference */ } }

/** User bins live in one module store so the Browser and the editor's right-click menu stay in step. Browser-local (localStorage). */
let binsState: UserBins | null = null
const binListeners = new Set<() => void>()
export function getUserBins(): UserBins { return binsState ??= readJson<UserBins>(USER_BINS_KEY, { bins: [], member: {} }) }
export function updateUserBins(change: (u: UserBins) => UserBins) { binsState = change(getUserBins()); writeJson(USER_BINS_KEY, binsState); binListeners.forEach(l => l()) }
function subscribeBins(l: () => void) { binListeners.add(l); return () => { binListeners.delete(l) } }
export function useUserBins(): UserBins { return useSyncExternalStore(subscribeBins, getUserBins) }
/** Put sources in a bin (null = back to Unsorted). */
export function moveToUserBin(keys: string[], binId: string | null) {
  updateUserBins(u => { const member = { ...u.member }; for (const k of keys) { if (binId) member[k] = binId; else delete member[k] } return { ...u, member } })
}
/** Make a bin (optionally starting with some sources) and return its id. */
export function createUserBin(name: string, keys: string[] = []): string {
  const id = `bin-${Date.now().toString(36)}`
  updateUserBins(u => ({ bins: [...u.bins, { id, name, colour: BIN_COLOURS[u.bins.length % BIN_COLOURS.length] }], member: { ...u.member, ...Object.fromEntries(keys.map(k => [k, id])) } }))
  return id
}

/** A remembered open/closed state for one Browser section (Sequences, Sources). */
export function useFold(id: string, initial = true): [boolean, () => void] {
  const key = `llr.film.browserFold.v1:${id}`
  const [open, setOpen] = useState(() => { try { const v = localStorage.getItem(key); return v === null ? initial : v === '1' } catch { return initial } })
  return [open, () => setOpen(o => { try { localStorage.setItem(key, o ? '0' : '1') } catch { /* optional */ } return !o })]
}

/** Section header with a disclosure triangle. Children after the button sit on the right (counts, actions). */
export function FoldHead({ open, onToggle, label, kind, children }: { open: boolean; onToggle: () => void; label: string; kind?: string; children?: ReactNode }) {
  return <h2 className="fcp-bin-head fcp-fold-head" data-kind={kind}>
    <button type="button" aria-expanded={open} onClick={onToggle}><i aria-hidden="true" className="fcp-fold" />{kind ? <i aria-hidden="true" className="fcp-kind-dot" /> : null}{label}</button>
    {children}
  </h2>
}

export interface BinProps {
  items: BinItem[]
  /** Saved uses per source id, across every project (drafts not counted). */
  usedCount: Map<string, number>
  /** Source ids used by the open sequence, including unsaved edits. */
  inSequence: Set<string>
  openKey: string
  selection: BrowserSelection
  busy: boolean
  onSelection: (selection: BrowserSelection) => void
  onOpen: (item: BinItem) => void
  /** Right-click / Shift+F10 / Menu key on a row: the editor shows the shared context menu. */
  onMenu: (item: BinItem, x: number, y: number, keys: string[]) => void
}

/** First run of the grouped Browser starts on All so every kind (and its colour) shows; after that the last chip is remembered. */
function loadBin(): Bin { try { if (localStorage.getItem(PREFS_KEY) === null) return 'all'; const v = localStorage.getItem('llr.film.bin.v1'); return (BINS.some(b => b.id === v) ? v : 'video') as Bin } catch { return 'video' } }

export default function FilmBin({ items, usedCount, inSequence, openKey, selection, onSelection, onOpen, onMenu }: BinProps) {
  const [bin, setBin] = useState<Bin>(loadBin)
  const [filter, setFilter] = useState('')
  const [prefs, setPrefs] = useState<Prefs>(() => readJson<Prefs>(PREFS_KEY, { group: 'type', view: 'list', sort: 'created:-1', folded: [] }))
  const userBins = useUserBins()
  const binCount = useRef(userBins.bins.length)
  const [naming, setNaming] = useState<{ id: string | null; name: string } | null>(null)
  const [dropOn, setDropOn] = useState('')
  const filterRef = useRef<HTMLInputElement>(null)

  useEffect(() => { try { localStorage.setItem('llr.film.bin.v1', bin) } catch { /* optional preference */ } }, [bin])
  useEffect(() => writeJson(PREFS_KEY, prefs), [prefs])
  // A bin made anywhere (here or from the right-click menu) switches the list to My bins so it shows.
  useEffect(() => { if (userBins.bins.length > binCount.current) setPrefs(p => ({ ...p, group: 'bins' })); binCount.current = userBins.bins.length }, [userBins.bins.length])

  const sortDef = SORTS.find(s => s.id === prefs.sort) ?? SORTS[0]
  const sort = sortDef.key ? { key: sortDef.key, dir: sortDef.dir } : null
  const setSort = (key: SortKey | null, dir: 1 | -1) => setPrefs(p => ({ ...p, sort: key ? `${key}:${dir}` : 'none' }))
  const used = (item: BinItem) => usedCount.get(item.id) ?? 0
  const useOf = (item: BinItem): UseState => item.kind === 'still' ? 'reference' : inSequence.has(item.id) ? 'in sequence' : used(item) ? 'used' : 'unused'
  const binOf = (item: BinItem) => { const b = userBins.member[itemKey(item)]; return userBins.bins.find(x => x.id === b) }

  const rows = useMemo(() => {
    const text = filter.trim().toLowerCase()
    const inBin = (item: BinItem) => {
      switch (bin) {
        case 'all': return true
        case 'video': case 'audio': case 'still': return item.kind === bin
        case 'sequence': return inSequence.has(item.id)
        case 'unused': return item.kind !== 'still' && !usedCount.get(item.id)
      }
    }
    const value = (item: BinItem, key: SortKey): string | number => key === 'status' ? STATUS_ORDER.indexOf(useOf(item)) : key === 'used' ? used(item) : key === 'size' ? (item.width ?? 0) * (item.height ?? 0) : key === 'seconds' ? (item.seconds ?? -1) : (item[key] ?? '') as string | number
    const list = items.filter(item => inBin(item) && (!text || `${item.label} ${useOf(item)} ${item.kind} ${item.model ?? ''} ${item.seed ?? ''} ${binOf(item)?.name ?? ''}`.toLowerCase().includes(text)))
    if (sort) list.sort((a, b) => { const x = value(a, sort.key), y = value(b, sort.key); return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * sort.dir })
    return list
  }, [items, bin, filter, prefs.sort, usedCount, inSequence, userBins]) // eslint-disable-line react-hooks/exhaustive-deps

  const counts = useMemo(() => Object.fromEntries(BINS.map(b => [b.id, items.filter(item => b.id === 'all' || (['video', 'audio', 'still'].includes(b.id) ? item.kind === b.id : b.id === 'sequence' ? inSequence.has(item.id) : b.id === 'unused' && item.kind !== 'still' && !usedCount.get(item.id))).length])), [items, inSequence, usedCount])

  /** Rows split into collapsible groups. Empty user bins still show (so they can take drops). */
  const groups = useMemo(() => {
    type Group = { id: string; label: string; kind?: string; colour?: string; bin?: UserBin; rows: BinItem[] }
    const g = prefs.group
    if (g === 'none') return [{ id: 'all', label: 'All sources', rows }] as Group[]
    if (g === 'type') return (['video', 'audio', 'still'] as BinKind[]).map(k => ({ id: k, label: k === 'still' ? 'Stills' : KIND_LABEL[k], kind: k, rows: rows.filter(r => r.kind === k) })).filter(x => x.rows.length) as Group[]
    if (g === 'status') {
      return STATUS_ORDER.map(s => ({ id: s, label: STATUS_LABEL[s], kind: `status-${s.replace(' ', '-')}`, rows: rows.filter(r => useOf(r) === s) })).filter(x => x.rows.length) as Group[]
    }
    const known = new Set(userBins.bins.map(b => b.id))
    return [...userBins.bins.map(b => ({ id: b.id, label: b.name, colour: b.colour, bin: b, rows: rows.filter(r => userBins.member[itemKey(r)] === b.id) })),
      { id: UNSORTED, label: 'Unsorted', rows: rows.filter(r => !known.has(userBins.member[itemKey(r)])) }] as Group[]
  }, [rows, prefs.group, userBins])

  const folded = new Set(prefs.folded)
  const foldKey = (id: string) => `${prefs.group}:${id}`
  const toggleGroup = (id: string) => setPrefs(p => { const k = foldKey(id); return { ...p, folded: p.folded.includes(k) ? p.folded.filter(x => x !== k) : [...p.folded, k] } })
  const setAllFolded = (fold: boolean) => setPrefs(p => ({ ...p, folded: fold ? [...new Set([...p.folded, ...groups.map(x => foldKey(x.id))])] : p.folded.filter(k => !groups.some(x => foldKey(x.id) === k)) }))
  const visibleKeys = groups.filter(g => prefs.group === 'none' || !folded.has(foldKey(g.id))).flatMap(g => g.rows.map(itemKey))
  const selectedKeys = visibleSourceKeys(selection, rows.map(itemKey))
  const selected = new Set(selectedKeys)
  const picked = rows.filter(i => selected.has(itemKey(i)))
  const pickedBin = picked.length && picked.every(i => binOf(i)?.id === binOf(picked[0])?.id) ? binOf(picked[0])?.id ?? UNSORTED : '__mixed'

  function selectItem(item: BinItem, modifiers = {}) {
    onSelection(selectBrowserItem(selection, itemKey(item), visibleKeys, modifiers))
  }
  function selectionFor(item: BinItem) {
    const key = itemKey(item)
    if (selected.has(key)) return selectedKeys
    selectItem(item)
    return [key]
  }

  function moveTo(keys: string[], binId: string) {
    moveToUserBin(keys, binId === UNSORTED ? null : binId)
  }
  function saveBinName() {
    if (!naming) return
    const name = naming.name.trim()
    if (!name) { setNaming(null); return }
    if (naming.id) updateUserBins(u => ({ ...u, bins: u.bins.map(b => b.id === naming.id ? { ...b, name } : b) }))
    else {
      createUserBin(name, selectedKeys)
    }
    setNaming(null)
  }
  function deleteBin(b: UserBin, size: number) {
    if (size && !window.confirm(`Delete the bin "${b.name}"? Its ${size} source${size === 1 ? '' : 's'} move back to Unsorted. No media is deleted.`)) return
    updateUserBins(u => ({ bins: u.bins.filter(x => x.id !== b.id), member: Object.fromEntries(Object.entries(u.member).filter(([, v]) => v !== b.id)) }))
  }
  function dropProps(groupId: string) {
    if (prefs.group !== 'bins') return {}
    return {
      onDragOver: (e: DragEvent) => { if (e.dataTransfer.types.includes(DRAG_TYPE) || e.dataTransfer.types.includes(MULTI_DRAG_TYPE)) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDropOn(groupId) } },
      onDragLeave: (e: DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropOn(d => d === groupId ? '' : d) },
      onDrop: (e: DragEvent) => {
        e.preventDefault(); setDropOn('')
        const multi = e.dataTransfer.getData(MULTI_DRAG_TYPE)
        let keys: unknown
        try { keys = multi ? JSON.parse(multi) : [e.dataTransfer.getData(DRAG_TYPE)] } catch { return }
        if (!Array.isArray(keys)) return
        const known = new Set(items.map(itemKey))
        moveTo(keys.filter((k): k is string => typeof k === 'string' && known.has(k)), groupId)
      },
    }
  }

  function header(key: SortKey, label: string, title?: string) {
    const active = sort?.key === key
    return <button type="button" role="columnheader" aria-sort={active ? (sort!.dir === 1 ? 'ascending' : 'descending') : 'none'} title={title ?? `Sort by ${label.toLowerCase()}`}
      onClick={() => active ? (sort!.dir === 1 ? setSort(key, -1) : setSort(null, 1)) : setSort(key, 1)}>{label}{active ? (sort!.dir === 1 ? ' ▲' : ' ▼') : ''}</button>
  }
  function openMenu(item: BinItem, x: number, y: number) { onMenu(item, x, y, selectionFor(item)) }
  const duration = (item: BinItem) => item.seconds === null ? '' : item.seconds >= 60 ? `${Math.floor(item.seconds / 60)}:${(item.seconds % 60).toFixed(0).padStart(2, '0')}` : `${item.seconds.toFixed(2)}s`

  function row(item: BinItem) {
    const ub = binOf(item)
    const details = prefs.view === 'details'
    return <button key={itemKey(item)} data-source-key={itemKey(item)} data-kind={item.kind} data-use={useOf(item)} className={selected.has(itemKey(item)) ? 'selected' : ''} aria-pressed={selected.has(itemKey(item))} aria-current={openKey === itemKey(item) ? 'true' : undefined} data-picked={selected.has(itemKey(item)) || undefined}
      title={`${item.label} · ${item.kind} · ${STATUS_LABEL[useOf(item)].toLowerCase()}${item.note ? ` · ${item.note}` : ''} — Ctrl-click to toggle, Shift-click for a range; double-click or Enter to open; right-click or Shift+F10 for more`}
      draggable onDragStart={e => { const keys = selectionFor(item); e.dataTransfer.setData(DRAG_TYPE, itemKey(item)); e.dataTransfer.setData(MULTI_DRAG_TYPE, JSON.stringify(keys)); e.dataTransfer.effectAllowed = 'copyMove' /* move into a bin, copy onto the timeline */ }} onDragEnd={() => setDropOn('')}
      onClick={e => selectItem(item, e)} onDoubleClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey) onOpen(item) }}
      onContextMenu={e => { e.preventDefault(); openMenu(item, e.clientX, e.clientY) }}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); onOpen(item) }
        else if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); openMenu(item, r.left + 24, r.bottom) }
      }}>
      <i aria-hidden="true" className="fcp-status-mark" data-use={useOf(item)}>{STATUS_MARK[useOf(item)]}</i>
      <span className="fcp-thumb-wrap" aria-hidden="true">
        {item.kind === 'audio' ? <span className="fcp-thumb fcp-thumb-audio">♪</span> : <Thumb src={item.kind === 'video' ? item.media : undefined} image={item.kind === 'still' ? item.media : undefined} frame={item.thumbFrame ?? 0} cacheKey={`${item.id}:${item.thumbFrame ?? 0}`} />}
        <i className="fcp-kind-badge">{KIND_MARK[item.kind]}</i>
        {item.seconds !== null && prefs.view === 'grid' ? <i className="fcp-thumb-dur">{duration(item)}</i> : null}
      </span>
      {details ? <>
        <strong>{item.label}</strong>
        <span className="fcp-col-kind"><i aria-hidden="true">{KIND_MARK[item.kind]}</i> {item.kind}</span>
        <span>{useOf(item)}</span>
        <span>{item.seconds === null ? '—' : `${item.seconds.toFixed(2)}s`}</span>
        <span>{item.width && item.height ? `${item.width}×${item.height}` : '—'}</span>
        <span title={item.created}>{item.created ? item.created.slice(0, 10) : '—'}</span>
        <span>{item.kind === 'still' ? '—' : used(item)}</span>
        <span>{item.seed ?? '—'}</span>
        <span title={item.model}>{item.model ?? '—'}</span>
      </> : <span className="fcp-row-text">
        <strong>{item.label}</strong>
        <small className="fcp-row-meta">
          <b className="fcp-kind-tag">{KIND_LABEL[item.kind]}</b>
          {item.seconds !== null && prefs.view !== 'grid' ? <span>{duration(item)}</span> : null}
          {item.kind !== 'still' && used(item) ? <span title="Uses in saved sequences">used {used(item)}</span> : null}
          {inSequence.has(item.id) ? <span className="fcp-in-seq" title="In the open sequence">in seq</span> : null}
          {ub && prefs.group !== 'bins' ? <span className="fcp-bin-tag" style={{ '--bin': ub.colour } as CSSProperties}>{ub.name}</span> : null}
        </small>
      </span>}
    </button>
  }

  const view = prefs.view

  return <div className="fcp-bin-browser" data-view={view} tabIndex={-1} onKeyDown={e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); e.stopPropagation(); filterRef.current?.focus(); return }
    if ((e.target as HTMLElement).closest('input,select,textarea,[contenteditable=true]')) return
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'a') { e.preventDefault(); e.stopPropagation(); onSelection({ keys: visibleKeys, anchor: visibleKeys[0] ?? null }) }
    else if (e.key === 'Escape' || ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'a')) { e.preventDefault(); e.stopPropagation(); onSelection(emptyBrowserSelection) }
  }}>
    <div className="fcp-bin-chips" role="toolbar" aria-label="Automatic bins">
      {BINS.map(b => <button type="button" key={b.id} data-bin={b.id} aria-pressed={bin === b.id} title={b.title} onClick={() => setBin(b.id)}>{['video', 'audio', 'still'].includes(b.id) ? <i aria-hidden="true" className="fcp-kind-dot" data-kind={b.id} /> : null}{b.label} <small>{counts[b.id]}</small></button>)}
    </div>
    <div className="fcp-bin-tools">
      <div className="fcp-bin-tools-row fcp-bin-search">
        <input ref={filterRef} className="fcp-bin-filter" type="search" aria-label="Filter sources" placeholder="Filter: name, seed, bin, unused…" value={filter} onChange={e => setFilter(e.target.value)} />
        <button type="button" className="fcp-new-bin" onClick={() => setNaming({ id: null, name: '' })} title={picked.length ? `New bin with ${picked.length} selected source${picked.length === 1 ? '' : 's'}` : 'New bin'}>+ Bin</button>
        {prefs.group !== 'none' ? (() => { const anyOpen = groups.some(g => !folded.has(foldKey(g.id))); return <button type="button" className="fcp-fold-all" aria-label={anyOpen ? 'Collapse all groups' : 'Expand all groups'} title={anyOpen ? 'Collapse all groups' : 'Expand all groups'} onClick={() => setAllFolded(anyOpen)}>{anyOpen ? '⊟' : '⊞'}</button> })() : null}
      </div>
      <div className="fcp-bin-tools-row">
        <select aria-label="Group sources by" title="Group into collapsible sections" value={prefs.group} onChange={e => setPrefs(p => ({ ...p, group: e.target.value as GroupBy }))}>
          <option value="type">Type</option><option value="bins">My bins</option><option value="status">Use</option><option value="none">No groups</option>
        </select>
        <select aria-label="Sort sources" title="Sort order inside each group" value={sortDef.id} onChange={e => setPrefs(p => ({ ...p, sort: e.target.value }))}>{SORTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select>
        <span className="fcp-view-switch" role="group" aria-label="Browser view">
          {(['list', 'grid', 'details'] as View[]).map(v => <button type="button" key={v} aria-pressed={view === v} title={v === 'list' ? 'List: name and key facts' : v === 'grid' ? 'Thumbnails' : 'Details: every column (scrolls sideways when narrow)'} onClick={() => setPrefs(p => ({ ...p, view: v }))}><i aria-hidden="true" className={`fcp-view-icon fcp-view-${v}`} /><span className="fcp-sr">{v === 'list' ? 'List' : v === 'grid' ? 'Thumbnails' : 'Details'}</span></button>)}
        </span>
      </div>

      {naming && !naming.id ? <form className="fcp-bin-naming" onSubmit={e => { e.preventDefault(); saveBinName() }}>
        <input autoFocus aria-label="New bin name" placeholder="Bin name, e.g. Rain shots" maxLength={60} value={naming.name} onChange={e => setNaming({ ...naming, name: e.target.value })} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setNaming(null) } }} />
        <button disabled={!naming.name.trim()}>Create bin</button><button type="button" onClick={() => setNaming(null)}>Cancel</button>
      </form> : null}
    </div>
    <div className="fcp-bin-table">
      {view === 'details' ? <div className="fcp-bin-cols" role="row">
        <span aria-hidden="true" /><span aria-hidden="true" />{header('label', 'Name')}{header('kind', 'Type')}{header('status', 'Use', 'In this sequence, used in saved sequences, or unused')}{header('seconds', 'Duration')}{header('size', 'Size')}{header('created', 'Created')}
        {header('used', 'Used', 'Uses in saved sequences (shots and audio placements); unsaved edits not counted')}{header('seed', 'Seed')}{header('model', 'Model')}
      </div> : null}
      {groups.map(g => {
        const open = prefs.group === 'none' || !folded.has(foldKey(g.id))
        const hasOpen = g.rows.some(r => itemKey(r) === openKey), hasPick = g.rows.some(r => selected.has(itemKey(r)))
        const isBin = prefs.group === 'bins'
        return <section key={g.id} className="fcp-bin-group" data-drop={dropOn === g.id || undefined} {...dropProps(g.id)}>
          {prefs.group !== 'none' ? <div className="fcp-group-head" data-kind={g.kind} style={g.colour ? { '--bin': g.colour } as CSSProperties : undefined}>
            {naming?.id === g.id ? <form className="fcp-bin-naming" onSubmit={e => { e.preventDefault(); saveBinName() }}>
              <input autoFocus aria-label="Bin name" maxLength={60} value={naming.name} onChange={e => setNaming({ ...naming, name: e.target.value })} onBlur={saveBinName} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setNaming(null) } }} />
            </form> : <button type="button" aria-expanded={open} onClick={() => toggleGroup(g.id)} title={open ? 'Collapse' : 'Expand'}>
              <i aria-hidden="true" className="fcp-fold" />
              <i aria-hidden="true" className={isBin ? (g.bin ? 'fcp-bin-swatch' : 'fcp-bin-swatch fcp-bin-swatch-none') : 'fcp-kind-dot'} data-kind={g.kind} />
              <span>{g.label}</span><small>{g.rows.length}</small>
              {!open && (hasOpen || hasPick) ? <em className="fcp-group-hint">{hasOpen ? 'open item' : 'selected'}</em> : null}
            </button>}
            {g.bin && naming?.id !== g.id ? <span className="fcp-group-actions">
              <button type="button" title={`Rename the bin "${g.label}"`} aria-label={`Rename bin ${g.label}`} onClick={() => setNaming({ id: g.bin!.id, name: g.bin!.name })}>✎</button>
              <button type="button" title={`Delete the bin "${g.label}" (sources move to Unsorted)`} aria-label={`Delete bin ${g.label}`} onClick={() => deleteBin(g.bin!, g.rows.length)}>✕</button>
            </span> : null}
          </div> : null}
          {open ? <div className="film-assets fcp-bin">
            {g.rows.map(row)}
            {!g.rows.length ? <p className="fcp-bin-empty">{isBin && g.bin ? 'Empty. Drag sources here, or pick one and use "Move to bin" below.' : 'Nothing here.'}</p> : null}
          </div> : null}
        </section>
      })}
      {!rows.length ? <p className="fcp-bin-empty">{items.length ? 'No sources in this bin match.' : 'No sources yet.'}</p> : null}
    </div>
    <p className="fcp-bin-selection-help">Ctrl-click: toggle · Shift-click: range · Ctrl+A: select visible</p>
    {picked.length ? <div className="fcp-bin-picked" data-kind={picked.length === 1 ? picked[0].kind : undefined}>
      <span role="status" title={picked.map(i => i.label).join(', ')}>{picked.length === 1 ? picked[0].label : `${picked.length} sources selected`}</span>
      <button type="button" aria-label="Clear source selection" onClick={() => onSelection(emptyBrowserSelection)}>✕</button>
      <label>Bin<select aria-label="Move to bin" value={pickedBin} onChange={e => { if (e.target.value === '__new') setNaming({ id: null, name: '' }); else moveTo(selectedKeys, e.target.value) }}>
        <option value="__mixed" disabled>Mixed bins</option>
        <option value={UNSORTED}>Unsorted</option>{userBins.bins.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}<option value="__new">New bin…</option>
      </select></label>
    </div> : null}
  </div>
}
