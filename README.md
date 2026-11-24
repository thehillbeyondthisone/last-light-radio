# Last Light Radio

Music for places that are still awake.

A local creator tool for long animated episodes built from preserved scene
masters, approved motion libraries and deterministic rules. Worlds and scenes
are user supplied. The scheduler never calls an LLM or invents canon.

## Source repository and local data

The Git repository includes application source, tests, fixtures, recovered
workflows, documentation and the existing branding/test-scene assets.
Generated renders, screenshots, local libraries, worker configuration,
virtual environments and frontend build output remain local under `artifacts/`,
`runs/`, `.local/`, `node_modules/` and `dist/`. One historical Python file under
`artifacts/gap-backend-20261114/before/` is retained as a regression-test baseline.
Disposable test libraries and local environment files are also ignored.
Git attributes preserve file bytes across platforms so checksum-protected
fixtures and workflow provenance survive Windows line-ending settings.

A fresh clone does not contain the creator's working library or installed
ComfyUI models. Follow the setup commands below, configure the worker for your
machine, and back up local libraries/media separately from Git.

## Film editor (2026-11-13)

The default workspace now separates **Projects → named Sequences → ordered Shots**.
Use `OPEN_FILM_EDITOR.bat` for the persistent first-cut working library on port8769.
It contains real approved Reading Idle/Page Turn video copies and accepted ACE-Step
music, not the earlier static audio fixture. Trim/reorder shots, edit separate audio,
save independent cuts and export the film. **Scene animation** remains a separate
workspace. Read [docs/FILM_EDITOR.md](docs/FILM_EDITOR.md) for the hierarchy and limits.
The original `.local/studio` library and media are unchanged.

## Scene-animation foundation

The local React studio imports scene stills, submits H3 motion requests, tracks
jobs, and previews candidates for explicit approval or rejection. It preserves
master bytes, generation provenance and review history in a separate working
store. Existing MP4 libraries can be copied in without modifying their originals.

The preserved **Scene animation** editor uses a Final Cut Pro 7-style Browser, source
Viewer, sequence Canvas and timeline. Create and audition actions first, then
place approved takes on named subject tracks. Each subject's automatic idle
lane sits below its Motions lane; pools, pacing and seeds live in Subject setup.
Disjoint pinned masks let subjects animate simultaneously. Location and pose
changes are deferred. See [`docs/EDITOR.md`](docs/EDITOR.md).

**View → All tracks overview** provides the compact FCP-style timeline as an
optional layout; Standard remains the default. Small **− / +** buttons in the
timeline adjust track heights independently of the video preview and time zoom.

The editor saves deterministic 1–600 second sequences and exports silent
H.264 MP4s. Available window-rain and mug-steam controls use saved scene regions.
Automatic idles appear as nested sequence blocks; open **Reading** to inspect
its source cuts and return with **Episode sequence**. **FX3 · Video texture**
offers live strength (0–100%), grain size, pattern seed and on/off controls;
**Apply texture settings** saves the look for export.
The earlier **Pilot builder** remains in Library workspace, including its
approved ten-minute picture-state workflow. See [`docs/AMBIENCE.md`](docs/AMBIENCE.md)
for effect limits.
The offline deterministic scheduler and live ComfyUI bridge are also available
through the CLI. Broader behavior/world authoring and audio mixing remain pending.

Python + React was confirmed by the creator on 2026-10-21; desktop packaging
comes later. The backend uses Python, SQLite and filesystem media; the interface
uses React + TypeScript/Vite. Pillow validates stills and WebP frames. Optional
FFmpeg support supplies previews of imported MP4s. The offline scheduler itself
uses the standard library and needs no running GPU.

## Clip Editor for phones and LAN

The Clip Editor is a separate browser workspace with one autosaved sequence.
Use the Python and FFmpeg environment from the studio setup. No frontend build is required.

```powershell
.\OPEN_CLIP_EDITOR.bat
.\OPEN_CLIP_EDITOR.bat --host 192.168.1.68
```

