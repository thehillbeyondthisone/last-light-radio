import { useEffect, useRef, useState } from 'react'
import { COMMAND_BY_ID, formatChord } from './shortcuts'
import type { Keymap } from './shortcuts'
import { FILM_MENUS } from './filmMenus'
import type { MenuAction } from './filmMenus'

/** FCP7-style menu bar. Items run the same command code as their keys and show the current (possibly customised) key.
 *  Menu items exist only while a menu is open, so they never shadow the toolbar buttons of the same name. */
const tidy = (label: string) => label.replace(/ \(Film editor\)$/, '').split(' — ')[0].replace(/ \(Film editor\)/, '')

export default function FilmMenuBar({ keymap, disabled, onCommand, onAction }: { keymap: Keymap; disabled: boolean; onCommand: (id: string) => void; onAction: (a: MenuAction) => void }) {
  const [open, setOpen] = useState<number | null>(null)
  const bar = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (open === null) return
    const close = (e: MouseEvent) => { if (!bar.current?.contains(e.target as Node)) setOpen(null) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])
  useEffect(() => { if (open !== null) bar.current?.querySelector<HTMLElement>('[role=menu] [role=menuitem]:not(:disabled)')?.focus() }, [open])
  function run(item: string | { action: MenuAction }) { setOpen(null); if (typeof item === 'string') onCommand(item); else onAction(item.action) }
  return <div ref={bar} className="film-menubar" role="menubar" aria-label="Film editor menus"
    onKeyDown={e => {
      e.stopPropagation() // menu keys must not reach the editor shortcuts
      if (e.key === 'Escape') { e.preventDefault(); setOpen(null) }
      else if (open !== null && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) { e.preventDefault(); setOpen((open + (e.key === 'ArrowRight' ? 1 : FILM_MENUS.length - 1)) % FILM_MENUS.length) }
      else if (open !== null && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault()
        const items = [...(bar.current?.querySelectorAll<HTMLElement>('[role=menu] [role=menuitem]:not(:disabled)') ?? [])]
        const i = items.indexOf(document.activeElement as HTMLElement)
        items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus()
      }
    }}>
    {FILM_MENUS.map((menu, mi) => <div key={menu.label} className="film-menu">
      <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={open === mi} disabled={disabled} onMouseDown={e => e.preventDefault()}
        onClick={() => setOpen(open === mi ? null : mi)} onMouseEnter={() => { if (open !== null && open !== mi) setOpen(mi) }}
        onKeyDown={e => { if (e.key === 'ArrowDown' || e.key === 'Enter') { e.preventDefault(); setOpen(mi) } }}>{menu.label}</button>
      {open === mi ? <div role="menu" aria-label={menu.label} className="film-menu-list">
        {menu.items.map((item, i) => {
          if (item === '-') return <hr key={i} role="separator" />
          if (typeof item === 'string') {
            const command = COMMAND_BY_ID.get(item); if (!command) return null
            const key = keymap[item]?.[0]
            return <button key={item} type="button" role="menuitem" title={command.label} onMouseDown={e => e.preventDefault()} onClick={() => run(item)}><span>{tidy(command.label)}</span>{key ? <kbd>{formatChord(key)}</kbd> : null}</button>
          }
          return <button key={item.action} type="button" role="menuitem" onMouseDown={e => e.preventDefault()} onClick={() => run(item)}><span>{item.label}</span></button>
        })}
      </div> : null}
    </div>)}
  </div>
}
