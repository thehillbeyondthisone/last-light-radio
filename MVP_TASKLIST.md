# Last Light Radio — MVP_TASKLIST.md

**Updated:** 2026-10-31
**How to use:** check only after acceptance conditions pass. `P0` = blocking, `P1` = next, `P2` = later. This is the reconstruction/build plan, not a claim these features exist.

**Windows quickstart checkpoint — 2026-10-21:** `quickstart.bat` checks/setup local media tools, builds stale UI, opens the existing studio after readiness and reuses it on relaunch. Logs and failures are visible; startup makes no new GPU requests. One explicit browser test through the saved technical cat recipe completed 39 frames, passed full MP4 decode, browser playback and all lossless protected-pixel audits, and remains unapproved. Existing eight approvals were preserved. Full suite: 138 tests (137 passed, one Windows symlink skip); TypeScript/Vite and 43-file Python checks passed. This verifies launch and the existing scene pipeline; audio, general behavior/world authoring and long-form acceptance remain incomplete. Evidence: `artifacts/quickstart-20261021/`.

## M0 — Locate and safeguard existing work [P0]

**Source-control checkpoint — 2026-11-19:** initialized Git against the existing GitHub `main` history and prepared the recovered application for source distribution. Local libraries, environments, worker settings and generated media stay excluded; the gap-test historical source baseline is retained. Verification: 95-file Python baseline and TypeScript check passed; 42 focused offline tests passed with one Windows symlink skip; the seed-7 ten-minute mock demo completed without network requests. No feature milestone or creator acceptance changed.

Clean-archive reproduction also passed after disabling Git newline conversion for checksum fidelity. Four Clip Editor integration tests passed with local loopback access.

- [x] Inspect user-designated project directory, Git status, available assets and current README; **do not assume a directory or repo exists**.
- [x] Preserve existing source/media/workflows; inventory and document any recovered partial implementation before building replacements.
- [x] Create a minimal reproducible local run/test script (Windows friendly); record versions and project path without hardcoding machine-specific paths into portable project files.
- [x] Set up tests, lint/format checks, structured logs, sample fixtures and a `README` showing development commands. Baseline checks cover syntax and whitespace; no external formatter is installed.
- [x] Reconcile any differences with `PROJECT_TRUTHS.md`; list unresolved decisions, do not silently rewrite scope.

**Acceptance:** code and tests (or clean skeleton) can be opened on a fresh environment, existing assets untouched, source-of-truth known.

## M1 — Offline domain model and deterministic engine [P0]
- [x] Persist world/location/entity IDs, scene/master checksum, actor/prop states, behavior definitions, clip/variant review status, episode and manifest records.
- [x] Validate that `MASTER` is copied immutably; separate candidates, approvals, exports and backups.
- [x] Implement eligibility: from-state, prop preconditions, time windows, actor presence, cooldowns, minimum gaps, weighted variant selection and anti-repeat.
- [x] Implement resource locks for actor/prop and exclusive full-frame AI shot usage. First slice conservatively serializes all picture events; no layered compositor.
- [x] Implement state updates after actions, transitions/recovery clips and legal static-hold fallback.
- [x] Generate frame-accurate manifest/event log from pinned inputs and seed, without ComfyUI or any AI/LLM service.
- [x] Save explicit reason codes for skipped/ineligible behaviors and fallback holds.
- [x] Tests: same seed = same timeline, different seeds change distribution, no invalid overlapping/contradictory actions, only approved clips chosen, exact requested frame length.

**Acceptance:** one-command offline simulation of a 10-minute episode with at least 3 idle variants + 2 action variants, test-verified deterministic event log.

## M2 — LAN ComfyUI bridge and local H3 proof [P0]
- [x] Implement saved URL and connection test, reconnect/timeouts; manual endpoint fallback. Connection probes can be retried; durable live prompt IDs support polling/download resume without a new submission.
- [ ] Add optional discovery only where practical (advertised mDNS and/or explicitly opt-in bounded LAN probes), with safe network behavior.
- [x] Query Comfy `/system_stats` and `/object_info`; show reported device/installed node classes without promising model readiness.
- [x] Accept API-format Comfy workflow JSON; inspect nodes and bind image/prompts/seed/output via explicit, user-confirmed mapping.
- [x] Implement `POST /upload/image`, `POST /prompt`, job ownership/progress via `/ws` or polling, output retrieval via `/history/{prompt_id}` and verified output conventions. This slice uses read-only history/queue polling, not WebSockets.
- [x] Mock offline/invalid/queued/success/failure/reconnect cases with tests. Preserve workflow snapshots and output provenance.
- [x] **With user's exported local H3 workflow:** submit one tiny single-image idle test and capture actual duration, FPS/codec, runtime, reported memory and quality notes. Used the identical graph recovered from successful history; 39 decoded frames, 384 x 480, 1.599 s, 35.925 s execution. Device snapshots retained; no peak VRAM claim.
- [x] Never clear shared Comfy queue or interrupt someone else's job.

**Acceptance:** one creator-authorized real H3 candidate generated through the LAN, saved locally with original master unchanged, or an honest documented blocker if the workflow isn't yet supplied.

**2026-10-21 checkpoint:** M0 and the offline M1 acceptance pass. Core M2 acceptance now passes with creator-authorized live test `0d42247f7f6b4e6da6ed5b034bb35b04`; output, ownership, exact prepared workflow, raw history, checksums and review artifacts are saved under `runs/h3-test/`. A Windows-native output subfolder was normalized safely and the same completed job downloaded on retry without resubmission. Optional discovery remains deferred. The generated picture and candidate remain noncanonical; visual quality/clip approval are M3 work. See `workflows/h3/LIVE_TEST.md` for the measured test and review limits.