Run the first command for this PC only, or run the second with this PC's
private IPv4 address from `ipconfig`. Open the address printed by the launcher
on your phone or PC. The default port is 8772. Keep the launcher window open
while using the editor. LAN mode is for a trusted private network where devices
can reach one another. Anyone who can reach the address can edit the shared cut
and queue clips.

1. Upload an image, describe the motion, choose the clip length and tap **Generate clip**.
2. Play the result in the Viewer and tap **Add to sequence** to append its picture and sound.
3. Pause or scrub to any frame and tap **Use frame as starting image** to continue from it. Write the next motion prompt and generate again.
4. Tap a sequence clip to move or remove it. Use **Play sequence** to preview the cut or **Export MP4** to save it as one file.

The upload accepts still JPEG, PNG, WebP and AVIF files up to 20 MiB and 64
megapixels. The editor keeps the uploaded file and makes a conditioning copy
up to 2048 pixels on its longest edge. HEIC/HEIF photos are converted to JPEG
on devices whose browsers can open them.

Generation uses the installed first-frame H3 workflow and the ComfyUI address
in `.local/worker.json`. Use `--worker http://WORKER-IP:8188` to set the worker for
this editor from the host PC. The phone only connects to the editor. Lengths
follow the workflow's 24 fps frame grid from 2 to 10 seconds. The 124-frame
default (5.17 seconds) is the live-verified length. The editor displays the
actual selected length and reports any mismatch returned by the worker.

The Clip Editor keeps images, jobs, clips and sequence revisions in
`.local/clip-editor`. The selected starting image and motion prompt are remembered
by each browser. Launch it once and use the printed address on every device.

### Draft with Local AI

Enable the local model API in Bionic under **Settings → Local Model API** and
use an installed Qwen model. Put its loopback API address and model ID in
`.local/clip-editor/local-ai.json`. For example, use the following with Bionic
running on port 1235. Use your own port and the ID from `/v1/models` if they differ.

```json
{
  "base_url": "http://127.0.0.1:1235/v1",
  "model": "qwen2.5-coder-3b-instruct"
}
```

In the Clip Editor, choose a starting image, enter a short direction in
**Motion prompt**, and click **Draft with Local AI**. The model sees the written
direction and selected duration. Review or edit the returned prompt and length,
then click **Generate clip** to send the starting image and prompt to H3.

## Open the creator studio

Double-click **`quickstart.bat`** in this folder, or run it from PowerShell:

```powershell
.\quickstart.bat
```

It checks Python/image/WebP/FFmpeg support, builds the interface when missing or
outdated, starts the local studio and opens your browser after the server is ready.
It reopens the existing `.local/studio` library, including imported scenes,
saved motion recipes, approvals and pilots. A second launch reopens that same
running studio. Keep the launcher window open; use **Ctrl+C** to stop it.
Server logs are saved in `.local/logs/`. Startup creates no new GPU requests;
the studio resumes polling previously submitted jobs as usual.

Python 3.11+ is required. The launcher can use installed Python or the existing
Codex runtime; set `LLR_PYTHON` to a particular `python.exe` if needed. If image
or video dependencies are missing, it creates an isolated `.local/venv` and
installs the dependencies declared in `pyproject.toml` there. First-time setup
needs internet access. Building the interface requires Node.js 20.19+ or 22.12+
with npm (the existing Codex Node runtime is also supported); an already current
build needs no Node process. No model downloads or cloud accounts are required.

Useful launcher options:

```powershell
.\quickstart.bat --check                 # Check/setup tools and build, then exit
.\quickstart.bat --rebuild               # Rebuild the interface and launch
.\quickstart.bat --no-browser            # Launch without opening another tab
.\quickstart.bat --port 8766             # Use another local port
.\quickstart.bat --data "D:\My LLR Library" # Explicitly select another working store
```

