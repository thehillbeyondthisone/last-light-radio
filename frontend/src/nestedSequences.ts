import type { SubjectEvent } from './editorTypes'

export interface IdleBed { actor: string; name: string; start_frame: number; end_frame: number; events: SubjectEvent[] }

function bedName(actor: string, events: SubjectEvent[]) {
  const labels = [...new Set(events.filter(e => e.origin === 'idle').map(e => e.label))]
  if (!labels.length) return `${actor} · holds`
  let words = labels[0].split(' ')
  for (const label of labels.slice(1)) {
    const next = label.split(' ')
    words = words.filter((word, index) => next[index] === word && words.slice(0, index).every((w, i) => w === next[i]))
  }
  return words.join(' ').replace(/\s+idle$/i, '').trim() || `${actor} · idles`
}

export function idleBeds(actor: string, events: SubjectEvent[]): IdleBed[] {
  const beds: IdleBed[] = []
  for (const event of events) {
    if (event.origin === 'motion') continue
    const previous = beds.at(-1)
    if (previous && previous.end_frame === event.start_frame) {
      previous.events.push(event); previous.end_frame = event.end_frame
    } else beds.push({ actor, name: '', start_frame: event.start_frame, end_frame: event.end_frame, events: [event] })
  }
  return beds.map(bed => ({ ...bed, name: bedName(actor, bed.events) }))
}
