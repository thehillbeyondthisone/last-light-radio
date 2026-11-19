# Creator studio verification — 2026-10-21

The local React interface and Python service implement the requested scene
import → H3 generation → candidate review flow. This is separate from the
offline scheduler; an episode assembly UI and renderer remain future work.

## Automated checks

- `scripts/run.ps1 test`: 86 tests ran, 85 passed, one Windows symlink-permission
  skip. GPU and LAN behavior use fake clients; the API test opens a temporary
  loopback server. Tests include exact master bytes, duplicate imports, durable
  generation identity, approval requirements, conflicting reviews, later
  rejection, altered-media detection, legacy read-only import and byte ranges.
- `scripts/run.ps1 check`: 23 Python files, no syntax/whitespace problems.
- `npm run build --prefix frontend`: strict TypeScript check and Vite production
  build passed. React/ReactDOM 19.3.1, TypeScript 7.0.2 and Vite 8.3.5 are pinned
  in `frontend/package-lock.json`.

## Browser and live worker

The in-app browser exercised the built application at
`http://127.0.0.1:8765`, backed by `.local/studio`:

1. Worker Test & Save reached `http://192.168.1.168:8188`, reported RTX 4070 and
   987 node classes, and validated the recovered H3 workflow.
2. The scene-import dialog read `assets/test_scene/test_still.png`. Import
   returned the existing exact-hash scene without duplicating or changing it.
3. Generate H3 clip submitted one noncanonical reading-idle test, seed 8.
   Local job ID: `2f704dba9a354680b99927add39efba7`. Background polling retrieved
   its animated WebP and registered it as an unapproved candidate.
4. The review room played the result and displayed the master comparison plus
   first/middle/last samples. Approval was saved with explicit visual
   acknowledgement and technical-test anchor labels. Rejection was then saved
   with a continuity-review note. Final status is **rejected**, with two review
   revisions and original media retained. It is excluded from approved results.
5. After restarting the server, scenes, jobs and both review decisions persisted.
6. The imported `Cat Resettles` MP4 played in the browser: 1920 × 1080,
   5.166667 seconds, readyState 4, no media error. Play and pause worked.
7. At the 814-pixel viewport, content width matched viewport width, with the
   inspector stacked below the preview. Browser warning/error logs were empty.

The eight imported approvals were unchanged. These tests verify application
behavior, not production visual quality or seamless loop suitability.

Screenshot: [`artifacts/studio-review.png`](../artifacts/studio-review.png).

## Existing library preservation

The creator selected a separate working-store import from
`D:\LastLightRadioMedia`. The importer opened `last_light_radio.db` in SQLite
read-only immutable mode, checked for an active WAL, copied primary files and
database records, then rechecked the database checksum. Source SHA-256 before
and after:

```text
d26f6e74675d0e4073e9915aeafec035b8ec0741f2c5053537ae68c01f406764
```

Import ID: `d26f6e74675d0e4073e9915a`.

- 102 primary files archived with checksums and source paths.
- Three scene stills: Apartment Pilot, Looking Outside and Exterior Reference.
- Eight completed MP4 candidates, preserving earlier approval records.
- One failed candidate retained as job history, without a render retry.
- Two final eight-minute exports archived as historical media.
- Masks, workflow/provenance, evidence, sequence manifests and every source
  database table retained in the import archive.

Regenerable raw frames, render chunks and benchmark caches remain at the source
and were excluded from the working copy. The complete manifest is
`.local/studio/legacy/d26f6e74675d0e4073e9915a/import_manifest.json`.

The working store now contains four stills (three imports plus the technical
example), ten candidates (eight historical, two technical) and eight latest
approved decisions. The original CLI smoke candidate remains unreviewed.

Those counts describe the initial interface checkpoint. Later user-generated
takes and the restored production test extend the candidate library.

## Restored production checkpoint

The creator requested restoration of the original crop/mask/start-end-pose
pipeline, then authorized the installed INT8 video VAE while waiting for the
original FP16 model. The exact old template is preserved independently of that
execution override under `workflows/h3/production/`.

Test `7f374713fdb64319a5fe039bc1017d79` / Comfy prompt
`2b1df2ff-b9d5-439c-b950-cc3f7d470cc9` completed with:

- Original Reading Idle A direction and seed 883101.
- Pixel-identical old first/last crops, 768 × 768 at (200,230), recovered reader
  mask and fixed canonical full-scene background.
- Turbo eight-step, res_multistep/simple graph, with the explicit INT8 VAE change.
- 124 verified raw PNGs, 24fps, 5.166667s, full-scene 1920 × 1080 H.264 output.
- 206.025s recorded server execution; no peak VRAM or general benchmark claim.
- Exact executed workflow match, full output video decode passed.
- Zero changed protected pixels in all three lossless assembled frame samples.

The browser submitted the request through the recovered controls. A service
restart resumed the same accepted prompt. Review displayed the earlier and new
MP4s with shared replay controls; both loaded at readyState 4 with no errors and
played at matched timestamps (5.055107s / 5.055065s during inspection). Console
warnings/errors were empty. The new candidate remains unapproved, with no
review rows; eight historical approvals remain unchanged.

Updated verification: 101 tests ran, 100 passed and one Windows symlink-permission
skip. Strict TypeScript/Vite production build and Python baseline checks passed.
Screenshot: [`artifacts/restored-motion-studio.png`](../artifacts/restored-motion-studio.png).
Reference compositor analysis: [`artifacts/motion-analysis/README.md`](../artifacts/motion-analysis/README.md).
Labeled old/new video, enlarged actor samples and reproducible metrics:
[`artifacts/restored-motion-comparison/README.txt`](../artifacts/restored-motion-comparison/README.txt).

