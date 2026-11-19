# Last Light Radio — HANDOFF_PLAN.md

**Handoff date:** 2026-10-18  
**Audience:** Codex / developer continuing the project with no previous chat context  
**Authority:** `PROJECT_TRUTHS.md` (confirmed decisions) > this plan (implementation proposal) > `MVP_TASKLIST.md` (execution order).  
**Project state:** planning/reconstruction. **No working code, H3 workflow file or benchmark has been verified as part of this package.** If any existing source is discovered, inventory and reconcile it first.

## 0. The concept in 60 seconds

**A tool that turns a single fixed, beautiful scene into an entire lived-in episode.** A woman reads, changes position, sometimes drinks tea or crosses the room; a cat naps, wakes, scratches and moves around; traffic, rain, lights, radio and music carry on. An episode lasts 60–90 minutes (or any configured duration) **without obviously replaying the same five seconds**.

**A world that continues between episodes.** The same cat may appear in a nearby apartment, the same bus route passes the convenience store, the same radio station plays in two different buildings, and the season advances over time. Each episode is a standalone listening/watching experience, but regular viewers can notice relationships and small continuing stories. Think *connected windows into one neighborhood*, not a playlist of unrelated AI clips.

**A production application, not an AI agent.** The creator imports any suitable still, defines regions, actors, behaviors, variations, timing and canon, generates candidate animations through ComfyUI on the LAN, approves usable clips, and lets a deterministic scheduler assemble/export the episode. User-supplied worlds and visual styles are supported; Last Light Radio is an example project created with this general-purpose tool.

**Illustrative episode links, not approved canon:** `Summer Rain` looking across a rainy intersection; `The Night Shift` at a convenience store in the same neighborhood; `Before Sunrise` in a nearby apartment. Bus 271, an orange cat and UMBRA FM 88.3 could reappear. These are sample continuity tests, not instructions to invent/lock story beats.

## 1. Outcomes and guardrails

### Success looks like
1. Import an unchanged `MASTER.png` and designate visible characters/props/ambient regions.
2. Register local ComfyUI on another LAN PC (H3 workflow provided by creator); submit an action render and retrieve candidate output.
3. Review and approve **multiple variants** of a given idle or action.
4. Author behavior rules in an approachable editor: action pools, weights, min/max gaps, cooldowns, prerequisites, transitions, schedules and rare events.
5. Produce a 10-minute reproducible pilot without live prompting/agent involvement; configure longer 60–90-minute episodes using the same mechanism.
6. Export a watchable video with continuous audio, a timeline manifest and a detailed event log.
7. Make **two different scene/episode records belonging to the same world**. A persistent continuity element can appear in both; world facts and chronology remain consistent after approval.
8. Reopen the project later and regenerate an episode from its world revision, seed and clip manifest without losing visual/semantic references.

### Non-goals for first release
- Training new video models; automated 3D reconstruction; moving-camera cinematography; fully generated continuous 90-minute AI video; cloud accounts; real-time multi-user collaboration; auto-scriptwriting; autonomous canon changes; automatic image segmentation; complex 2D physics/rigging; public video hosting.
- Automatic generation of *new lore* at runtime. A director can recombine authored events, but not fabricate world facts.
- Compositing two unrelated full-frame generative videos at once. Different logical character schedules do **not** imply their frames can simply be layered.

## 2. Product architecture

```text
                             CREATOR UI (local application)
        Image / region editor | behavior pools | world bible | review | timeline
                                          |
                                          v
                               LOCAL PROJECT SERVICE
         ---------------------------------------------------------------
         | Project/asset store | World Registry | Scene/Clip Registry   |
         | Deterministic World/Episode Director | Job/event log         |
         ---------------------------------------------------------------
                     |                              |
              workflow adapter                  timeline engine
                     |                              |
           COMFYUI ON LAN (H3 first)              media assembly
           optional future models                FFmpeg / exports
                     |                              |
            candidate clips --------------> approved library
                                                      |
                                   final MP4 + manifest + project data
```

