# Continuous rain and mug steam

New timelines use **masked-ambience-v3**: layered rain and larger rolling glass
droplets, with the established mug steam. Existing v1/v2 timelines still use their
original renderer. Optional ambience is applied after the exclusive character
picture has been assembled. It reuses the recovered Apartment masks and leaves the H3
workflow, approved clips, canonical image and original D: library unchanged.
The renderer is new code; the old effect implementation was not recovered.

## Use it

In **Pilot builder**, choose **Apartment Pilot**, then enable **Window rain**
and/or **Mug steam** under **Continuous ambience**. Adjust their strength and
build a new timeline. Play or scrub the preview before exporting. The new plan
pins the selected masks, parameters, seed, particles and renderer version;
the earlier pilot and its MP4 remain available separately.

The browser and CPU exporter evaluate effects from the **absolute episode frame**.
Seeking to 30 seconds evaluates that instant directly. A clip boundary does not
restart the effect, and a hold does not freeze it. The base picture continues to
use exact decoded exit-frame holds; the effect is never fed back into that base.

The first version exposes the recovered Apartment masks. Authoring equivalent
effect regions on a different image is a follow-up to the existing region wizard;
the app does not assume a mug/window location on arbitrary images.

## Appearance and protection

- **Rain:** 800 seeded streaks across three depths, with different speeds,
  widths and lengths. Four-part tapered tails and subpixel rendering soften the
  motion; a shared, slowly changing wind gives the shower direction. Water
  highlights sample the underlying picture to catch warm neon or cool city light.
  The glass adds 120 beads, including 26 runners and a sparse set of larger
  drops. Ten runners have a resting diameter of roughly 13–22 pixels at the
  recovered window's full resolution. Pinned adhesion/release curves make them
  creep, accelerate, catch and release again. Their bodies narrow and stretch
  with speed; recent-position trails follow their winding paths and fade.
  The lens magnification varies through each drop. Each bead bends the current background, with
  a dark lower rim and a small upper glint. The saved mask's
  cutouts protect the window frame, railing and foreground silhouettes. The
  effective mask additionally excludes every selected actor mask's nonzero
  support, including feathering. Nothing outside the effective mask changes
  before encoding. Rain geometry is normalized to the saved region and is not
  tied to a hardcoded window, landmark or city. Existing painted rain is retained.
- **Steam:** the image already contains a painted plume. A small, smooth local
  displacement makes that existing plume drift within the saved feathered steam
  mask. Displacement tapers to zero at its vertical endpoints, keeping the mug
  anchored. It is restrained movement of existing pixels, not a fluid simulation
  or a new H3-generated plume. Larger changes would benefit from a clean
  background and a separately isolated steam layer.

The default rain strength for newly enabled layers is 22%; steam remains 18%.
Both use the absolute episode clock, including droplets and trails. Seeking
evaluates the requested instant directly, without warming up a simulation.
Steam's original seeded phase is preserved. No dependencies or model calls were
added. v1/v2 rendering remains available so saved plans and exports retain their
appearance.

Effects are scene-specific drafts for visual review. Inspect the chair/plume
boundary, rain cutouts and both reader poses. If a later action moves the mug or
crosses an effect region, disable or re-author that effect mask for the action.
Canvas/Pillow rasterization can differ slightly; use the MP4 for final judgment.
H.264 is lossy, so exact protected-pixel guarantees apply before video encoding.

For other effects, the same compositor can later accept a separately reviewed
transparent clip, with a continuous phase and a checked loop seam. Slowly moving
glass beads and short trails now use local optical approximations; accumulating
and merging water, surface splashes, audio and true volumetric steam remain
future work. None requires regenerating the character library.

## Short preview and audit

The current saved v3 timeline is `05a9a35fdd6464bbce3483249185df0a`, named
**Apartment Pilot · rolling raindrops**, seed 7, rain 22%, steam 18%.
The separate **24-second** review includes the initial hold, complete Reading
Idle B clip and actual exit-frame hold. Whole-scene and enlarged-window MP4s
passed full 576-frame decoding and timestamp checks. The rain bed is identical
to v2 at the same seed; the changes concern the glass drops. Previous drafts,
masters and approved clips are preserved.

```powershell
python scripts/preview_ambience.py --pilot-id 05a9a35fdd6464bbce3483249185df0a --seconds 24 --output NEW_PREVIEW_FOLDER
python scripts/audit_ambience.py --preview-folder NEW_PREVIEW_FOLDER
```

