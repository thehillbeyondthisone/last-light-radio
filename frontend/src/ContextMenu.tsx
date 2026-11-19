import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { MenuIcon } from './menuIcons'
import type { MenuIconId } from './menuIcons'

/** Shared right-click menu (dark, two-line items: what it is, then what it does).
 *  The editor builds the entries at render time from what was right-clicked, so they always reflect current state. */
export type MenuTone = 'view' | 'edit' | 'review' | 'danger'
export interface MenuEntry {
  id: string
  icon: MenuIconId
  label: string
  /** Second line: what happens. Replaced by `disabled` when the item can't be used, so it never silently does nothing. */
  hint: string
  shortcut?: string
  tone?: MenuTone
  disabled?: string | null
  run: () => void
}
export interface ContextMenuProps { x: number; y: number; title: string; subtitle?: string; sections: MenuEntry[][]; onClose: () => void }

export default function ContextMenu({ x, y, title, subtitle, sections, onClose }: ContextMenuProps) {
  const menu = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; maxHeight?: number } | null>(null)
  // Keep the menu on screen: flip up or left near the edges, and scroll if it is taller than the window.
  useLayoutEffect(() => {
    const el = menu.current; if (!el) return
    const place = () => {
      const w = el.offsetWidth, h = el.scrollHeight, vw = window.innerWidth, vh = window.innerHeight, m = 4
      const left = Math.max(m, x + w > vw - m ? x - w : x)
      let top = y + h > vh - m ? y - h : y
      if (top < m) top = Math.max(m, vh - h - m)
      const next = { left: Math.min(left, Math.max(m, vw - w - m)), top, maxHeight: h > vh - 2 * m ? vh - 2 * m : undefined }
      setPos(p => p && p.left === next.left && p.top === next.top && p.maxHeight === next.maxHeight ? p : next)
    }
    place()
    // Hints can re-wrap once fonts settle: place it again if its size changes.
    const watch = new ResizeObserver(place); watch.observe(el)
    return () => watch.disconnect()
  }, [x, y, sections.length])
  // Give focus back to where it was when the menu closes.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    return () => { if (before && document.contains(before)) before.focus({ preventScroll: true }) }
  }, [])
  // Focus the first usable item once the menu is visible (a hidden element cannot take focus).
  const focused = useRef(false)
  useEffect(() => {
    if (!pos || focused.current) return
    focused.current = true
    menu.current?.querySelector<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)')?.focus({ preventScroll: true })
  }, [pos])
  const items = () => [...(menu.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)') ?? [])]
  const shown = sections.filter(s => s.length)
  return <div className="ctx-backdrop" onMouseDown={onClose} onContextMenu={e => { e.preventDefault(); onClose() }}>
    <div ref={menu} role="menu" aria-label={`Actions for ${title}`} className="ctx-menu"
      style={pos ? { left: pos.left, top: pos.top, maxHeight: pos.maxHeight } : { left: x, top: y, visibility: 'hidden' }}
      onMouseDown={e => e.stopPropagation()} onKeyUp={e => e.stopPropagation()}
      onKeyDown={e => {
        // Keys stay in the menu: the editor's shortcuts (Space plays, Enter opens) listen on window.
        e.stopPropagation()
        const all = items(), i = all.indexOf(document.activeElement as HTMLButtonElement)
        if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); onClose() }
        else if (e.key === 'ArrowDown') { e.preventDefault(); all[(i + 1) % all.length]?.focus() }
        else if (e.key === 'ArrowUp') { e.preventDefault(); all[(i + all.length - 1) % all.length]?.focus() }
        else if (e.key === 'Home') { e.preventDefault(); all[0]?.focus() }
        else if (e.key === 'End') { e.preventDefault(); all[all.length - 1]?.focus() }
      }}>
      <div className="ctx-head" role="presentation"><strong>{title}</strong>{subtitle ? <span>{subtitle}</span> : null}</div>
      {shown.map((section, n) => <div key={n} role="group" className="ctx-section">
        {section.map(item => <button key={item.id} type="button" role="menuitem" data-tone={item.tone ?? 'view'} disabled={!!item.disabled}
          aria-label={item.label} aria-describedby={`ctx-hint-${item.id}`}
          onClick={() => { onClose(); window.setTimeout(item.run, 0) /* after the menu is gone and focus is restored (Reject opens a prompt) */ }}>
          <MenuIcon id={item.icon} />
          <span className="ctx-text"><span className="ctx-label">{item.label}</span><span className="ctx-hint" id={`ctx-hint-${item.id}`}>{item.disabled || item.hint}</span></span>
          {item.shortcut ? <kbd className="ctx-key">{item.shortcut}</kbd> : null}
        </button>)}
      </div>)}
    </div>
  </div>
}