**Boundaries that should remain clean:**
- **World Registry:** geography, entities, relationships, canonical facts and chronology; does not know specific generation node IDs.
- **Scene Registry:** each canonical image, camera/style restrictions, entity hit regions, environment/prop anchors.
- **Motion Library:** idles, actions, candidate clips, approved variants, transitions, provenance and visual/state contracts.
- **World Director:** selects only user-authored, canon-compatible circumstances, references or small events; never silently changes canon.
- **Episode Director:** seeded deterministic schedule; resolves eligibility/conflicts, applies states and cooldowns, emits a frame-accurate manifest; no LLM/model calls.
- **Generation Adapter:** transforms a tested workflow template into a ComfyUI prompt for an explicit asset request; can be swapped for different models.
- **Media Engine:** assembles approved clips, static holds, verified effects, audio and transitions; exports/validates delivery files.
- **UI:** creator-visible controls and status. The UI never contains hidden scheduling rules that are absent from persisted project data.

### Recommended initial stack (proposed, **not yet approved**)
- **Windows-first** local-first application.
- **Backend:** Python 3.11+ with FastAPI/Pydantic or equivalent; JSON schema validation; SQLite for metadata/relationships plus filesystem media for source assets.
- **Frontend:** lightweight React + TypeScript/Vite SPA served by local service, or reuse an existing app stack if source is recovered. Package as a Windows desktop shell *later* if worthwhile; do not spend the first sprint on packaging.
- **Timeline:** internal frame-based EDL manifest; consider OpenTimelineIO for interchange once cuts are stable. OTIO models editing decisions but does not render media.
- **Rendering:** FFmpeg with controlled version, subprocess args (no unsanitized shell), scratch workspace, logs and progress.
- **Tests:** Python unit/integration tests + fixture media; deterministic scheduling tests must run without GPU or live ComfyUI.

The architecture matters more than any one stack. If an actual repository exists, prefer compatible existing infrastructure and document deviations.

## 3. Data hierarchy and safe storage

```text
Workspace
  World(s)
    ├── World Bible (geography, recurring places/characters, relationships)
    ├── Canon revisions + chronological events
    ├── Locations (relative positions, neighborhood, shared references)
    ├── Scenes (one canonical source still per camera/scene setup)
    │    ├── immutable MASTER image + checksums
    │    ├── entity/object/ambience regions and visual anchors
    │    ├── behavior definitions
    │    └── candidate / approved clips + workflow provenance
    └── Episodes
         ├── world revision, in-world time, continuity cues
         ├── scheduler seed + editorial manifest + provenance
         ├── audio playlist / ambient beds
         ├── proposed canon changes
         └── review state / final export(s)
```

**Minimum durable records** (naming can evolve; preserve the semantics):

| Record | Must contain |
| --- | --- |
| `world` | Stable ID, title, optional geographic topology, canon revision, optional audio/radio lore |
| `location` | World ID, unique ID, stable spatial relationships, references and appearances |
| `entity` | Stable ID, human/animal/object, identity refs, location affiliations, relationships |
| `scene` | World/location IDs, immutable master asset hash, composition/camera restrictions, user-marked clickable regions |
| `behavior` | Actor/region ID, state preconditions, state result, semantic action, weight, cooldown, timing limits, rarity and conflict locks |
| `variant` | Behavior ID, video asset, FPS/duration, start/end anchor/state, review status, metadata, generation provenance |
| `episode` | World ID + **specific canon revision**, scene IDs, in-world time, selected cues, seed, duration, editorial status |
| `timeline_event` | Frame start/end, lane, asset/variation IDs, actor/resource locks, before/after state, selection explanation |
| `canon_patch` | Proposed fact/relationship/event changes, dependencies, effective in-world date, approval and commit status |

Use **immutable asset IDs**, content hashes (e.g., SHA-256) and append-only revision history for reviewed masters and committed episodes. World facts refer to IDs, not labels like “the cat” or “store.” In general, store structured records in the database and media as files relative to a workspace root; avoid absolute paths to one of the user's machines in portable projects. Allow Windows drive locations chosen by the user; do not assume OneDrive.

### Example behavior definition (illustrative contract; adapt schema after tests)

