import type { AmbienceLayer, PilotSummary } from './types'

export interface SubjectSettings { actor: string; mode: 'continuous' | 'spaced' | 'still'; seed: number; pool: string[] }
export interface Placement { id: string; candidate_id: string; start_frame: number; end_frame?: number; actor?: string }
export interface TextureSettings { enabled: boolean; strength: number; size: number; seed: number }
export interface TextureRecipe extends TextureSettings { renderer_version: 'video-texture-v1'; clock: 'absolute_episode_frame'; blend: 'overlay'; tile_size: number }
export interface EditorConfig {
  scene_id: string; title: string; fps: number; duration_frames: number; seed: number
  subjects: SubjectSettings[]; placements: Placement[]; ambience: { kind: 'rain' | 'steam'; opacity: number }[]
  audio_tracks?: AudioPlacement[]
  texture?: TextureSettings
}
export interface EditorClip { id: string; label: string; actor: string; role: string; frames: number; state: string }
export interface EditorState {
  revision: number; config: EditorConfig; sequence_id: string | null; actors: string[]; clips: EditorClip[]
  excluded: { id: string; label: string; reason: string }[]
}
export interface SubjectEvent {
  index: number; kind: 'clip' | 'hold'; origin: 'motion' | 'idle' | 'hold'; actor: string
  start_frame: number; end_frame: number; label: string; variant_id?: string; layer_clip_id?: string; placement_id?: string
}
export interface SubjectSequence extends PilotSummary {
  manifest: {
    kind: 'studio_subject_sequence'; title: string; width: number; height: number; fps: number; duration_frames: number
    manifest_hash: string; tracks: { actor: string; events: SubjectEvent[] }[]; events: SubjectEvent[]
    clips: { id: string; actor: string; label: string; frames: number }[]; config: EditorConfig
    ambience?: { renderer_version: string; clock: string; layers: AmbienceLayer[] }; steam_pauses: [number, number][]
    texture?: TextureRecipe | null
  }
}
export interface EditorSave { revision: number; config: EditorConfig; sequence_id: string; sequence: SubjectSequence }
export function timecode(frame: number, fps = 24) {
  const seconds = Math.floor(frame / fps)
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60, frame % fps].map(v => String(v).padStart(2, '0')).join(':')
}

export interface AudioPlacement { id: string; role: 'production' | 'music'; asset_id: string; start_frame: number; source_in_frame: number; duration_frames: number; gain_db: number; fade_in_frames: number; fade_out_frames: number; enabled: boolean }
export interface AudioAsset { id: string; label: string; status: 'candidate' | 'approved' | 'rejected'; duration_seconds: number; media_url: string; version: number; source?: { path: string; sha256: string }; provenance?: Record<string, unknown> }