## M3 — Motion library, variants and clip review [P0]

**Passing-car trial — 2026-10-26:** one isolated H3 candidate completed
124 frames / 24fps. All raw/lossless/saved-sample containment checks and full/
detail decoding/timestamps pass. A dark vehicle approaches with wet-road
reflections; original light bands are too bright and late foreground support/
occlusion needs visual revision. Trial approval and placement remain unchecked.
An additional CPU brightness comparison preserves the body/dark-channel deltas
and all protected pixels across 124 frames; three movies pass full decode and
timestamps. Lamp balance remains uneven in one passage and the late exit still
needs refinement; neither appearance is production-approved.
No live car subject/job/candidate was added. Existing media/reviews/sequences
and application/workflow files were preserved, allowing only the independently
authorized radio derivative. Evidence: `artifacts/passing-car-20261026/`.

**Approved radio cue scope — 2026-10-26:** creator approved only the synchronized
display cue after viewing the comparison. Separate CPU take
`709d4298e10a5a72ff5f827de9806230` carries light timing inside the corrected
adjustment (frames 34–68), preserving sync when moved as a whole. All 124
lossless frames match the reviewed proposal; pixels outside display support
and 91 out-of-cue frames are unchanged. Four movies pass full decode/timestamps.
Take approval and placement remain pending. No editor implementation, overlap
rule, saved sequence, existing review or GPU job changed. Generic mask correction
is disabled for this derivative; source/transform provenance is retained.
Evidence: `artifacts/radio-sync-proposal-20261026/`.

**Cat stretch correction — 2026-10-26:** creator likes the first three cat previews but reports clipped tail/paws in the fourth. Saved PNGs confirm complete source anatomy. Playback caught an early leftward tail sweep beyond the first correction; final pending v2 includes the complete arc, protects the reader in front and preserves proportions in a wider detail view, reusing all 124 PNG references. All lossless containment/saved-sample, old/new added-area and full/detail/comparison frame/timestamp checks passed. Preserved 43 prior media/master files, 39 reviews, four masters and two sequences; two CPU candidates and zero GPU jobs added. First attempt retained; no editor changes or production placement. Evidence and an eight-event first-pass proposal: `artifacts/cat-stretch-correction-20261026/`. Audio/mixing and final creator review remain outstanding.

**Cat variation trials — 2026-10-26:** four new pending cat actions (yawn, listen/head lift, paw grooming and lying stretch) completed at 124 frames / 24fps each. All 496 source PNGs/lossless composites, saved-sample replay, full/detail media and the 172-frame comparison passed containment/decode/timestamp checks; browser playback advanced. Distinct intended actions appear in passage samples; stretch tail lift, anatomy/contact and exact joins remain creator review. Preserved 39 prior master/output files, 35 reviews, four masters and two saved sequences; added four jobs/candidates without editor changes, approval or timeline placement. Reproduction: `artifacts/cat-variations-20261026/`. Approved-library acceptance remains incomplete.

**Radio headroom correction — 2026-10-25:** saved unmasked PNGs confirm the creator-reported head clipping is the diagonal mask edge. One pending CPU correction reuses all 124 frames; the complete lossless replay preserves pixels outside added head support and passes containment plus full/detail/paired frame/timestamp checks. No new GPU job, approval or saved sequence; 38 prior media/master files, 34 review records, four masters and two saved sequences were preserved. Current editor subject creation was confirmed through a new name in Create action / Who moves? and one passing isolated regression. Usage and deferred editor notes updated; no editor implementation changed. Evidence: `artifacts/radio-headroom-20261025/`.

**Radio/compositing exploration — 2026-10-24:** a new unapproved 124-frame radio-adjustment take, a 124-frame CPU-only customer mask correction and a 384-frame soft-window effect passed lossless containment plus full original/detail timing checks. Saved unmasked frames confirm the old diagonal customer cutoff came from the mask. Radio contact/joins, corrected playback and light softness remain creator review. Earlier masters/media/reviews/saved sequences and eight approvals were preserved; one GPU job and two candidates were added, with no editor implementation change. Evidence: `artifacts/radio-compositing-20261024/`.

**One-way departure/light-on checkpoint — 2026-10-24:** one unapproved 124-frame H3 shop departure follows a rightward route toward the receding street instead of returning inside; final occlusion/shrink needs review. A separate 576-frame continuous-tone effect lights two originally dark windows and holds their state. Full lossless containment and original/detail frame/timestamp checks passed. A deterministic, release-ineligible ten-minute proposal has eight events spaced 45–120 seconds apart including lead/tail. Existing masters/media/reviews/saved sequences and eight approvals were preserved; no editor changes or production placement occurred. Evidence: `artifacts/departure-lighting-20261024/`.

**Street-activity exploration — 2026-10-24:** creator feedback set aside the unmotivated plant swing/fixed-basket occlusion. A 720-frame apartment-light state demo and three 124-frame H3 shop trials (arrival, undersized step-out, adult-scale retry) passed all lossless protected-pixel and full original/detail frame/timestamp checks. Entry and adult-scale exit/pause/return are visible in passage samples; all candidates remain unapproved. Four masters, 28 prior review records, eight approvals and two saved sequence summaries were preserved. Evidence: `artifacts/street-activity-20261023/`; editor depth/state/scale changes stay deferred in `docs/EDITOR_LEARNING_NOTES.md`.

**Scene-object exploration — 2026-10-23:** three new unapproved Apartment Pilot ambient/object H3 takes completed (plant, candle/light, radio), each 90 frames at 24fps. All 270 lossless composites, full media decoding and frame/timestamp checks passed. A separate 144-frame brightness-only CPU comparison preserves the artwork and has exact canonical lossless endpoints. Candle shape and radio strength need review/revision; approved-variant acceptance is unchanged. Existing masters/media/reviews/sequences were preserved. Evidence: `artifacts/scene-animations-20261023/`.