```json
{
  "id": "behavior.reader.sip_tea",
  "scene_id": "scene.summer_rain.street_window",
  "actor_id": "entity.reader",
  "label": "Sip tea",
  "eligible_from": { "pose": "seated_reading", "cup": "on_table" },
  "result_state": { "pose": "seated_reading", "cup": "on_table" },
  "min_gap_seconds": 480,
  "cooldown_seconds": 900,
  "weight": 1.0,
  "time_windows": ["evening"],
  "requires_resource_locks": ["actor.reader", "prop.cup", "frame.full_scene"],
  "variants": [
    {"clip_id": "clip.tea.01", "weight": 2.0, "status": "approved"},
    {"clip_id": "clip.tea.02", "weight": 1.0, "status": "approved"}
  ]
}
```

The **schema must distinguish** semantic actor/prop state from **visual anchor compatibility** (e.g., exact same seated pose/cup position/lens/crop). Both are needed for truly invisible edits. A semantically compatible clip may still jump visually; require a user review and/or conservative frame continuity check. Make no unsupported claim that model output will loop perfectly.

### Clip lifecycle and provenance
`requested → queued → generating → candidate → reviewed_approved | reviewed_rejected → archived/reusable`.

For each candidate, keep `scene/master hash`, workflow JSON snapshot/hash, Comfy `prompt_id`, model/node information if available, prompts/negative prompts, seed, conditioning still(s), generation parameters, output checksum, reviewer notes, start/end previews and media properties. When replacing a clip, never change the identity of an already approved file; create a new revision. Projects may carry raw user-owned source stills and licensed music separately.

## 4. Creator workflow

### A. Import & lock the image
- Import existing image at original resolution; copy as immutable master and record hash. A scene always knows exactly which master belongs to it.
- Let creator add manual boxes/polygons and names for actors/objects/ambient regions. Auto detection/segmentation can be added later.
- Define camera/palette/object placement constraints as readable metadata and display a comparison overlay during review.
- If multiple camera angles are desired, each uses a **separate canonical scene** connected to the same location; do not let a model mutate the shot unpredictably.

### B. Define states and actions visually
- Click an entity region; edit **states** (reading/sitting, standing at window, cat curled up, cat walking), **idle pools**, **action pools**, **variant weights**, **cooldowns**, **gaps**, **schedule windows**, **interaction dependencies** and **allowed transitions**.
- Distinguish `idle` (small, return-to-anchor activity), `action` (may change state), `transition/recovery` (returns to a safe anchor), `ambient` (regional/masked or audio-only) and `world cue` (a recurring background event).
- Creator need not draw a complex node graph to begin. An actor-centric list, state dropdown and rule chips are enough for MVP, with an optional graph view later.
- Add a **Preview behavior** control (plays variants and displays the entry/exit contract) and **Simulate 10 minutes** (runs scheduler without video rendering, shows events/reasons).

### C. Generate candidate clips using ComfyUI
- Start with the creator's **working local H3 workflow** exported to **API-format JSON**. Show a binding UI mapping canonical image, optional end frame, prompt, seed, length/resolution, and actual output node. Node IDs must come from the imported workflow, not hard-coded assumptions.
- Adapter introspects reachable ComfyUI, checks required node types and reports missing types or unverified model files. Model capability must be empirically measured (VRAM, run time, frame consistency), never inferred from the user's GPU name alone.
- Candidate clips become reusable resources only after review. Allow batch variants and controlled randomized seeds if that capability is available in the workflow.
- Creator may approve/reject in a gallery; store why (identity drift, geometry changes, bad hands, bad return pose, abrupt audio, etc.).

### D. Assemble episode, without an AI director
- Set world, location(s), in-world timestamp, mood, duration (e.g., 60/90 minutes), seed, music/ambient inputs and authored continuity cues.
- Ask the deterministic director to produce an **editable plan** from approved pools. User may lock or replace events; save any manual edits as a new manifest revision.
- Produce editorial timeline/preview using static holds + approved clips + approved transitions + safe effects; audio remains continuous and intentional.
- Export MP4 and human-readable event/canon report. Full reproducibility requires freezing both the episode manifest and all referenced assets; reseeding produces a new variation but not new canon.

## 5. Deterministic scene and episode director

