/** Browser keys include the item kind so equal ids in different libraries stay distinct. */
export interface BrowserSelection { keys: string[]; anchor: string | null }
export const emptyBrowserSelection: BrowserSelection = { keys: [], anchor: null }

/** Range order comes from the displayed, expanded rows, never the underlying library order. */
export function selectBrowserItem(selection: BrowserSelection, key: string, visible: string[], modifiers: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {}): BrowserSelection {
  const additive = modifiers.ctrlKey || modifiers.metaKey
  const start = selection.anchor ? visible.indexOf(selection.anchor) : -1
  const end = visible.indexOf(key)
  if (modifiers.shiftKey && start >= 0 && end >= 0) {
    const range = visible.slice(Math.min(start, end), Math.max(start, end) + 1)
    return { keys: additive ? [...new Set([...selection.keys, ...range])] : range, anchor: selection.anchor }
  }
  return { keys: additive ? selection.keys.includes(key) ? selection.keys.filter(k => k !== key) : [...selection.keys, key] : [key], anchor: key }
}

/** Hidden/removed sources never participate in a bulk bin operation. Sequence selections are separate. */
export function visibleSourceKeys(selection: BrowserSelection, visible: string[]): string[] {
  const selected = new Set(selection.keys)
  return visible.filter(key => selected.has(key))
}