- [x] Compare compatible source takes/revisions in the native Viewer with shared playback, exact decoded frame inspection, explicit loop/exit-hold/pose-plate boundaries and advisory seam measurements; retain manual approval and production eligibility checks. See `docs/TAKE_COMPARISON.md`.

**Digest-trial checkpoint — 2026-10-23:** native comparison passed isolated unequal-duration and real-media browser checks. Separate OFF→ON→OFF H3 button candidates and an ordinary-code playback demo passed full decoding and all 78 lossless protected-pixel checks; their joins remain unapproved and persistent-state editor integration remains pending. 201 tests ran (200 passed, one Windows symlink skip), TypeScript/Vite and 58-file Python checks passed. Four production masters, 25 candidates, eight approvals and sixteen jobs were preserved. Evidence: `artifacts/digest-trials-20261023/`.

**Sip / focused-workflow checkpoint — 2026-10-21:** a 5.167-second mug-sip candidate and a corrected-mask derivative are available for creator review. One H3 job supplied both; the derivative reuses saved PNGs and remains independently unapproved. Source media, four masters and eight existing approvals are preserved. Scene → motion → focused review now uses a large preview, one take request and collapsed settings; the Episode editor and authoring wizard remain follow-up UX work. 140 offline tests ran (139 passed, one Windows permission skip); build, 46-file Python check, full MP4 decode and all 124 protected-pixel replays passed. Sip approval, episode integration/steam behavior and production join acceptance remain unchecked. Evidence: `artifacts/sip-20261021/README.md`.
- [x] Register candidate clips with scene/master/workflow/version, semantic and visual entry/exit states, timecode/FPS and media checksum. Restored production candidates pin recovered start/end states; review anchors remain explicit and editable. General behavior/state authoring remains a separate task.
- [ ] Support multiple variants for every idle/action/transition and independent weights, approvals, cooldowns and activity density.
- [x] Provide preview/review with head/tail frames, master overlay or side-by-side compare, accept/reject notes. React studio includes playback, master comparison, three frame samples, notes and review history.
- [x] Make approval an explicit action; no unreviewed candidate is eligible for release timeline. Studio approval requires visual acknowledgement and named anchors; latest status gates its verified approved library. Scheduler fixtures independently enforce approval eligibility; a studio-to-episode bridge remains pending.
- [ ] Cache/reuse approved actions between episodes when allowed by state and canon; no destructive edits when replacing a variant.
- [ ] Test: visually reviewed version remains immutable; rejected variants never scheduled; incompatible anchors trigger diagnostic + hold/recovery.

**Acceptance:** 3 approved idle clips + 2 approved action variants available for a single scene, traceable back to the Comfy request.

**2026-10-21 studio checkpoint:** creator-requested scene import, live H3 generation and candidate review UI are implemented and browser-verified. Candidate provenance includes master/workflow hashes, parameters, timing and media checksums; review stores visual anchors, but the full semantic-state/behavior authoring contract is not yet exposed. The separate working store imported eight historical approved MP4s without modifying the old library. A new noncanonical UI verification take was approved/rejected for persistence testing and left rejected. Historical approvals do not complete the new pilot's visual-quality acceptance. Tests and detailed evidence: `docs/STUDIO_VERIFICATION.md`.

**Recovered production process:** inspection of the eight completed legacy clips identified the earlier 768-square actor-crop, separate first/last-pose, turbo 8-step H3 and masked-composite pipeline. Exact endpoint crop preparation was verified against all source plates. The restoration checkpoint below implements this path alongside the preserved smoke-test workflow. Exact color-correction/endpoint-blend source code remains unrecovered; see the dated implementation notes in `PROJECT_TRUTHS.md`.

**Restoration checkpoint:** the app now offers the eight recovered action presets with actor crops, masks and start/end poses, saves raw PNGs, and assembles full-scene MP4 candidates. Live test `7f374713fdb64319a5fe039bc1017d79` used seed 883101 and the original Reading Idle A inputs/recipe, with a creator-authorized INT8 VAE variant because the old FP16 file is absent. It completed at 124 frames / 24fps / 5.167s, remains unapproved, and opens beside the old approved take with shared playback controls. Reference-based compositing is restored; exact historical color correction remains uncertain. Tests, runtime and source preservation are recorded in `PROJECT_TRUTHS.md`.

**Action/hold checkpoint:** six matched INT8 tests now cover page turn, both cat actions and the complete reading/window/reading cycle. All renders decoded with expected counts; comparison previews include direct joins, supplied-pose holds and actual-frame holds. Protected samples remained exact; the source library and prior approvals were preserved. Small hard-reset differences from generated frames to pose plates remain a continuity consideration. Tests stay unapproved for creator review; this does not complete the approved-variant or production-episode acceptance. Evidence: `artifacts/motion-suite-20261021/review/README.txt`.

