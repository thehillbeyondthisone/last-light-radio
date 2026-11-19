export type TrackDensity = 'default' | 'reduced' | 'small' | 'standard' | 'large'

// Track geometry matches editor.css. Screen space never changes episode data.
export function timelineHeight(subjects: number, effects: number, density: TrackDensity, nested: boolean) {
  const rows = nested ? 1 : subjects * 2 + effects + 3
  const height = density === 'reduced' ? 12 : density === 'small' ? 22 : density === 'large' ? 52 : 32
  return 20 + rows * height + (nested ? 0 : subjects) + 66
}

export function monitorHeight(available: number, requested: number, tracks: number, fit: boolean) {
  const minimum = Math.min(220, Math.max(100, available - 190))
  const maximum = Math.max(minimum, available - 190)
  return Math.round(Math.max(minimum, Math.min(maximum, fit ? available - tracks : requested)))
}

export function rulerStep(scale: number) {
  return [1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600].find(seconds => seconds * scale >= 65) ?? 3600
}