### Scheduling rules (implement as testable plain code)
1. Initialize from **pinned canon revision**, scene/environment state, actors/props, user duration, seed and approved clip manifests.
2. Create separate logical tracks for actors, animals, background events, weather and audio. The tracks compete for shared visual resources and have explicit **resource locks**.
3. Determine next eligible behaviors by time window, preconditions, minimum gaps, cooldowns, recency, rarity, actor presence and required resources.
4. Select among eligible behaviors and **approved variants** using seeded weighted random selection. Discourage repeats both within one episode and, optionally, across episodes by storing recent history.
5. Validate entry visual anchor / state and end state. Insert a reviewed recovery clip or safe hold when needed. If there is no compatible action, do not force a bad cut; use a still/ambient hold and log the fallback.
6. Add the chosen event to a frame-accurate event log; update state and lock/availability times. Continue until requested duration is filled exactly.
7. Validate manifest invariants; then hand off to assembly. No LLM decisions, no model calls in this scheduling loop.
8. Store seed, scheduler version, clock/frame rate, manifest hash, clip hashes and world revision. Same inputs must result in the **same event order and frame boundaries**.

**Important:** different logical actor tracks can simulate independent lives, but MVP assumes AI-generated **full-frame clips occupy an exclusive video resource**. Rain overlays and masks are allowed only after user review; separate character clips cannot overlap until clean isolation, background reconstruction, occlusion and blending are demonstrated. This avoids the trap of two incompatible videos both painting the whole room.

### Variety strategy
- Many idles and meaningful actions; 2–5 variants per behavior for tests, not a hardcoded cap.
- Anti-repeat windows, category quotas, soft “quiet periods,” time-of-day routines, short/long idles, rare appearances and configurable event density.
- Long quiet holds are a **feature**, not a bug; use credible noise/ambience and subtle changes between events, never rapid arbitrary motion simply to meet an activity quota.
- Different episode seeds, weather/audio beds, authored world cues and stateful histories vary the experience while preserving visual identity.
- Optionally give episodes authored "personalities" (gentle/stormy/busy/late-night) as deterministic parameter presets.

### Example timeline (illustrative, NOT fixed pacing)

| In-episode time | Picture / action | State + continuity note |
| --- | --- | --- |
| 00:00–05:30 | Canonical still + safe rain/reflection bed | Reader seated, cat resting |
| 05:30 | One of several reader idle clips | Starts/ends seated anchor |
| 11:45 | Cat stretches | Only if reviewed cat motion preserves master |
| 18:20 | Tea sip variation #2 | Cup present; actor/state/visual anchor match |
| 27:00 | Bus route 271 visible beyond window | Authored world cue; must match location/time |
| Later | More quiet holds, rare events, music changes | Spaced across requested runtime |

Do **not** hardcode these events, frequencies, names or timestamps.

## 6. The shared-world engine: what makes the series special

**Two levels of continuity:**
- **Scene continuity**: no teleporting, duplicate cups, changing furniture, strange camera moves, identity/pose shifts or jump cuts.
- **Universe continuity**: the cat is the same entity across locations, the store is on the same street, the bus uses the same route, the character's whereabouts/time make sense, world events advance in a consistent order.

### World Registry responsibilities
- Give every world, neighborhood, location, entity, route, prop, recurring sound and authored event a stable ID.
- Record location adjacency and sightlines explicitly (not necessarily a literal GIS map). E.g., an apartment overlooks the store/intersection; both scenes can reference the same crossroad.
- Record entity identity sheets, visual refs, relationships, schedule hints and location membership. Do not generate a new version of a character without creator permission.
- Record in-world chronological `events`, `facts`, `fact_valid_from` or `fact_valid_until` and references to prior canon revisions.
- Provide a **continuity checker**: impossible co-presence, conflicting visual identity, missing prerequisites, an event occurring before its cause, crossing established route geometry, contradictory seasons, stale world revision.
- Show **where a fact appeared before** (episode IDs and timestamps) so the creator can build deliberate echoes and reveals.