## M4 — First complete episode export [P0]
- [x] Optional recovered rain/steam effects continue over clips and holds using an absolute episode clock; validate short-preview timing and protected pixels. These technical checks do not establish creator visual acceptance. Authoring effect regions on other scenes and a full-length ambience export remain pending.
- [x] Apply the creator-approved rain playback fix (2026-10-30). Installed browser playback reached 51.708s across ten reading boundaries with rain advancing and no error. Twelve ambience tests and TypeScript/Vite passed; original media, reviews, settings and other source are preserved. Evidence: `artifacts/rain-applied-texture-v2-20261030/`.
- [ ] Obtain creator visual acceptance of rain in the assembled episode and validate its full ten-minute export; the playback fix does not finish episode appearance.
- [x] Provide a creator-controlled Video texture track: live enable/strength/size/seed, persisted settings, undo/reopen and deterministic finishing in CPU export. Verified the UI save → reopen → 10-second 1080p export with rain/steam at 65%/2px/seed 23, all 240 frames/timestamps and six hold checks. Existing plans retain their appearance. See `artifacts/nested-texture-editor-20261030/`.
- [ ] Choose the final texture settings in the editor and review the finished episode look in the full ten-minute export.
- [ ] Validate a short combined look preview, then export and review all ten minutes with the selected motions, accepted rain/video treatment and continuous audio. Keep the earlier silent technical proof separate.
- [x] Timeline generator creates exact-length holds and approved full-frame clips with compatible pose transitions and visible join diagnostics. Pixel-level join approval remains a creator review.
- [ ] Add continuous test music + ambience beds, crossfades and simple mix levels; retain audio origin/licensing metadata.
- [x] FFmpeg/media worker exports local MP4 at source dimensions / 24fps; never modify masters. Configurable delivery resolution/FPS remains pending.
- [x] Export sidecar `episode_manifest.json` and human-readable `event_log.md` with seed/world revision/clip IDs and timestamps.
- [x] Verify the silent visual pilot plays for exactly 10:00, fully decode all frames/timestamps, and inspect boundary/hold samples. Audio-stream verification awaits the audio track.
- [x] Run at least two timeline seeds to show genuine order/variant changes without breaking state constraints; the seed-7 pilot was actually exported.

**Acceptance:** watchable, connected **10-minute proof** made from one master image and approved actions, with creator-accepted rain, overall video treatment and continuous audio, without any live AI-agent direction. The creator's 2026-10-30 report leaves the final visual acceptance incomplete.

**Rolling-drop checkpoint — 2026-10-21:** v3 adds interspersed larger drops, pinned creep/release curves, speed-dependent stretching, curved refraction and fading trails sampled from actual recent positions. The v2 falling-rain bed and steam phase are preserved; old v1/v2 drafts keep their appearance. A separate 24-second whole-scene and window-detail review passed full frame/timestamp checks. All 12 ambience tests passed, and the full suite ran 132 tests (131 passed, one OS symlink skip); TypeScript/Vite and Python baseline checks passed. No generation or approval changes. Full-length v3 export remains pending. Evidence: artifacts/rolling-drops-20261021/.

The v3 lossless replay also passed all 576 protected-pixel audits (zero changed protected pixels). Browser playback, pause, direct seeking and legacy v2 loading passed without console errors.

**Rain quality checkpoint — 2026-10-21:** v2 adds three depths of tapered, wind-driven rain plus refracting glass beads, slow runners and short trails. Seeded geometry stays continuous over clips/holds and can be evaluated directly when seeking. Existing v1 drafts keep their original renderer; source media and reviews are preserved. Separate 24-second v2 preview passed full decode/timing and all 576 protected-pixel audits. 129 offline tests ran (128 passed, one OS symlink skip); TypeScript/Vite and Python baseline checks passed. Full-length v2 export and general effect-region authoring remain pending. Evidence: artifacts/rain-v2-20261021/; docs/AMBIENCE.md.

**Visual pilot checkpoint — 2026-10-21:** Pilot builder previews and exports the approved Apartment library using deterministic picture-state scheduling and actual-exit-frame holds. Seed 7 / Quiet uses all eight approved clips in 23 motions and 24 holds. The resulting 1920 × 1080 / 24fps MP4 passed full 14,400-frame/timestamp validation and browser playback; 118 sampled boundary/hold frames contained no black frames. Media, workflows and review versions are pinned; changed approvals block export, including during encoding. Originals and all eight approvals were preserved. This completes the silent timing/encoding proof; final visual acceptance, audio/mixing and configurable delivery settings remain incomplete. See the 2026-10-30 correction above, docs/PILOT_BUILDER.md and artifacts/pilot-20261021/.

## M5 — Linked-world continuity [P0 — core product feature]
- [ ] World Bible UI/data: stable IDs, recurring people/pets/props, locations, relative spatial relations, audio/radio details, persistent chronology.
- [ ] Link two scene masters to different locations in **one** world, with shared facts and entity references.
- [ ] Pin each draft episode to a specific canon revision + in-world date/time; note continuity prerequisites.
- [ ] Show previously used recurring world references (bus, cat, station, rain, etc.) across episodes.
- [ ] Add provisional `canon_patch`, chronology validation, explicit approval/commit, and ability to reject a draft without affecting canon.
- [ ] Build a two-episode demonstration with a recognizable same-world detail and one approved persistent change.

**Acceptance:** two standalone episodes with an observable, deliberate connection; approving episode 1 enables a valid later-world change, while a rejected episode cannot alter the world.

