export type View = 'film' | 'editor' | 'scenes' | 'setup' | 'generate' | 'review' | 'pilot' | 'worker'
export type ReviewStatus = 'candidate' | 'approved' | 'rejected'
export interface Scene {
  id: string; title: string; description: string; width: number; height: number
  fixture: boolean; created: string; master_hash: string
  master: { id: string; path: string; sha256: string }
  image_url: string; thumbnail_url: string
}
export interface Review {
  version: number; decision: ReviewStatus; notes: string; entry_anchor: string
  exit_anchor: string; created: string
}
export interface MediaProperties {
  container?: string
  width: number; height: number; frame_count: number; duration_seconds: number
  effective_fps: number; pixel_decode_verified: boolean
}
export interface ActorCrop { x: number; y: number; width: number; height: number }
export interface MotionProfile {
  id: string; name: string; scene_id: string; actor: string; role: string
  start_state: string; end_state: string; crop: ActorCrop
  frames: number; fps: number; seed: number; prompt: string
  reference_candidate_id?: string; first_scene_id: string; last_scene_id: string
  mask_url: string; first_url: string; last_url: string
  origin?: 'authored'; revision?: number; parent_id?: string; family_id?: string; vae_name?: string
  authoring?: { template_id: string; polygon?: [number, number][]; geometry?: string; feather: number; context: number }
  creative_direction?: { starter_id: string; description: string }
  mask_edit?: { version: number; source_candidate_id: string }
  conditioning_transform?: { fitted_box: number[]; source_box: number[]; conditioning_size: number[] }
  hold_policy?: string
}
export interface Candidate {
  id: string; scene_id: string; label: string; status: ReviewStatus; version: number
  created: string; media_url: string; frames: { start: string; middle: string; end: string }
  crop_url?: string
  can_adjust_area?: boolean
  source_frames?: { start: string; middle: string; end: string }
  reviews: Review[]
  metadata: {
    legacy?: boolean
    motion?: {
      profile?: { id: string }
      profile_id: string; actor: string; crop: ActorCrop; start_state: string; end_state: string
      reference_candidate_id: string; mask_sha256?: string; mask?: { sha256: string }; compositing_policy?: string
      composite_policy?: { color_policy?: string; historical_algorithm_status?: string }
      vae_name?: string
    }
    prompt_id: string; workflow_sha256: string
    execution?: { runtime_seconds?: number }
    parameters: Record<string, string | number | boolean>
    outputs: { sha256: string; path: string; properties: MediaProperties }[]
  }
}
export interface Job {
  id: string; scene_id: string; label: string; status: string; created: string
  motion_profile_id?: string
  can_resume: boolean; error: { code: string; message: string } | null
}
export interface Worker {
  connected: boolean; url: string; checked_at?: string | null; workflow_valid?: boolean
  production_workflow_valid?: boolean
  production_errors?: { message: string }[]
  node_count?: number; devices?: { name: string; vram_total: number }[]
  errors?: { message: string }[]
}
export interface StudioState {
  ambience_catalog?: { scene_id: string; layers: { kind: 'rain' | 'steam'; label: string; opacity: number }[] }[]
  pilot_catalog?: { scene_id: string; approved_count: number; clips: { id: string; label: string; actor: string; start_state: string; end_state: string }[]; excluded: { id: string; label: string; reason: string }[] }[]
  pilots?: PilotSummary[]
  sequences?: PilotSummary[]
  imports: { source: string; scene_count: number; candidate_count: number; sequence_count: number; failed_candidates_retained: number }[]
  scenes: Scene[]; candidates: Candidate[]; jobs: Job[]; worker: Worker
  motion_profiles?: MotionProfile[]
  motion_templates?: { id: string; name: string; description: string; direction: string }[]
  motion_starters?: { id: string; name: string; direction: string; hint: string; template_id: string; frames: number }[]
  motion_restrictions?: string
  production?: { default_vae_name: string; available_vae_names: string[]; original_vae_name: string }
  workflow: { name: string; confirmed: boolean; parameters: Record<string, string | number | boolean> }
}
export interface PilotEvent {
  index: number; kind: 'clip' | 'hold'; start_frame: number; end_frame: number; label: string
  variant_id?: string; actor?: string; start_state?: string; end_state?: string
  frame_image?: { path: string; sha256: string }; entry_image?: { path: string; sha256: string }; exit_image?: { path: string; sha256: string }
}
export interface PilotSummary {
  kind?: string
  id: string; scene_id: string; title: string; status: string; progress: number; created: string
  error: { message: string } | null; approval_current: boolean; media_url: string | null; manifest_url: string; log_url: string
}
export interface Pilot extends PilotSummary {
  manifest: {
    steam_pauses?: [number, number][]
    ambience?: { renderer_version: string; clock: string; layers: AmbienceLayer[] }
    title: string; fps: number; duration_frames: number; width: number; height: number; seed: number; density: string
    manifest_hash: string; audio: string; events: PilotEvent[]
    clips: { id: string; label: string; actor: string; approval_version: number }[]
    joins: { at_frame: number; candidate_id: string; whole_frame_mean_absolute_rgb_0_255: number; exact_rgb_match: boolean }[]
  }
}
export interface AmbienceLayer {
  kind: 'rain' | 'steam'; label: string; opacity: number; bounds: [number, number, number, number]
  particles: { x: number; y: number; speed: number; length: number; alpha: number; phase: number; depth?: number }[]
  glass_model?: string
  glass?: GlassDrop[]
}
export interface GlassDrop {
  x: number; y: number; speed: number; radius: number; trail: number; alpha: number; phase: number
  roll?: { keys: [number, number][]; duration: number; offset: number; wander: number; trail_seconds: number }
}