The comparison CLI confirmed identical prompt, seed, duration and frame rate;
the only workflow changes are the VAE and job-owned input/output paths. All
1,797,469 protected pixels checked in each lossless boundary sample were equal
to the canonical background. Numeric differences between clips describe RGB
values, including encoding/compositing effects, and are not quality scores.
The standalone comparison video also passed full decode validation.

## Ten-minute visual pilot — 2026-10-21

The later continuous-ambience checkpoint adds rain/steam controls and a saved
effect-enabled draft, with a separately exported 24-second proof. The completed
ten-minute MP4 described below remains preserved.

### Continuous ambience verification

Story: Pilot builder's effect controls → saved pilot API → recovered masks and
versioned procedural recipe → live canvas timeline and CPU MP4 export.

| Boundary | Evidence |
| --- | --- |
| Controls | Browser enabled rain 12% / steam 18% and saved `d175b1191f41517ad3503956eb7f6416`. |
| API/data | Manifest pins both mask hashes, strengths, particles, seed and absolute-frame clock; registered mask routes load. |
| Preview | Canvas clock advanced from the first hold through reading/page-turn joins to frame 1185, then paused; canvas/base bounds matched. |
| Export | Separate 24s / 576-frame / 1920x1080 MP4 fully decoded with correct timestamps; enlarged detail video also validated. |
| Protection | All 576 replayed frames preserved 1,392,868 protected pixels per frame; both effects changed during 451 adjacent hold-frame pairs. |
| Preservation | Eight approvals, eleven pending candidates and twelve H3 jobs unchanged; original pilot retained; no new ComfyUI submission. |

Browser media/console errors were absent. Review room also displayed “7 pending
takes have earlier approved versions” and linked the INT8 reading-idle take to
its approved original. No archive or review decision was made. The full suite
ran 126 tests: 125 passed, one Windows symlink skip. Strict TypeScript/Vite build
and 39-file Python baseline checks passed. See [AMBIENCE.md](AMBIENCE.md) and
`artifacts/ambience-20261021/` for repeatable commands and limits.

The creator requested an assembled pilot from approved clips and holds, plus
timeline preview and MP4 export. The browser opened **Pilot builder**, selected
all eight approved Apartment clips, saved seed 7 / Quiet and queued the export.
Timeline scrubbing, sequential clip playback, advancement to an actual-exit-frame
hold and pause were exercised. The API persisted the immutable plan and source
review versions; no new H3 jobs or review decisions were created.

Pilot `2481403c3b2e2ba6c035718f94cc734c` completed with 23 motions and 24 holds,
1920 × 1080, 24fps, 14,400 frames and exactly 600 seconds. The CPU worker fully
decoded the finished MP4 and checked all presentation timestamps. All 24 holds
matched the current RGB frame before compression. A separate read-only audit
inspected 118 exported boundary/hold samples and found no black frames.

The completed browser player reported duration 600, dimensions 1920 × 1080,
readyState 4 and no media error. Native playback advanced to 46 seconds and
paused normally. Browser warnings/errors were empty. A server restart and page
reload reopened the saved **MP4 ready** pilot and its downloads. Normal cancelled
media requests are handled without attempting an error response on a closed
socket; the loopback test covers this observed player behavior.

The full offline suite ran 120 tests: 119 passed, one Windows symlink-permission
skip. The nine pilot tests cover deterministic length, approval/media changes,
state compatibility, exact hold encoding, revocation during export, persistence
and loopback routes. Strict TypeScript/Vite build and 35-file Python baseline
checks passed. Final files, screenshots and numeric evidence are in
[`artifacts/pilot-20261021/`](../artifacts/pilot-20261021/README.md).

This is a silent draft for creator review. Small source clip-entry differences
remain visible in join diagnostics. Audio mixing and broader shared-world
authoring are pending. Original media and all eight source approvals remain
unchanged. Repeatable usage: [`PILOT_BUILDER.md`](PILOT_BUILDER.md).

## Service and media boundaries

The Python HTTP service binds to 127.0.0.1. The browser uses same-origin JSON
requests with a studio header; the server rejects foreign origins and invalid
Host headers. The service serves only registered media or built frontend files.
Worker requests use the existing validated H3 adapter. No shared queue clearing,
interruption, automatic uncertain-submission retry or canon mutation is exposed.

Master/candidate copies are application-immutable with checksums and conflicting
overwrite refusal. This is not a filesystem permission lock. Approval copies
are historical artifacts; current status and hash validation determine library
eligibility. MP4 timing imported from the old database retains that provenance;
sample decoding alone does not certify every frame or visual continuity.

## Scene-setup wizard v1

The creator can now import a scene, outline an actor, preview a feathered mask and automatic context crop, choose poses/states, and save a versioned H3 recipe. Browser verification saved revisions one and two, submitted exactly one short INT8 take through Generate, and played it with decoded first/last frame holds. All 39 raw PNGs and the MP4 decoded; three lossless samples retained exact protected pixels. The new take remains unapproved. Full offline suite: 111 tests, 110 passed and one Windows symlink skip. After a final saved-VAE default fix, all 10 recipe tests passed again. Strict TypeScript/Vite build and 31-file Python baseline checks passed. Browser warnings/errors were empty. See MOTION_RECIPES.md and ../artifacts/recipe-wizard/validation.json.