## M6 — Visual behavior editor [P1 — essential authoring UX]
- [x] Creator-requested full keyboard workflow with Final Cut Pro 7 defaults and editable bindings (2026-11-01): 62 default keys over 59 commands — J/K/L shuttle (reverse and 2×/4×/8×), K+J/L frame steps, I/O and Mark Clip, In-to-Out/around/loop playback, edit/marker navigation, match frame, F10 overwrite, lift, debounced one-revision nudges, undo/redo/save, zoom/fit/track height, Ctrl+1–4 windows and typed FCP7 timecode. **Keyboard…** (Alt+H) shows a color-coded keyboard; remapping asks before moving a used key, restores defaults and exports/imports JSON. Layout and per-scene markers are browser-local; In/Out/markers never enter saved sequences. Verified in the real editor over an isolated library clone; 215 tests (1 Windows skip), TypeScript/Vite and 62 Python-file checks pass. See `docs/EDITOR.md` → Keyboard; evidence/backups: `artifacts/keyboard-shortcuts-20261031/`.
- [x] Install the creator-requested optional FCP-style layout under **View → All tracks overview**, retaining Standard as the default, and add small **− / +** track-height buttons. Installed-build browser checks verify 17/17 overview rows, an approximately 539 × 303px contained picture at 1440 × 804, independent height/zoom, button limits, restoring Standard, resetting custom heights and all 117 nested Reading segments. TypeScript/Vite, the nested regression and 61 Python-file checks pass. Library fingerprints match; backups/evidence: `artifacts/layout-review-20261031/`. The earlier side-by-side proposal remains rejected.
- [x] Implement the creator-approved nested idle sequences. Main timeline groups each uninterrupted idle/hold span; opening Reading exposes its source cuts and local playback range, with Viewer audition and Episode sequence navigation. Manual actions and original source timing remain intact. Verified with the real saved Reading bed and action-gap regression; see `artifacts/nested-texture-editor-20261030/`.
- [ ] Present all editor changes to the creator for approval before applying
  code/UI changes, timing/effect settings or saved sequence placements.
  First requested synchronization: restrained radio flicker during the reader's
  adjustment, with contact timing and strength previewed together. Existing
  independent-track mask validation must remain effective; overlapping radio
  and reader masks currently prevent simple two-clip placement. See
  `docs/EDITOR_LEARNING_NOTES.md` (2026-10-26); implementation remains pending.
- [ ] After further creator trials, revisit object/ambient motion creation, pending-versus-approved counts, detail audition and light-only/strength controls from `docs/EDITOR_LEARNING_NOTES.md`. Creator explicitly deferred editor implementation during the 2026-10-23 animation batch.
- [x] Add the creator-requested FCP7 sequence workspace: action creation/audition/review/placement, separate named subject Motions above Automatic idles, subject idle pools/pacing/seeds, persistent revisions and silent CPU export. Restrict simultaneous subjects to disjoint validated masks and returning canonical poses; location changes remain deferred. See `docs/EDITOR.md`.

**Subject-editor checkpoint — 2026-10-23:** Browser/Viewer/Canvas/Timeline, source audition, explicit review, action placement/movement, seeded automatic idles, mask correction, fixed-region effects, reopening and CPU export are implemented. Case-only subject spelling shares one track; take numbering matches the Viewer. Tests: 169 ran (168 passed, one Windows symlink skip), TypeScript/Vite and 53 Python-file checks passed. Isolated browser export verified 240 frames/timestamps with rain/steam; a separate 96-frame replay changed zero protected pixels. Four live masters, 25 candidates, eight approvals and sixteen jobs were preserved; no GPU submission or production review was made. Evidence: `artifacts/editor-20261023/`. Broader behavior/world/audio and 60–90-minute acceptance remain incomplete.
- [x] Guide returning-motion creation through a plain-language action, a painted area and a protected-scene preview; reuse an existing subject area and append mask-only corrections without another GPU render. Verified independently of the broader behavior-authoring acceptance below.

**Guided authoring checkpoint — 2026-10-21:** New motion offers five starting points, paints Include/Protect areas with Undo/keyboard access, carries rendering defaults and saves or explicitly requests a first take. Existing takes expose source-frame area correction and deterministic CPU recomposition; originals and review status are preserved. Another take now chooses a fresh variation unless seed reuse is selected. Isolated browser checks covered save, queue, correction and validation; its real-scene 124-frame correction passed full decoding and protected-pixel replay. 143 tests ran (142 passed, one OS symlink skip); build and 49 Python checks passed. No live render or approval was added. Full behavior pools/weights/cooldowns, different-ending-pose UX and Episode simplification remain pending. Usage: `docs/GUIDED_MOTION.md`; evidence: `artifacts/guided-motion-20261021/`.

- [x] Click/define manually marked regions on master image to select actor, animal, object or environment. Wizard v1 supports drawn boxes, polygons and coordinate boxes with feathered-mask previews.
- [ ] Author named states, actions, idle pools, variant weights, rarity, cooldowns, spacing, conditions and transitions with plain-language labels.
- [ ] Simulate a short schedule within the editor; display timeline and reasons for event selection or exclusion.
- [ ] Clearly distinguish independent logical schedules from simultaneous visual compositing; surface resource-lock conflicts.
- [ ] Make character/object definitions reusable across different scenes in the same world without accidental identity changes.

**Acceptance:** creator builds a scene's behavior plan without editing code/JSON and previews a deterministic schedule.

## M7 — Long-form, reliability and quality [P1]
- [ ] Parameterize duration to 60/90 minutes (and arbitrary sensible values) without source-code edits.
- [ ] Add variability/distribution diagnostics: repeats, event frequency, quiet periods, rare-event counts, duplicate appearances and time constraints.
- [ ] Run hour-long export and verify exact duration, continuous audio and no broken boundary transitions.
- [x] Resume missing/failed Comfy jobs without duplicating output; preserve exports after server disconnect. Resume uses recorded prompt ownership for polling/download only. An uncertain submission stays visible and is never automatically submitted again; this does not reconstruct an unknown prompt ID.
- [ ] Add portable project reopen/move with missing-asset reports and hash validation.
- [ ] Document real H3 performance on user's RTX 4070 setup; test alternative workflow adapter only if motivated by results.

**Acceptance:** an unattended configured 60–90-minute episode exports reliably from previously approved source media, with traceable manifest and stable world continuity.