### World Director behavior
- Given a canon revision and creator-authored episode intention, choose eligible recurring cues/appearances and scene references. Examples: bus in background, same station heard faintly, cat present in later scene, changed storefront sign after a previous authored event.
- The director **proposes** an episode-specific state and optional `canon_patch` (new fact, changed relationship, moved prop, passed season). Proposed patches require **approval to commit**. Draft generation, failed exports and alternative takes must not modify published world history.
- When scheduling recurring details, enforce identity/time/geography first, variety second. A cameo is meaningful because it is consistent, not because every episode forces one.

### World-canon example

```text
World W1 (creator-owned; world facts provisional)
  Location L1 = intersection storefront
  Location L2 = upstairs apartment, overlooks L1
  Route R271 = passes L1 in certain periods
  Radio S1 = "UMBRA FM 88.3"
  Entity C1 = neighborhood cat

Episode E01 (world rev 4, evening, rainy): see R271 from L1; hear S1
Episode E02 (world rev 4, later same evening): from L2 hear S1;
                   reference the same rain and intersection
Episode E03 (world rev 5, another morning): C1 at L2; rain has ended

E03 can only rely on a changed world fact after that change has been
proposed, reviewed and committed to produce rev 5.
```

**Do not mistake this example for confirmed narrative canon.** The **shared registry + factual references between episodes** are the confirmed product requirement.

### Storytelling design principle
Make repeat-viewer discoveries optional: a familiar cat, station ident, traffic, a shop sign, band poster, poster weathering or an offscreen neighbor. Episodes are cozy, entertaining and meaningful as standalone experiences. Small evolution over time should reward attention without requiring viewers to learn lore.

## 7. ComfyUI LAN worker contract

### Connection and discovery
- Remember the last successful host:port or base URL and check it on startup. Provide an **editable manual endpoint** as a guaranteed fallback.
- Where available, use mDNS/zeroconf for explicitly advertised instances. Otherwise optionally offer an **opt-in, limited-range LAN probe** with clear scope and timeouts. Do not claim stock ComfyUI universally advertises a discoverable service, and do not indiscriminately scan a network.
- For a remote Comfy server, its configured listener/firewall must permit LAN clients; do not silently alter security settings. Default to private LAN/VPN, not exposing an unauthenticated generator to the public Internet.
- Show connection status, server device stats if provided, available nodes, selected workflow validity, queue depth, recent errors, reconnect state.

### Self-hosted ComfyUI API (subject to instance/version/extension validation)
- `GET /system_stats`: server/GPU information where available.
- `GET /object_info`: installed node classes and input declarations; **does not necessarily prove that model weights are installed or functional**.
- `POST /upload/image`: stage the canonical/conditioning image, when needed by the imported workflow.
- `POST /prompt`: submit **API-format workflow graph**; track the returned `prompt_id` (and validation errors).
- `GET /history/{prompt_id}`: read completion and recorded output metadata.
- `GET /view`: retrieve supported output files when returned output references are compatible; if the workflow uses a video/custom output convention, implement an adapter for its actual result structure.
- `WS /ws` (client ID where supported): real-time queue/progress/error; polling `/history` and `/queue` as a fallback.

Do not cancel other people's Comfy jobs or clear shared queues as a side effect. Implement **job ownership**, retries/backoff, timeout reporting and cancel scoped to owned work where safe. Do not assume `/interrupt` is safe on a shared server. Save all submitted workflow snapshots and imported outputs locally so other machines or restarted sessions do not break asset links.

**Official docs:** https://docs.comfy.org/development/comfyui-server/comms_routes and https://docs.comfy.org/development/comfyui-server/comms_messages . Confirm capabilities against the creator's running version.

### H3 and future models
- H3 is **locally runnable in the user's ComfyUI setup according to the user**; test the specific actual workflow and custom node versions, rather than arguing from generic model requirements.
- Store “workflow adapters” as mappings: supported capabilities (single image / first-last frame / reference video / mask), node binding names, required assets, accepted sizes/durations, output parser and constraints.
- Benchmark representative clips with user permission; log time, peak VRAM if available, frames, quality notes, endpoint reliability. Keep alternatives like Wan/LTX as optional experiments behind the same interface.
- No automatic GPU benchmark, mass job submission or model downloads on first launch.

## 8. Media assembly / delivery