If port 8765 belongs to another service or library, the launcher reports the
conflict. An older studio started before the readiness endpoint was added must
be closed once before relaunching. For the existing lower-level runner:

```powershell
.\scripts\run.ps1 studio
```

Open [the local studio](http://127.0.0.1:8765). Keep the command running while
using the app. Restarting it reopens the same `.local/studio` library. Use
`studio --port 8766 --data PATH_TO_WORKING_STORE` for another local port/store.

1. **Import scene…:** import a PNG, JPEG or static WebP, up to 20 MB / 40 megapixels.
   Exact master bytes are copied; thumbnails are separate. Identical images
   select the existing scene instead of duplicating it.
2. **ComfyUI worker:** test/save the worker URL. The verified LAN endpoint is
   `http://192.168.1.168:8188`. Compatibility reports check the recovered graph.
3. **Create action:** describe a returning action, mark its area and
   preview the protected scene. Choose **Make first take**, or **Save for later**.
   Existing subjects reuse a saved area. The motion workspace plays takes,
   offers **Adjust motion area** without another render, and keeps technical
   settings folded away. Another take uses a fresh variation by default.
   See [`docs/GUIDED_MOTION.md`](docs/GUIDED_MOTION.md). Saved prompt IDs let
   polling resume without submitting again.
4. **Viewer:** play a take, compare it with the master and inspect first,
   middle and last frames. Approval requires a visual-check acknowledgement and
   start/end anchor labels. Rejection requires a reason. Both preserve media
   and append review history; only the latest approved revision is eligible.
5. **Timeline:** place an approved take on its subject's Motions track. Configure
   automatic idles in **Subject setup**, build/play the combined Canvas, then
   export/download the MP4, manifest and event log. Holds preserve each subject's
   preceding decoded exit frame. See [`docs/EDITOR.md`](docs/EDITOR.md).

The previous Scenes, motion, Review room and Pilot builder tools remain available
through **Library workspace**. Existing pilots and exports are preserved.

For the recovered Apartment Pilot, **Generate motion** now defaults to
**Recovered actor motion**. Choose an action to restore its actor crop, mask,
start/end poses, original direction, seed and duration. The eight recovered
presets include reader idles, page turn, window transitions and cat actions.
The original 768-square turbo eight-step graph is preserved separately under
`workflows/h3/production/`; the small full-scene smoke recipe remains available.

The current worker has the turbo LoRA but lacks the original FP16 video VAE.
The creator authorized an explicit **INT8 comparison variant** while waiting
for FP16. Choose the video VAE in the form; the chosen filename and difference
from the original template are recorded with the job. No missing model is
silently replaced. The VAE affects pose conditioning as well as decoding.

Production generation uploads exact independent first/last crops, saves owned
PNG frames, and composites them through the saved feathered mask over the
canonical background. It outputs a full-scene H.264 MP4 and a raw actor preview,
retaining original frames and lossless assembled boundary samples. Outside the
effective mask, lossless assembled pixels equal the canonical background.
The MP4 uses the recovered CRF15/slow, 24fps, BT.601 limited-range convention;
its compression is lossy. This is a reference-checked reconstruction of the old
compositor, not a claim of recovered original source code or exact palette
correction. See [`artifacts/motion-analysis/README.md`](artifacts/motion-analysis/README.md).

New production candidates open with **Compare with earlier take** in Review.
The shared play/pause/replay controls display the matched historical clip
beside the new take. Check both boundaries and the palette before approving.
The completed Reading Idle A test also has a labeled
[comparison video](artifacts/restored-motion-comparison/comparison.mp4) and
[enlarged actor samples](artifacts/restored-motion-comparison/actor-contact-sheet.png).
`python scripts/compare_motion.py --job-id ID --store .local/studio --output NEW_FOLDER`
creates this evidence for a completed matched test without submitting or
approving media. It refuses to replace an existing evidence folder.

The user-authorized import from `D:\LastLightRadioMedia` is complete: three
legacy scene stills, eight completed MP4 candidates with their recorded approvals,
and two final exports were copied/archived. A failed old render is retained as
history. The source database and assets were read without modification. The
generated reading-room still remains a separate noncanonical technical example.

The import archives primary media, masks, evidence, workflows, database records
and final exports. Regenerable raw-frame, benchmark and render-chunk caches stay
in the source folder. The exact scope and paths are recorded in
`.local/studio/legacy/IMPORT_ID/import_manifest.json`. Existing-library imports
are available under **ComfyUI worker** and deduplicate by database checksum.

For a fresh checkout, install the Python dependencies and build the interface:

```powershell
python -m pip install -e ".[media]"
npm ci --prefix frontend
npm run build --prefix frontend
.\scripts\run.ps1 studio
```

Python 3.11+ and a current Node.js release are required for that setup. The
`media` extra supplies FFmpeg for MP4 import/review; an installed `ffmpeg` or
`LLR_FFMPEG` executable path also works. This checkout has an isolated FFmpeg
package under `.local/vendor`. Runtime use of the built studio needs no Node
process. For frontend development, run `npm run dev --prefix frontend` alongside
the Python studio; Vite proxies `/api` to port 8765.

The server binds only to loopback. The browser talks to the local API, and the
Python worker talks to ComfyUI. All new working data stays under `.local/studio`
(SQLite registry, immutable masters/candidates, approval copies and records).
Back up that entire folder while the studio is stopped. Source media remains
independent of the working copy.

## Run from this source checkout

Requires Python 3.11+. Tested on Windows with Python 3.12.14.
The demo/check commands need no dependency installation; tests include Pillow.
In PowerShell, from this directory:

```powershell
.\scripts\run.ps1 demo
.\scripts\run.ps1 test
.\scripts\run.ps1 check
```

The runner finds `py`, installed Python, or the bundled Codex Python runtime.
Override it with `-Python 'C:\path\to\python.exe'` or `LLR_PYTHON` if necessary.
Equivalent commands for any supported Python installation:

```text
python -m last_light_radio demo --seed 7 --seconds 600 --output runs/demo
python -m unittest discover -s tests -v
python scripts/check.py
```

The offline fixture contains `SCENE_A`, `READER`, three `READ_IDLE` variants and
two `SIP_TEA` variants. These are **mock metadata**, not animated files or creator
approvals. The tiny PPM fixture is a checksum/storage test image. The generated
reading-room test illustration is separate under `assets/test_scene/`, with
its exact generation prompt and provenance. Both are noncanonical.

The demo prints paths to a standalone `schedule.html`, `episode_manifest.json`
and `event_log.md`. Open the HTML in a browser to inspect the schedule. Repeating
the same seed and inputs produces identical manifest/log content. Another seed
changes variant choices:

```powershell
.\scripts\run.ps1 demo --seed 8 --output runs/demo-seed8
```

Output stores contain separate `masters`, `candidates`, `approved`, `exports`,
`backups`, `records` and `manifests` directories. Master bytes are copied without
changing the source. Snapshot and output paths use content hashes and refuse
conflicting overwrites. On reopen, hashes expose externally modified assets.
The store stages and flushes writes before publishing them, so an interrupted
write does not leave a partial final master/snapshot. This is application-level
immutability, not a filesystem permission lock.

## H3 workflow and LAN connection

`workflows/h3/workflow_api.json` is the exact 11-node API graph recovered from a
successful job. Original history, raw-file hash and captured node definitions
are preserved beside it. It requests 384 x 480, 39 frames, 12 Euler steps and
animated WebP output at 24 fps. The original Mothman prompt is historical source
material, not the first Last Light Radio scene.

`workflows/h3/bindings.json` separately maps this graph's image, motion prompt,
seed and other controls. The creator confirmed use of this recovered mapping for
live generation on 2026-10-21; its `confirmed` flag now records that authorization.
No reusable adapter code assumes these particular node IDs. Previewing changes
deep-copies the template, checks input types and validates the edited graph.

```powershell
.\scripts\run.ps1 workflow
.\scripts\run.ps1 workflow --image LastLightRadio/test_still.png --prompt 'Gentle breathing, one blink, locked camera. Preserve all geometry and props.' --seed 7 --preview-output runs/h3_preview.json
.\scripts\run.ps1 probe --url http://192.168.1.168:8188 --save
.\scripts\run.ps1 probe
```

`workflow` is offline. A preview image name is only a proposed server path; the
image has not been uploaded. `probe` makes only GET requests to `/system_stats`
and `/object_info`. A successful `--save` writes the editable endpoint to the
ignored `.local/worker.json`; the endpoint is not hard-coded in source. No
network scan, queue clearing, model download, submission or interruption
is performed by these two commands. Required node classes being present does not prove model or
future generation readiness.

The recovered `SaveAnimatedWEBP` output convention is parsed explicitly as
`images` plus `animated` flags. Mock jobs exercise queueing, running, failure,
timeout, reconnect, ownership and success without pretending to create media.
The connection-only `ComfyClient` remains read-only. The separate
`LiveComfyClient` is used only by explicit live render commands.

## Submit and resume one live render

This command uploads a copy of the image, validates a prepared graph against
the worker's current node definitions, saves workflow/ownership snapshots and
submits exactly one GPU job. The default small H3 dimensions, length, FPS and
sampling settings remain those of the recovered workflow.

```powershell
.\scripts\run.ps1 render --image assets/test_scene/test_still.png --prompt 'Gentle breathing and one blink. Locked camera; preserve book, hands, cup, cat and room geometry. Return to the initial pose.' --seed 7 --output runs/h3-test
.\scripts\run.ps1 job --job-id LOCAL_JOB_ID_FROM_RENDER --output runs/h3-test --wait-seconds 45
```

`render` creates a new job each time it is explicitly invoked. Use `job` with
the printed **local job ID** to continue polling an existing render. It resumes
from the recorded worker URL and prompt ID across process restarts, and never
uploads or submits again. It can be repeated after a connection/read/download
failure. A bounded wait expiring does not cancel the GPU job. There is no
automatic POST retry: an uncertain submission is recorded for reconciliation
instead of risking a duplicate render.

Requests, workflow and node-definition snapshots, device statistics and status
events are preserved under the output store's `records/` tree. Uploaded filenames
and output prefixes use a unique local job subfolder and never request overwrite.
Completed outputs go to `candidates/LOCAL_JOB_ID/` with byte checksums, container
metadata and a `candidate.json` provenance record. They remain unapproved and
cannot silently become production clips. Resume verifies the master and any
already-downloaded candidate checksums. No live client method clears the shared
queue or interrupts another job.

The WebP inspector reports encoded frame count, millisecond durations and
effective FPS separately from requested FPS. It checks container structure;
full pixel decoding and head/tail visual review are separate validation steps.
Before/after device snapshots are retained, but peak VRAM is explicitly unknown.
The studio additionally decodes every new WebP frame and prepares three review
samples. Imported MP4s retain their historical timing metadata and are sampled
with FFmpeg; fresh MP4 approval performs a full video decode.

The first authorized smoke test completed on 2026-10-21: **384 x 480, 39 decoded
frames, 1.599 seconds**, with **35.925 seconds** recorded server execution using
cached model-loader nodes. WebP stored 41 ms per frame, so effective playback is
24.39024 fps versus requested 24 fps. The original still and recovered workflow
checksums did not change. See `workflows/h3/LIVE_TEST.md` for saved output paths
and quality notes; the result is an unapproved candidate with some head/face drift.

Optional pixel QA uses Pillow (available in the Codex bundled Python runtime):

```text
python scripts/review_webp.py PATH_TO_DOWNLOADED_WEBP
```

It decodes all frames and writes `review/validation.json`, individual sample
frames and a head/middle/tail contact sheet without changing the candidate.

API references: [ComfyUI routes](https://docs.comfy.org/development/comfyui-server/comms_routes)
and [execution messages](https://docs.comfy.org/development/comfyui-server/comms_messages).

## Data and scheduling rules

`fixtures/demo_project.json` is the executable contract example. Records include
stable world/location/entity IDs, canon revision, scene/master hash, actor and
prop state, visual anchors, behavior rules, variants and their review status,
draft episode settings, and proposed canon patches. Paths are portable and
relative to the project root. The first slice supports one draft episode per
project file. Drafting never changes world facts or commits canon patches.

Every clip occupies the entire picture lane. Actor/prop locks are recorded,
and conservative sequential scheduling prevents overlaps. Eligibility checks
presence, semantic state, visual entry anchor, approval, FPS, time windows,
cooldown and minimum gap. Cooldown/gap count from a behavior's previous end.
Weights select behaviors and variants; the last variant is avoided when an
alternative is eligible. Clips are never shortened or retimed to fit.

Fallback holds retain the actual current frame/anchor, including a previous
clip's last frame. An unsafe anchor requires an approved compatible transition
or a visible failure; it never silently snaps back to the master. Every skip
and fallback has a reason code. The manifest pins seed, timebase, world revision,
master, variants, provenance and input hash. The mock CLI manifest remains
`renderable=false`. The studio's separate pilot manifest becomes renderable
after real-media hash, full-decode and timing validation.

## Verification and next work

`unittest` checks deterministic replay, seed variety, exact length, approvals,
state/anchor compatibility, cooldowns, windows, recovery, canon preservation,
master checksums, interrupted writes, portability, CLI integration, workflow
bindings, the mock API, studio persistence, non-destructive legacy import,
review revisions, API origin checks and media byte ranges. Tests use fake GPU
clients and one temporary loopback HTTP server; they never need ComfyUI. The baseline `check` command
checks Python syntax, tabs, trailing whitespace and final newlines; a full style
formatter/type checker is not installed. A symlink-escape test skips when Windows
does not grant symlink creation permission.

Verified on 2026-10-21 after production restoration: 101 tests ran, 100 passed and one OS-permission symlink
test skipped; Python baseline checks and the strict TypeScript/production build
passed. The browser import → live H3 generation → review → persisted decision
flow was exercised, along with playback of an imported MP4. Restored test
`7f374713fdb64319a5fe039bc1017d79` completed 124 frames at 24fps using the old
Reading Idle A seed and poses plus the authorized INT8 video VAE. The app plays
it beside the earlier approved take; the new candidate remains unapproved. See
[`docs/STUDIO_VERIFICATION.md`](docs/STUDIO_VERIFICATION.md) for evidence.

Scene setup now authors reusable motion recipes for imported images: draw an
actor region, preview a feathered mask and context crop, choose matching poses,
then save and generate with the proven H3 pipeline. Saved revisions preserve
existing takes. See [`docs/MOTION_RECIPES.md`](docs/MOTION_RECIPES.md) for the
creator workflow, image geometry, validation and current limits.

The approved-library scheduler bridge and ten-minute silent export are verified;
the first new MP4 is in `artifacts/pilot-20261021/`. Next work is music/ambience,
broader behavior/rule authoring and shared-world continuity. The two imported
final exports remain separate historical artifacts.

`PROJECT_TRUTHS.md`, `HANDOFF_PLAN.md`, `MVP_TASKLIST.md` and `AGENTS.md` were
copied from the supplied handoff. Their original Desktop copies and all recovered
H3 source artifacts remain untouched. This directory was not a Git repository
at inventory time; no remote or commit was created.

### Audio milestone (2026-11-13)
The editor now imports reviewed WAV sources and saves production/music clips with trim, gain and fades. Choose **Viewer > Audio**, approve the source, place it, apply changes, and export a mixed movie. Existing sequences without audio remain silent. Canvas playback is still picture-only; use source audition or the exported movie for sound. See docs/EDITOR.md for limits and verification.
