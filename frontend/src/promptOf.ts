// The recorded prompt of a clip, wherever its importer put it. Owned jobs first: their brief is full length,
// while an imported asset's provenance may hold only a receipt for a brief over 1000 characters.
type Rec = Record<string, unknown>
const obj = (v: unknown): Rec | undefined => v && typeof v === 'object' && !Array.isArray(v) ? v as Rec : undefined
const str = (v: unknown) => typeof v === 'string' && v.trim() ? v : undefined

export function promptOf(provenance?: Rec | null, jobMetadata?: Rec | null): string | undefined {
  const p = obj(provenance), gm = obj(p?.generation_metadata), g = obj(p?.generation), d = obj(p?.draft)
  return str(jobMetadata?.brief) ?? str(gm?.brief) ?? str(gm?.prompt) ?? str(g?.brief) ?? str(g?.prompt) ?? str(d?.prompt) ?? str(p?.brief) ?? str(p?.prompt)
}
