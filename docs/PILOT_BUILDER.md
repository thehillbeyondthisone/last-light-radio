# Ten-minute pilot builder

The studio can assemble a silent visual pilot from the current approved motion
library. It uses deterministic Python scheduling and CPU video encoding. It
does not call ComfyUI, generate motion, change reviews or commit world facts.

## Creator workflow

1. Start `scripts/run.ps1 studio` and open http://127.0.0.1:8765.
2. Open **Pilot builder**. Choose a scene with compatible approved clips.
   **Apartment Pilot** currently has eight. Newly generated tests stay excluded
   until explicitly approved in Review room with matching start/end states.
3. Choose the clips, a title, an episode seed and a motion density. Quiet leaves
   at least 18 seconds between motions; Balanced uses 10 and Active uses 5.
   Behavior cooldowns can create longer holds.
   Apartment Pilot also offers optional **Continuous ambience** controls for
   window rain and mug steam. Build a new plan after changing effect settings.
4. Select **Build timeline preview**. Play the timeline, scrub it or select an
   event. The event table shows exact frame lengths and state changes. Expand
   join diagnostics to inspect differences at the next clip's entry.
5. Select **Export 10-minute MP4**. Keep the studio process running while its
   background CPU worker encodes and fully decodes the finished file to validate
   every frame and presentation timestamp. The interface shows progress/errors.
6. Play the finished MP4 or download it, its timeline manifest and event log.
   Saved plans and completed exports reopen with the working store.

The seed, density, selected media/review versions and scheduler version fix the
timeline. Rebuilding identical inputs returns the same plan. Changing a seed
changes eligible selections without changing clip durations or state rules.
Exact encoded bytes also depend on the installed FFmpeg/runtime.

## Continuity and source preservation

- Only currently approved MP4s with a pinned motion recipe, compatible poses,
  original scene dimensions and native 24fps timing are eligible. Imported
  historical clips use the recovered recipes; authored clips use their saved
  recipe revision. Unsupported approvals appear as visible exclusions.
- The master starts the timeline. A clip runs only from its compatible full-scene
  pose. Reading-to-window transitions enable window idles and a matching return.
  Reader and cat clips occupy one exclusive picture lane: no independent
  full-frame layering, guessed crop overlays, trimming or retiming.
- A base hold after motion repeats the **actual last decoded frame** of that clip.
  It never silently resets to the conditioning still. Before lossy encoding,
  the worker verifies that each hold's pinned image equals its current RGB frame.
  Optional ambience is drawn afterward and keeps moving during these holds.
- Every source video is hash checked and fully decoded during preparation.
  Plans pin master/media hashes, workflow provenance, approval versions, states,
  seed and timecodes. Approval changes or modified media block an existing plan's
  export; a revocation during encoding also blocks publication.
- A compatible pose label does not prove pixel-identical boundaries. Join RGB
  differences are diagnostics, with no automatic quality threshold. No fades or
  forced pose replacements are added. The assembled pilot remains a draft for
  creator review, even though its source clips are approved.

## Export contract and limits

V1 exports exactly 600 seconds / 14,400 frames at 24fps, using the master scene
dimensions (padding an odd dimension by one pixel when necessary for yuv420p).
The output is H.264, CRF17/veryfast, BT.601 limited range, fast-start MP4, **without
audio**. Music, sound ambience, audio licensing/mixing, configurable delivery settings,
longer episodes and the broader behavior editor remain future work.

The worker streams the complete picture into one encoder. A rejected, altered,
missing, incorrectly timed or undecodable source fails visibly. Final validation
checks full decode, exact frame count, dimensions, frame rate and timestamps.
It records the published checksum and every hold check in `export_report.json`.

Files live under `.local/studio/exports/pilots/PILOT_ID/`:

- `pilot.mp4`
- `episode_manifest.json`
- `event_log.md`
- `export_report.json`

Completed outputs are immutable. Retrying a failed/interrupted export starts
encoding the same pinned plan from the beginning, rather than resuming halfway
through the movie. A verified completed output is reused. A restart surfaces an
interrupted export and preserves source media and completed files.

The technical pilot world scope has no committed lore or chronology. Its visual
pose graph is not the finished shared-world or semantic behavior authoring UI.
The later rain/steam first pass adds separately masked continuous visual effects;
see [AMBIENCE.md](AMBIENCE.md) for the preview, protection checks and limits.

## Verified first pilot — 2026-10-21

Pilot `2481403c3b2e2ba6c035718f94cc734c`, seed 7 / Quiet, uses all eight existing
approved Apartment clips: 23 motion events (113.167s) and 24 holds (486.833s).
It returns to the reading pose and exports 1920 × 1080, 24fps, exactly 10:00.
The 41,912,704-byte file fully decoded with all 14,400 timestamps verified.
All 24 pre-encoding hold checks matched. Of 118 sampled boundary/hold frames,
none were black. Native browser playback loaded at 600s / 1920 × 1080 and played
without a media error; the console had no warnings/errors.

Evidence and a delivery copy are in `artifacts/pilot-20261021/`. The eight source
approvals, 12 H3 jobs and 20 candidate records remained unchanged. No new H3
submission was made. The original D: media library was not modified.
