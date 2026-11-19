import type { ReactNode } from 'react'

/** Icons for right-click menu items, keyed by action so the same action looks the same in every menu.
 *  Every entry is a placeholder for now (a dashed square with a letter). To add a handcrafted icon, put a 16×16 SVG
 *  (stroke="currentColor") in ICONS under its id; MenuIcon uses it instead of the placeholder. */
export type MenuIconId =
  | 'open-viewer' | 'open-audio' | 'open-still' | 'review' | 'audition' | 'reject'
  | 'insert' | 'overwrite' | 'append' | 'place-take' | 'place-a1' | 'place-a2'
  | 'lift' | 'ripple-delete' | 'close-gap' | 'move-earlier' | 'move-later' | 'continue-shot'
  | 'mute' | 'unmute' | 'remove'
  | 'import' | 'guide' | 'show-history' | 'flag-here' | 'flag-remove' | 'hide' | 'show'
  | 'bin-move' | 'bin-new' | 'bin-out'

const PLACEHOLDER: Record<MenuIconId, string> = {
  'open-viewer': 'V', 'open-audio': 'A', 'open-still': 'S', review: 'R', audition: 'P', reject: 'X',
  insert: 'I', overwrite: 'O', append: '+', 'place-take': 'T', 'place-a1': '1', 'place-a2': '2',
  lift: 'L', 'ripple-delete': 'D', 'close-gap': 'G', 'move-earlier': '<', 'move-later': '>', 'continue-shot': 'C',
  mute: 'M', unmute: 'U', remove: '-',
  import: 'i', guide: '?', 'show-history': 'H', 'flag-here': 'F', 'flag-remove': 'f', hide: 'h', show: 's',
  'bin-move': 'B', 'bin-new': 'b', 'bin-out': 'u',
}

/** Handcrafted icons go here, e.g. 'insert': <svg viewBox="0 0 16 16">…</svg>. */
const ICONS: Partial<Record<MenuIconId, ReactNode>> = {}

export const MENU_ICON_IDS = Object.keys(PLACEHOLDER) as MenuIconId[]

export function MenuIcon({ id }: { id: MenuIconId }) {
  const art = ICONS[id]
  return <span className="ctx-icon" data-icon={id} aria-hidden="true">{art ?? <span className="ctx-icon-placeholder">{PLACEHOLDER[id]}</span>}</span>
}