### Video
- Convert all approved inputs to consistent chosen frame rate, resolution and color handling while preserving originals. Choose delivery settings with the creator; any defaults are provisional.
- MVP: freeze frame or safe static hold between approved full-frame clips; make cuts only at reviewed matching anchors. Add **simple environmental overlays** only when compositing has been tested with masks/alpha and background preservation.
- Assemble using FFmpeg or a proven media pipeline; keep an internal frame-accurate manifest independent of encoding.
- Verify exported duration within one frame/timing tolerance, playable streams, no black gaps, no missing assets and consistent aspect ratio. Sample boundary frames for visual jumps.
- Export both playable video and machine-readable/human-readable event manifest. Optional OTIO interchange can follow; OTIO is not itself a renderer (https://opentimelineio.readthedocs.io/en/latest/index.html).

### Sound, station and music
- Support user-provided music playlists, room tone, ambient loops (rain, HVAC, traffic), short event effects and optional radio interstitials.
- Keep radio station/music identity in world data: a fictional station can recur across episodes while songs/ambiences vary.
- Crossfade audio beds cleanly, avoid harsh loop joins, allow simple gain and ducking settings, preserve cue timestamps and attribution/licensing metadata.
- Do not assume licensed commercial music is cleared for uploads or redistribution.

### Project portability
- Relative asset paths or an explicit remapping mechanism; checksum checks on reopen; portable project export/import with clear missing-asset diagnostics.
- Keep candidate caches cleanly separated from approved masters and exports. Do not delete source media by default.
- Make resumable jobs after LAN disconnection and export failures; no hidden state only in UI memory.

## 9. User interface — progressive disclosure

**Suggested primary views:**
1. **Worlds:** world bible, map/adjacency, canon timeline, episodes and relationships (a simple list is enough for MVP).
2. **Scene:** canonical image canvas; click manually marked person/cat/prop/environment region; visual identity references and anchors.
3. **Behavior:** inspector for states, multiple idle/action variants, rarity/weights/cooldowns and preview; expose invalid entry/exit transitions clearly.
4. **Motion Library:** Comfy workflow selector, variant batch queue, review/reject gallery, provenance, start/end frame compare.
5. **Episode:** duration, seed, time, world revision, event density, soundtrack, continuity cues; simulate/inspect timeline and export.
6. **Workers/Jobs:** Comfy connection/status, in-flight jobs, error details and reconnect.

**UI usability:** default to comprehensible labels, not arcane graph jargon. Examples: “Reading quietly,” “Sip tea,” “Return to seated pose,” “Don't repeat within 12 minutes.” Show user-defined variants side by side, allow weights and a preview. Keep a powerful advanced mode available, but a first scene should be possible without configuring dozens of fields.

## 10. Engineering quality gates and tests

### Tests requiring no AI/GPU
- Identical world revision + seed + assets + settings => identical manifest/event log hash.
- Same actor cannot simultaneously sit and walk; full-frame clips cannot overlap until declared mask-based compositor is enabled.
- A clip requiring `cup_on_table` never runs if the cup is gone; a seated idle never starts while standing.
- Cooldown and gap limits respected; different variants selected over long runs when eligible; no approval-bypassing fallback.
- If no eligible clip exists, a legal hold fills the gap and warning explains why.
- Changing a world fact creates a proposed patch; a draft/rejected episode cannot mutate published canon.
- Referenced entities and locations match stable world IDs; cross-episode event ordering checked.
- Recover project from interrupted process with intact master hash and no missing metadata.
- Mock API covers Comfy offline, invalid workflow, missing nodes, timeout, queued, success, malformed metadata, reconnect.

### Tests using actual H3/Comfy (once workflow provided)
- Confirm server reachable from the machine running Last Light Radio. Confirm installed nodes/required models, upload image, submit 1 single-image idle, track progress, and download usable result.
- Record actual VRAM/time and output codec/FPS. Validate a candidate starts/ends at a visually useful anchor.
- Produce at least 3 distinct idle variants and 2 tea-sip variants (or equivalent creator-chosen actions); mark review decisions and prove only approved results reach timeline.
- Produce a watchable 10-minute pilot with stable camera/style and no obvious continuity discontinuities at event boundaries.

### World continuity demonstration
- Create two scene masters attached to two locations in the **same world**; shared recurring reference appears in both using identical world ID.
- Simulate two linked but independently enjoyable episodes; show canon revision and timeline facts each used; commit a fact in episode 1 and validate its permitted effect in episode 2.
- Show that rejecting the later episode changes no earlier lore or assets.

## 11. Build phases and checkpoints

| Phase | Deliverable | Exit test |
| --- | --- | --- |
| M0 Inventory & foundations | existing project discovery, truth reconciliation, fixtures, skeleton | tests run offline; no source destroyed |
| M1 Data model + scheduler core | immutable masters, state contracts, deterministic manifests | same inputs produce same schedule; guardrails enforced |
| M2 LAN Comfy bridge | live connection and imported H3 workflow adapter | user-approved one job queued, downloaded and audited |
| M3 Motion library + review | variant pools and gallery, approve/reject | only approved variants eligible; provenance intact |
| M4 Video/audio proof | static holds, approved actions, continuous sound, FFmpeg | playable ~10 min with manifest; duration verified |
| M5 World bible + links | stable world IDs, references, canon revisions & patches | 2 episodes share place/character reference consistently |
| M6 Visual behavior editor | selectable scene regions and friendly rule controls | user authors actor behavior without editing JSON |
| M7 Long-form reliability | configurable 60–90 min, resuming, portability, QA | full-length export without broken transitions or canon drift |

See `MVP_TASKLIST.md` for actionable tasks. This order is a **recommended dependency order**, not a claim the code already exists.

## 12. Risks, decisions and recovery notes

| Risk / unknown | Response |
| --- | --- |
| H3 model naming, nodes and performance not inspected | import user's actual Comfy **API-format workflow**; benchmark 1 clip; no assumptions about cloud or VRAM |
| Generative output drifts from master | explicit approval, frame comparisons, immutable master, rejection + safe holds |
| Full-frame actor clips overwrite other actors | exclusive scene-resource lock in MVP; only enable multi-region compositing after proof |
| State-compatible cut still looks wrong | additionally review start/end **visual** anchors; recovery clips or safe cut only |
| Excessively repetitive 90-min results | variation pools + sparse events + cooldowns + atmosphere, schedule metrics/review |
| Automatic server discovery not supported | remembered endpoint and manual connection; only opt-in scans/announcements |
| World contradicts itself over multiple episodes | stable IDs, pinned revisions, chronology validator, approve proposed patches |
| Hardware too slow for many AI clips | small test set, cache/reuse assets, static holds, queue/progress budget |
| Lost assets or code | no destructive writes, repo inventory and backups, portable workspace and hashes |
| Overbuilt editor before proven pipeline | 10-minute vertical slice first, then add friendly visual UI |

### Creator inputs that are useful *when needed*, not blockers for offline work
- The currently working **H3 ComfyUI API-exported workflow JSON**, and the workflow's input/output conventions (after offline architecture exists).
- One canonical image for the first pilot (the street-level intersection reference remains a plausible creative start, not a requirement).
- One sample audio bed or music track with rights cleared for testing.
- First choice of output dimensions/FPS, export folder and application packaging preference (can use temporary dev defaults until asked).

## 13. First session for Codex (do this, not everything)

1. Read `AGENTS.md`, `PROJECT_TRUTHS.md`, this file and `MVP_TASKLIST.md`.
2. Inspect the provided working directory/repository before altering it. If nothing exists, initialize a minimal Windows-friendly local project with documented run/test commands.
3. Implement domain entities: worlds, locations, canonical scenes, actor states, behavior definitions, approved variants, episode configs, manifest events and proposed canon patches; validate with static fixtures.
4. Build a **headless deterministic scheduler** with seed, resource locks, cooldowns and fallback hold. Test under mock media with no ComfyUI/GPU.
5. Define a **mockable Comfy adapter contract** and a simple connectivity probe. Do not bind H3 node IDs until user shares their working workflow.
6. Produce a concise status report, with what truly works and the next 3 tasks. Record verified new facts in `PROJECT_TRUTHS.md`.

**Definition of a safe handoff:** a developer can start from these files alone, without needing hidden conversation context, and without mistaking imaginative episode examples for canon or design hypotheses for installed software.