## Later enhancements [P2 — explicitly defer]
- [x] Validate/import a native fixed-camera CozyClay keyframe ZIP as an immutable, unsubmitted H3 recipe with source provenance. Prove deterministic native primitive motion exports and preserve the isolated upstream export fix. Reference video/depth/normal conditioning and human-contact/rigged-character acceptance remain unimplemented. See `docs/COZYCLAY_H3.md` and the dated digest evidence.
- [x] Run one separately unapproved CozyClay→H3 rigid-object candidate: 124 frames / 24fps, full source/output decode/timestamps, all 124 lossless protected-pixel checks and paired browser playback/exit holds. Coarse contact-and-return motion is visible; exact trajectory/timing and production join approval remain pending. Evidence: `artifacts/digest-trials-20261023/cozyclay/review/`.
- [ ] Multi-region/masked character compositing with proper occlusion and background preservation.
- [ ] More sophisticated graphic World Bible/adjacency map and event graph; richer cross-episode arc planning.
- [ ] Smart suggestions, segmentation or model-assisted clip review, if desired by creator (never required in runtime director).
- [ ] Expanded workflow adapters (Wan, LTX, etc.) and reference/first-last-frame conditioning support where proven.
- [ ] Dedicated desktop packaging/installer, proxy previews, OTIO interchange and publishing integrations.

## Immediate Codex ticket: START HERE

**Goal:** make a small, honest, testable first slice, not the whole app.

1. Read `AGENTS.md`, `PROJECT_TRUTHS.md`, `HANDOFF_PLAN.md` and this tasklist.
2. Inspect the actual local workspace. Report recovered files/Git state; preserve them.
3. Implement **M0 + core M1** with fixture scene `SCENE_A`, actor `READER`, actions `READ_IDLE` (three variants) and `SIP_TEA` (two variants), all mocked as metadata (video generation **not** required for this ticket).
4. Simulate `10:00` of elapsed timeline twice with the same seed: verify manifests byte-equivalent under canonical serialization. Test invalid actions don't run, full-frame resource collisions cannot occur, and a no-clip fallback produces a valid hold.
5. Sketch/mock ComfyUI adapter interface and connection status. Do not invent H3 node IDs.
6. Return run/test instructions, files changed, test results, next three tasks and any specific creator input needed.

### Acceptance tests to automate before marking first ticket done
- Same scheduler version + identical seed/config/world revision/approved clips => identical event timeline.
- Incompatible before/after state or non-approved variant => never placed.
- Full-frame tracks cannot collide; background ambience remains legal where explicitly declared.
- Exact 10-minute output duration in event manifest (frame timebase explicit).
- An episode draft cannot mutate committed world facts.

**First handoff deliverable from Codex:** runnable offline simulator + tests + brief evidence report; **not** a claim of completed video software.

**Scene-authoring checkpoint — 2026-10-21:** reusable motion recipes now connect imported images to the proven H3 pipeline without editing JSON. The wizard authors region geometry, feathering, context crops, idle/action or distinct pose-change states, prompts, seeds, timing and an explicit VAE. Saved revisions preserve old takes; new variation seeds and one-second decoded endpoint holds support review. A 39-frame live reader take completed and remains unapproved. Ten focused recipe tests cover small/odd image geometry, EXIF orientation, protected pixels, immutable revisions, workflow/model pinning and the API/encoder flow. Full-suite/build evidence is in docs/MOTION_RECIPES.md and artifacts/recipe-wizard/. M6 behavior pools, weights, cooldowns, simulation and episode assembly remain incomplete.

**Second-image acceptance test — 2026-10-21:** the wizard successfully configured the separate portrait reading-room still and generated one 39-frame sleeping-cat take from a small crop at the image edge. All 39 raw frames, lossless replay checks and full MP4 frame count passed; actual saved samples matched. Protected lossless pixels remained exact; small lossy-video differences are documented separately. The take remains unapproved. Reproducible audit and browser evidence: artifacts/wizard-second-image-20261021/README.md. No episode or approved-library acceptance is implied.

## Film audio integration - 2026-11-13 checkpoint
- [x] Extend existing editor with immutable WAV import, explicit source review, separate production/music placements, trim/gain/fades and revision persistence.
- [x] Mix saved placements during existing export; retain deterministic silent behavior for legacy projects. Isolated real ACE-Step plus synthetic production sound exported and tested.
- [x] Full offline regression: 219 passed, one Windows permission skip (220 total), Python checks and frontend build passed.
- [ ] Verify actual H3 audiovisual test media inside editor after supported transfer to Toast.
- [ ] Synchronized live Canvas audio preview, waveform/loop tools and direct ACE-Step job adapter.
- [ ] Broader linear short-film shot assembly and reusable FMV branching. This audio slice does not implement them.

## Film project/sequence milestone - 2026-11-13
- [x] Independent named projects/sequences above preserved scene composer, immutable reviewed video sources, ordered trimmed shots, separate audio, save/reopen/export.
- [x] Actual moving two-shot first cut + accepted ACE music,214frames8.917s720p24fps; sources preserved. Alternative cut independently edited/saved/reopened/exported through browser.
- [ ] Script/storyboard authoring, direct new-generation shot workflow, transitions/ripple editing, live mixed preview and FMV branches remain future work; do not mark full filmmaking pipeline done.

- [x] Film library reference recipe path restored with one existing hash-preserved sleeping-cat recipe and its immutable pose/mask assets; no new generation. See artifacts/film-reference-recipe-20261113/verification.json.

## Joint AV workflow milestone - 2026-11-13
- [x] Text-only proven H3 recipe integrated into Film with explicit brief/seed, read-only preflight, immutable jobs/receipts, safe retries and reviewed video/production-audio imports.
- [x] Actual worker compatibility preflight and no-generation browser QA;237test full regression passed with1existingOS skip; end-to-end mocked AV export verified.
- [ ] Verify a real completed jointAV result through the new adapter using a user-directed brief; supported transfer of old test media remains blocked.
- [ ] Direct ACE-Step job routing, reference-conditioned jointAV, script/storyboard authoring and FMV branches.
- [x] Actual previously accepted H3 AV package imported after user download; separate real bell+production+ACE music sequence exported and decoded with unchanged originals. New adapter live-generation completion still not exercised by this recovered-test import.

