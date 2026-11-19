import { useThumb } from './thumbs'

/** A small poster frame. Decorative only (alt="", aria-hidden), so button text and labels are unchanged. */
export default function Thumb({ src, frame, cacheKey, className = 'fcp-thumb', image }: { src?: string; frame: number; cacheKey: string; className?: string; image?: string }) {
  const { ref, url } = useThumb(image ? undefined : src, frame, cacheKey)
  const shown = image ?? url
  return <span ref={ref} className={className} aria-hidden="true">{shown ? <img src={shown} alt="" draggable={false} /> : null}</span>
}
