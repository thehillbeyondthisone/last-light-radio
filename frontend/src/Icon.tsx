export type IconName = 'scene' | 'spark' | 'review' | 'plus' | 'arrow' | 'check' | 'close' | 'settings' | 'upload' | 'lock' | 'play' | 'pause' | 'refresh' | 'chevron' | 'radio'
const paths: Record<IconName, string> = {
  scene: 'M3 5h18v14H3z M3 15l5-5 5 5 3-3 5 5 M16 8h.01',
  spark: 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  review: 'M7 4h10l3 3v13H4V7z M9 4V2h6v2 M8 12l3 3 5-6',
  plus: 'M12 5v14 M5 12h14', arrow: 'M4 12h15 M13 6l6 6-6 6',
  check: 'M5 12l4 4L19 6', close: 'M6 6l12 12 M6 18L18 6',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  upload: 'M12 16V3 M7 8l5-5 5 5 M4 15v6h16v-6', lock: 'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4',
  play: 'M8 4l12 8-12 8z', pause: 'M8 5v14 M16 5v14',
  refresh: 'M20 8a8 8 0 1 0 0 8 M20 3v5h-5', chevron: 'M9 5l7 7-7 7',
  radio: 'M4 8h16v12H4z M4 8l14-5 M8 12h8 M8 16h.01 M12 16h4',
}
export default function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