- [x] Direct explicit ACE-Step cue jobs with exact tested recipe, local preflight, owned status/import, source audition/review independent of picture shots, immutable provenance and non-blocking provider execution. Full mock lifecycle + real old-task poll/download verified; no unrequested creative generation.
- [ ] Exercise a fresh creator-directed music cue through new submission path; no new creative brief provided in this milestone.
- [x] Restore foundational FCP7 pane arrangement and tested operational conventions while preserving Film backend/cuts; stable contextual generation/audio tools. Evidence artifacts/film-fcp7-restore-20261113/VERIFICATION.md.

## Integrated FMV first slice - 2026-11-13
- [x] Inspect original Titanic prototype requirements and actual story/performance runtime without changing them.
- [x] Project-owned sequence-level branching document, optimistic saves, stable nodes/choices, frozen media/provenance and validation.
- [x] Contextual FMV Viewer authoring and Canvas rehearsal without restructuring the FCP7 shell.
- [x] Real existing-media technical fixture, independent frozen movie hash verification and original cut preservation.
- [x] Backend full regression253tests/252passed+1existing skip;75Python checks clean.
- [ ] Titanic-specific dialogue/performance mapping, flags/inventory, timed hotspots and game-runtime export (not implemented by this slice).
- [x] Final browser FMV save/reopen/branch/terminal/cycle/replay/exit playhead QA and TypeScript/Vite build passed; fixed FCP7 layout retained.

## Generative timeline/frame references - 2026-11-13
- [x] Persistent generation destinations, real status placeholders, metadata, candidate import and revision-safe approval-gated placement.
- [x] Immutable image upload/sourceframe extraction, first/last role bindings and UI/API parity.
- [x] Actual text-toAV and pairedfirst+last localworker tests; preserve frozen provenance and measured duration.
- [x] Browser candidate review/place/export, FABLEcut playback, referencecapture/selection/persistence/preflightinvalidation.
- [ ] Browser observation of active animation, fileupload, musictrim/conflict; backendmock tests do not imply these UIflows verified.
- [ ] Seamless generativeextension, alternative-angle imagegeneration, exact ripple/roll editing and whole-song pacing (not completed by reference binding).

## Continuation and audio-first milestone - 2026-11-13
- [x] Actual renderedlast-usedframe continuation, immutablelineage, stale guards, aligned1frame boundarypolicy and explicitreview/place.
- [x] Realclosing-book continuation study generated/exported separately from mainFABLEcut.
- [x] Trueaudio-only savedsequences, WAVexport, realwaveforms, markers/selection, independenttimebase, picturelaterwithoutshorteningaudio.
- [x] Explicitgenerationplacement fixedaudio/rippleaudio options, no silentvoice shift on audio-firstdefault.
- [x] 281backendtests cleanwithoneexistingWindows skip; Unicodeprovenance regression.
- [ ] Native ripple/roll handle operations and lip-sync synthesis remain separate future capabilities.

## Audio-led shot planning - 2026-11-13
- [x] Persistent selected intervals, shot-specific briefs/reference roles, grouped candidate lineage and bound generation.
- [x] Picture-only interval fitting, explicit trim, short-take rejection, revision/idempotency guards and unchanged soundtrack.
- [x] Real15-second FABLE existing-media author/review/fit/export workflow, independent decode/hash/baseline checks and stable FCP7 browser QA.
- [x] Final291tests/290pass+1existing skip;84Python checks; finalTS/Vite buildDiuiUT7O.
- [ ] Whole-song bounded streaming import and versioned180-240s ACE adapter; no new song rendering or pacing approval yet.

## Whole-song infrastructure - 2026-11-13
- [x] Bounded streamed256MiB/600s WAV import, immutable originals and efficient verified waveforms.
- [x] Versioned180/210/240s ACE capability alongside preserved proven30s recipe; lyrics/structure and honest duration/runtime provenance.
- [x] Actual180s34.56MB HTTP upload verified, no audition; five existing cuts unchanged; music job count0.
- [x] Browser preflight/draft/invalidation/fallback QA and302test regression with one existingWindows skip.
- [ ] Browser automated file-picker upload blocked by extension file-URL permission; HTTP route verified separately, no setting changed.
- [ ] Actual full-song/vocal render and pacing review with a selected original approved brief; infrastructure tests do not establish creative quality.


## Playback correction - 2026-11-13

[x] Completed-render Canvas playback and timeline Space correction verified in Chrome: 422-frame chorus through end, pause/resume, text-field exemption, stale-render fallback. Live unrendered seamless playback remains pending. Evidence: `artifacts/playback-fix-20261113/QA.md`.

## Film editor UI treatment - 2026-11-13

[x] FCP7-arrangement UI pass (type, pane structure, Browser bins, monitors, timeline legibility, unified tool panels, non-colour state cues); read-only browser checks passed. Evidence: `artifacts/ui-treatment-20261113/QA.md`.
- [ ] Re-run append / save / reopen / export on a disposable cut with the new UI when dot is not mid-edit.
- [ ] Check file-picker imports, approvals and a real generation job's running state in the new panels.

