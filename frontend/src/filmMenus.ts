/** Film editor menu bar (FCP7-style menus). Pure data, so a check can confirm every command exists and is handled.
 *  A string is a command id (runs the same code as its key); an object is an editor action without a key. */
export type MenuAction = 'newSequence' | 'import' | 'cleanup' | 'generate' | 'history' | 'guide' | 'keyboard'
export type MenuItem = string | { action: MenuAction; label: string } | '-'
export const FILM_MENUS: { label: string; items: MenuItem[] }[] = [
  { label: 'File', items: [{ action: 'newSequence', label: 'New sequence…' }, { action: 'import', label: 'Import / generated sources…' }, { action: 'cleanup', label: 'Clean up clips…' }, '-', 'edit.save', 'edit.saveAll', '-', 'edit.render'] },
  { label: 'Edit', items: ['edit.undo', 'edit.redo', '-', 'edit.lift', 'edit.rippleDelete', 'edit.liftRange', 'edit.extractRange', '-', 'edit.deselect'] },
  { label: 'Mark', items: ['mark.in', 'mark.out', 'mark.clip', '-', 'mark.clearIn', 'mark.clearOut', 'mark.clearBoth', '-', 'nav.in', 'nav.out', '-', 'mark.add', 'mark.delete', 'mark.deleteAll', 'nav.prevMarker', 'nav.nextMarker', '-', 'nav.matchFrame'] },
  { label: 'Sequence', items: ['edit.insert', 'edit.overwrite', 'edit.replace', '-', 'edit.addEdit', 'edit.selectEdit', 'edit.toggleSide', 'edit.extend', 'edit.trimBack', 'edit.trimForward', 'edit.trimBackMulti', 'edit.trimForwardMulti', '-', 'timeline.snap'] },
  { label: 'Tools', items: ['tool.select', 'tool.razor', 'tool.roll', 'tool.slip'] },
  { label: 'Playback', items: ['play.toggle', 'play.stop', 'play.reverse', 'play.forward', 'play.inToOut', 'play.around', '-', 'nav.start', 'nav.end', 'nav.prevEdit', 'nav.nextEdit', 'nav.prevFrame', 'nav.nextFrame'] },
  { label: 'View', items: ['timeline.zoomIn', 'timeline.zoomOut', 'timeline.fit', 'timeline.trackSize', '-', 'window.standard'] },
  { label: 'Window', items: ['window.browser', 'window.viewer', 'window.canvas', 'window.timeline', 'window.toggleMonitor', 'window.find', '-', { action: 'generate', label: 'Generate' }, { action: 'history', label: 'Queue' }] },
  { label: 'Help', items: [{ action: 'guide', label: 'Generation guide' }, { action: 'keyboard', label: 'Keyboard layout…' }] },
]
/** Command ids used in the menus (for the check). */
export const MENU_COMMANDS = FILM_MENUS.flatMap(m => m.items.filter((i): i is string => typeof i === 'string' && i !== '-'))