Evidence: `artifacts/rolling-drops-20261021/preview/`. The enlarged view is
`rolling-window-detail.mp4`. Full suite: 132 tests, 131 passed and one Windows
symlink-permission skip. The 12 focused ambience tests cover motion with pauses,
acceleration, stretching and lateral drift, direct seeking, unavailable glass
models, protected pixels, exact legacy v2 output and the retained steam phase.
TypeScript/Vite and 41-file Python baseline checks passed.

All 576 frames were replayed for the exact pre-encoding mask audit: zero
changes in 1,392,868 protected pixels per frame. Both rain and steam moved in
451 successive hold-frame comparisons. Browser playback crossed the motion
and hold boundaries, paused and sought directly to frame 14,399; the previous
v2 draft also loaded correctly. Canvas/base bounds matched and no console
warnings or errors were observed.

The rolling curves approximate adhesion and gravity; this is not a fluid solver.
Drops recycle only beyond the pane edges, and trails never connect across that
cycle boundary. Their paths and timing are pinned in the draft, so playback and
export need no simulation warmup. A full ten-minute v3 export remains pending.

### Earlier v2 checkpoint

The saved v2 timeline is `8f5e9ac2c399f7bc57db95a49fd59b4c`, named
**Apartment Pilot · rain on glass**, seed 7, rain 22%, steam 18%.
Its **24-second** 1920 × 1080 / 24fps review clip includes the initial hold,
the complete Reading Idle B clip and its actual exit-frame hold. It is a
separate draft; the original ten-minute export is preserved.

```powershell
python scripts/preview_ambience.py --pilot-id 8f5e9ac2c399f7bc57db95a49fd59b4c --seconds 24 --output NEW_PREVIEW_FOLDER
python scripts/audit_ambience.py --preview-folder NEW_PREVIEW_FOLDER
```

Evidence: `artifacts/rain-v2-20261021/final/`. `ambience-preview.mp4` is the
whole scene; `window-detail.mp4` is an enlarged view of the same 24 seconds.
The full 576-frame decode and presentation timestamps passed. Exact lossless
replay changed zero of 1,392,868 protected pixels per frame; rain and steam
each moved in all 451 hold-frame comparisons. Automated coverage includes
legacy v1 pixels, seeded depth/glass parameters, retained steam phase, lens
refraction, seek replay, protected regions and CPU export. Full suite: 129 tests,
128 passed and one Windows symlink-permission skip. TypeScript, production build
and the 40-file Python baseline check passed.

### Earlier v1 checkpoint

The earlier saved 10-minute ambience timeline is
`d175b1191f41517ad3503956eb7f6416`, seed 7, rain 12%, steam 18%.
Only a **24-second preview** has been exported for this effect pass; the original
10-minute MP4 remains the completed full-length export.

```powershell
python scripts/preview_ambience.py --pilot-id d175b1191f41517ad3503956eb7f6416 --seconds 24 --output NEW_PREVIEW_FOLDER
python scripts/audit_ambience.py --preview-folder NEW_PREVIEW_FOLDER
```

The preview refuses to truncate a motion clip and preserves existing folders.
It includes the initial hold, complete Reading Idle B clip and actual exit-frame
hold. Both effects stay on the same clock. Evidence is in
`artifacts/ambience-20261021/preview/`:

- `ambience-preview.mp4`: 1920 × 1080 / 24fps / 576 frames / exactly 24 seconds.
- `steam-and-rain-detail.mp4`: enlarged mug and window views, same duration.
- `preview_manifest.json`, `preview_report.json`, `protected-pixel-audit.json`.
- Contact sheets show temporal samples and both clip boundaries.

Full preview decoding/timestamps passed. Replaying all 576 frames changed zero
of the 1,392,868 protected pixels per frame. Both effects moved in 451 successive
hold-frame comparisons. The browser also crossed multiple clip/hold joins while
its effect clock advanced, then paused correctly; canvas and base-image bounds
matched. No media/console errors were observed. Six focused ambience tests plus
the full suite passed: 126 ran, 125 passed, one Windows symlink-permission skip.
Strict TypeScript/Vite build and 39-file Python baseline checks passed.

## Why eleven clips are awaiting review

The current queue contains seven INT8 restoration comparisons (Reading Idle A,
Page Turn, Cat Ear Tail, Cat Resettles, Look Toward Window, Window Watching Idle,
Resume Reading), two wizard verification takes (reader and sleeping cat), and
two early full-scene H3 takes (first reading idle and Gentle idle).

There are no byte-identical output duplicates. The seven comparisons repeat
already-approved actions with the restored pipeline/INT8 VAE. All eleven stay
outside the pilot library until explicitly approved. Review room now explains
when an earlier approved take is available. Their media and review status were
left unchanged; no archive/delete action was requested after the clarification.
The queue audit is `artifacts/ambience-20261021/review-queue-audit.json`.