## Film editor FCP7 alignment - 2026-11-13
- [x] Step 1 keyboard parity (shared registry, typed timecode, sequence In/Out, markers).
- [x] Step 2 selection separate from playhead; Insert F9 / Overwrite F10 / Replace F11 with Canvas buttons; Shift+Delete ripple delete; audio lift. Saved / reopened / exported on test sequence `sequence.f3d17782d6724490b4b3562a3e1e4839` (352 frames).
- [x] Step 3 per-sequence drafts, Save all (Ctrl+Alt+S), Render (Alt+R), render bar - write pass 2026-11-13: Save all saved 2 sequences, stale draft refused by server, Render red -> striped -> green (manifest hash matches).
- [x] Boden decisions 1/3/4/6 (2026-11-14): Browser select vs double-click open, Render saves first, sequence TC from 01:00:00:00, app-window launcher - built, checked without saving.
- [x] Step 4 slices A+B: Browser lists video/audio/stills, automatic bins, sortable columns, row menu (Reject behind confirm) - checked without writes.
- [x] Step 4 slice C: one transport for both monitors (3.5) - built, step 2 playback regression rerun in rendered and live mode without saving.
- [x] Gaps on V1 - dot (server, 2026-11-14).
- [x] Step 5 slice A: UI gaps + Lift - write pass 2026-11-15: saved, reopened, exported; gap frames black. Playback across a gap verified live and rendered (2026-11-15).
- [x] Step 5 slice B1: razor, roll, ripple, slip, extend by keyboard + palette - checked without saving.
- [x] Step 5 slice B2: drag edit points (roll/ripple), slip by mouse - checked without saving; gap playback verified.
- [x] Step 5: drag clips to move (overwrite) / rearrange (Alt) with snapping (N) - checked without saving.
- [ ] Step 5 last: audio level/fade overlays (4.7).
- [x] Generation flow A1-A3 (job cards, one-click Generate, brief-first form) - built; A2 not exercised live.
- [x] Generation guide (optional walkthrough) + clickable requested-take blocks with Hide - checked without writes.
- [x] One review per take (picture + sound) and a History tab - checked without approving.
- [x] Generate tab replacing H3 take + Music cue, with Where it goes (playhead / before / after clip / end / library), flags on V1, Place from History - checked without generating.
- [ ] Generation flow A4-A8 (audition in context, place with editor tools + sound, timeline entry points, per-sequence drafts, vocabulary); server B1-B4 for dot.
## Production references follow-up (2026-11-15)
- [x] Backend-only versioned visual reference registry, explicit H3 first-frame compiler, pinned shot-plan generation lineage; 27 focused regressions pass.
- [ ] Add FCP7-preserving Characters/Locations/Props Browser and reference inspector; preserve bindings on plan resaves.
- [ ] Seed verified Mara/van master views, deploy service safely, and validate one real bound take end-to-end.
- [ ] Add separately verified multiview/geometry conditioning; current adapter only consumes first/last images.

## Production Library actual multi-image slice (2026-11-17)
- [x] Ordered 1-9 reference-image conditioning, pinned character/location/prop view revisions, role tokens, separate uploads and take provenance; safe preflight and mock lifecycle tests.
- [x] Preserve first-frame mode and existing FCP7 panel layout; TypeScript / isolated build verified.
- [ ] Coordinate shared deployment with Claude; isolated browser smoke first.
- [ ] Validate real multi-reference visual quality after selected character views are reviewed. Experimental FL2VA route is not proven native REF2VA or 3D consistency.
- [x] ; Lift / ' Extract In to Out (Premiere keys; split at In/Out, V1 + all audio incl. music) - checked without saving.
- [x] Audition in context, thumbnails, menu bar (2026-11-17) - checked without writes.
- [ ] Boden: one generate -> review -> place -> save pass (checklist in chat 2026-11-17).

## Browser multi-selection — 2026-11-19
- [x] Ctrl/Command-click toggles, Shift-click ranges, visible-source Select All, clear and separate Viewer opening; sequence rows share selection gestures.
- [x] Bulk source-bin creation and moves, including filtered-selection scope; isolated Chrome checks and all frontend checks/build pass. Reproduce via `artifacts/browser-multiselect-20261119/QA.md`.
- [ ] Manually confirm bulk drag-and-drop in the creator's editor; automated native drag attempts did not establish a completed drop.

## No approve/reject, clip length, Queue tab — 2026-11-19
- [x] Approve/Reject removed from Film (server + UI); finished takes import themselves; Browser shows use (in sequence / used / unused). Python Film/audio/timeline tests and all frontend checks pass.
- [x] Drag Browser clips onto V1 (Insert) and sound onto A1/A2; verified on the scratch library (`film-ui-test`), including saving a sequence with a rejected-status clip.
- [x] Generate: clip length (seconds → frames, step 4) capped by a creator "longest clip" limit (default 124 frames, the only proven length).
- [x] History renamed Queue: rendering / failed / waiting-to-place jobs; finished clips fold away.
- [ ] Restart :8769 and rebuild dist (server and UI must change together).
- [ ] Boden: one real H3 run at a non-124 length (e.g. 96 frames) to confirm the worker returns exactly that many frames, then decide the longest-clip limit.

## Separate Clip Editor — 2026-11-19

- [x] Standalone phone-width editor and opt-in private LAN listener with a separate working library.
- [x] Upload → choose length → generate → append. Scrub to a specific frame and use it to generate the next clip. Reorder, reopen, play and export a two-clip cut with sound. Verified over private HTTP using the mock worker and CPU-encoded media.
- [x] Accept and normalize larger mobile stills. Verified a 48 MP JPEG upload, EXIF orientation, and preservation of the original bytes.
- [ ] Verify one fresh non-default-length result on the live H3 worker and open the editor from a physical phone.

## Clip Editor local prompt drafting — 2026-11-24

- [x] Draft editable text and a valid clip length with a local model. Offline HTTP coverage includes invalid drafts and verifies drafting creates no render or sequence changes.
- [x] Draft with local Bionic Qwen, generate one H3 clip, and confirm playback and full decode in an isolated library. Reproduce with **Draft with Local AI** in `README.md` using `assets/test_scene/test_still.png`.
