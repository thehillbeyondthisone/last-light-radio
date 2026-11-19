# Qwen local video director: executable field guide
2026-11-17 | Toast controller -> Harbinger ComfyUI | documentation, not a render request

## Read this first
You are a local language-model operator, not the video model. Turn the user's idea into a small shot plan, use the existing H3 graph, submit once, inspect actual footage, and edit useful moments. Do not invent executable APIs, node IDs, successful renders, unseen scenery, or approvals. No cloud inference is required by the command path below. The model needs a trusted local file/shell/HTTP tool bridge. A chat-only Qwen can write a plan but cannot execute it. Local visual assessment requires a vision-capable local model or human review; textual metadata cannot judge acting or lip sync.

Start with ONE SD shot. Preserve all source media, old takes, production sequences and UI code. Coordinate with the current GPU operator before submitting: an empty queue does not prove nobody is about to use it. Never clear queues, interrupt jobs, restart services or change models to get around a conflict. Existing Astrid tests share this GPU.

This is the user's experimental creative controller, NOT a replacement for the repository's deterministic Last Light Radio episode scheduler. Read repository AGENTS.md before code changes. This guide does not authorize changing that architecture.

## 1. Exact local setup
Toast repository: `C:\Users\thisi\OneDrive\Documents\repos\last-light-radio`
Archived working package: `docs\local-llm-mara-20261115`
Use `comfyui_client_safe.py`. NEVER use sibling `comfyui_client.py`: its old submit path could send a job and then lose the receipt.
Harbinger Comfy root: `C:\Users\thefo\AppData\Local\Comfy-Desktop\ComfyUI-Shared`
Harbinger source renders: `C:\Users\thefo\Documents\film-pipeline-tests\2026-11-15-van-character\action-v2`
Comfy on Harbinger: `http://127.0.0.1:8188`
Comfy from Toast: `http://192.168.1.168:8188` (rechecked read-only today; address can change).
Toast worker config: `.local\worker.json`. Read it if the LAN address stops working. Do not assume localhost on Toast reaches Harbinger or expose Comfy to the Internet.

On Toast use the explicit installed interpreter below. Bare `python` currently resolves to a nonworking WindowsApps alias. No pip installation is needed for this stdlib-only client.

```powershell
$repo = 'C:\Users\thisi\OneDrive\Documents\repos\last-light-radio'
$py = 'C:\Users\thisi\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe'
$pkg = Join-Path $repo 'docs\local-llm-mara-20261115'
$client = Join-Path $pkg 'comfyui_client_safe.py'
$base = 'http://192.168.1.168:8188'
& $py --version
& $py -B $client --help
```

## 2. Smallest useful reproduction
The archived A03 graph makes Mara, whose mug is already down, rise and move toward the rear doors. It is a reproducible baseline, not an Astrid workflow. Changing the prompt to Astrid while retaining Mara's image is NOT character replacement.

Read-only preflight (no queue mutation):
```powershell
$graph = Join-Path $pkg 'A03.workflow.json'
& $py -B $client --base $base preflight $graph
if ($LASTEXITCODE -ne 0) { throw 'Resolve preflight problems before proceeding.' }
```
Checks installed classes, literal loader/image choices, system/queue and reference hashes. A model-list/schema check is not output quality validation.

After the user has authorized the experiment and GPU ownership is settled, prepare a NEW local directory. Preparation writes files only; it does not render:
```powershell
$run = Join-Path $repo ('artifacts\qwen-local-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $py -B $client --base $base prepare $graph $run --shot S01 `
  --variable 'Exact A03 baseline replay; unique output prefix only' `
  --planned-start 'Mug on counter; Mara has empty hands' `
  --planned-end 'Mara at closed rear doors, reaching for latch'
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; inspect output.' }
```
Review `$run\workflow.json` and `$run\experiment.json` before submission. Preserve their hashes.

Render once, only after coordination:
```powershell
& $py -B $client --base $base submit $run --confirm
# Exit 3 means ambiguous submission. Do NOT submit again; use reconcile.
& $py -B $client --base $base poll $run --wait --interval 20 --timeout 1800
# Only after history confirms successful completion:
& $py -B $client --base $base download $run
```
Run these separately, inspect exit codes between them. A timeout is not cancellation. To recover after interruption:
```powershell
& $py -B $client --base $base reconcile $run
& $py -B $client --base $base poll $run --wait
```
The client writes durable receipts/history and refuses repeat submission for the same run directory. Never create a second directory to bypass that guard. Reconcile queue/history by unique output prefix after an ambiguous POST. If reconciliation finds nothing but the submission outcome is still uncertain, stop and investigate rather than assuming failure.

## 3. What this graph actually does
Use the full API JSON beside this guide, not a screenshot of a Comfy workflow. The graphs live in the ARCHIVED PACKAGE above, not this guide's folder.

| Setting | Archived A01-A05 recipe |
|---|---|
| Main node | MiniMaxH3ImageToVideo, first-frame conditioning |
| Size / FPS | 672 x 384 / 24 |
| Duration | A01-A04:192 frames,8s; A05:144 frames,6s |
| Sampler / scheduler | res_multistep / simple |
| Steps / denoise | 8 / 1.0 |
| Turbo LoRA strength | 1.0 |
| Seeds | A01..A05 =2026111701..2026111705 |
| Audio | H3 generates audio; no external singing guide in these graphs |

Exact loader filenames:
- minimax_h3_fl2va_pruned_int8_convrot.safetensors
- qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
- minimax_h3_video_vae_int8_convrot.safetensors
- minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
- minimax_h3_audio_vae_fp32.safetensors

The qwen3vl filename above is H3's text/vision encoder, NOT your local directing agent. Do not replace it with the controller model.

Bindings ONLY for these archived graphs: node6 `prompt`, `width`, `height`, `length`; node8 `noise_seed`; node18 `image`; node13 fps24; node14 output prefix. Leave decoder, audio/video latent separation, mux and connections intact. For a new graph, rediscover bindings; do not reuse these numbers blindly.

To change one literal input at prepare time, add e.g. `--set '8.noise_seed=2026111801'`. For a new prompt held in `$prompt`, add `--set "6.prompt=$prompt"`. For a verified new first frame use `--set '18.image=unique-existing-input.png'`. The client refuses rewiring graph links. Run preflight on the prepared graph too. Use the known 8s/6s lengths first; don't assume every integer frame count is model-compatible. SD success does not guarantee native HD success, especially lip sync.

## 4. Direct a shot, not a vague mood
Before generating, write this compact contract:
- PURPOSE: what new story information the audience learns.
- START: observed body/prop/door positions in the input image.
- ACTION: one clear physical action, or a short causal chain the duration can show.
- END: visible completion state that can be checked.
- CAMERA: position, viewing direction, framing, movement or locked camera.
- INVARIANTS: identity, wardrobe, object locations and lighting to preserve.
- SOUND: intended dialogue/ambience; generated sounds remain unverified until heard.
- EDIT USE: the moment the editor needs, with handles before/after.

Example prompt structure, grounded in an inspected matching frame:
"Continue from this exact frame. The mug is already resting on the counter; it stays there. With empty hands, Mara rises, turns toward the closed rear doors, and walks down the aisle. End with her standing at the doors, hand reaching for the latch, doors still closed. Camera stays behind her, following gently. Preserve her clothing, face, cabinet layout, kettle and windows. Natural purposeful movement. Quiet footsteps and cloth sounds. No speech, music, cuts or titles."

Do not demand a completely new angle and many complex actions from an incompatible first frame. First create/validate a matching new-angle still. Prompt constraints are requests, not physical guarantees.

For a simple scene, plan 3 complementary views: master establishes the event; insert/POV reveals what caused it; reaction/action shot advances the decision. A tighter crop of the master is not a reverse angle. Define camera location, sightline, eyeline and screen direction against the SAME room. Use draft geography for unseen regions, never claim it is observed.

## 5. Continuity: reproduce versus genuinely continue
The admired 32.5s Mara sequence was FIVE trimmed generations, not one long model run:
A01/A02 original reference -> A03 mug-down reference -> A04 at-rear-doors -> A05 outside-rear.
A04 exited despite a prompt to remain inside. A05 was rewritten from its ACTUAL end state. This is the central lesson: observe, update state, then continue.

Existing immutable input names: `van-mara-reference-20261115.png`, `mara-mug-down.png`, `mara-at-rear-doors.png`, `mara-outside-rear.png`. Preflight hashes them.
Replaying archived downstream images tests reproduction. A new chain must extract a frame from the NEW prior take. Pick the useful action boundary, not blindly the final frame. Preserve source, write unique PNG, inspect it, upload under unique input name with overwrite disabled, and verify the returned filename/hash before using it.

On Harbinger FFmpeg is `C:\dev\ffmpeg\bin\ffmpeg.exe`. Example frame extraction (replace FRAME_INDEX with a reviewed integer):
`ffmpeg -i candidate.mp4 -vf "select=eq(n\,FRAME_INDEX)" -frames:v 1 unique-next-reference.png`
Resolve FFmpeg locally before running on Toast; do not assume the Harbinger path exists there. Standard Comfy upload is multipart POST `/upload/image`, fields `image`, `type=input`, `overwrite=false`. The safe client does not implement upload. Use a verified local bridge/editor image import or provide a tested uploader; do not pretend a local Toast filename is already a Harbinger input.

A still carries appearance/state, not velocity, persistent 3D geometry or hidden surfaces. Video-tail continuation is a different workflow. Do not claim these graphs use it.

## 6. Reusable character/location references and editor boundary
The desired system pins approved character appearance, named location views and prop references to each shot. Keep identity sheets separate from location geometry; label images by role, version and checksum. A generated sheet is a candidate until reviewed. Preserve unknowns and record which features are actually visible.

Production editor: Toast `http://127.0.0.1:8769/`.
Isolated new multi-reference build: Toast `http://127.0.0.1:8771/`, separate test data. It is NOT the production editor. Do not restart or deploy over Claude's UI work.
Read `docs\PRODUCTION_LIBRARY_MULTIREF_2026-11-17.md` before using that experimental route. It supports 1-9 ordered references and Picture N roles through MiniMaxH3ReferenceToVideo, with video VAE connected. Save shot plan -> Prepare generation -> preflight -> Generate is the intended lineage path; direct unplanned requests lack full registry revision lineage. Never mix reference-images mode with first/last-frame or continuation mode.

IMPORTANT: installed FL2VA/Turbo8 weights are being reused experimentally; native REF2VA weights were not present at this checkpoint. API wiring success is not proof of multiview consistency. Astrid testing is separately coordinated. The current portrait/reference sheet includes cloud-created inputs; using them with local video inference is NOT a fully local asset-creation pipeline. For an all-local demonstration supply locally created or user-provided canonical images and document their origin.

## 7. Verify and edit before calling it finished
Require successful history, nonempty downloaded file, expected frame count/FPS/dimensions, full decode, and visual/audio review. A queue item disappearing is not success. Use locally available ffprobe and FFmpeg:
`ffprobe -v error -show_streams -show_format -of json candidate.mp4`
`ffmpeg -v error -i candidate.mp4 -f null -`

Watch the full take and listen. Check face/wardrobe, hands, mug release/contact, doors, actual travel, furniture and window positions. Inspect beginning, middle, end and action boundaries. Don't score identity or sync from file metadata. If local vision/audio review is unavailable, say "technical checks passed, visual/audio review pending."

Trim on action and story pace; don't concatenate everything end-to-end. The historical Mara trim was A01 1..8s; A02 2.5..7.25; A03 0..7.5; A04 0..7.5; A05 0..5.75 =32.5s. These are evidence for those old takes, NOT universal trim points. New takes need new reviewed trims. Avoid restarting actions, repeated pauses, flipped eyelines and ambience pops. Preserve a candidate cut separately; do not replace approved sequences without authorization.

## 8. Learn without burning the GPU
Hold reference, seed, duration, audio, resolution and prompt fixed except the ONE variable under test. Keep baseline and candidate, compare matching passages with labels. Never conclude that a higher resolution is automatically better or that mouth-opening metrics prove syllable alignment. FABLE showed good SD sync could fail at HD; this remains an observed limitation, not a solved causal explanation.

Keep a small persistent checkpoint after every step:
```json
{"experiment":"unique id","stage":"prepared|submitted|complete|reviewed|blocked","prompt_id":null,"workflow_path":"...","reference_sha256":"...","one_variable":"...","planned_start":"...","observed_end":"unknown until review","output_path":null,"selected_in_out":null,"quality_status":"candidate","next_action":"...","blocker":null}
```
Use the safe client's experiment.json plus a separate director-notes.json, not an incompatible rewrite of its receipt schema. On resume, read checkpoint and reconcile the saved job before doing anything else. Keep only current shot, canon summary, tool contract and receipt in Qwen context; retrieve previous shots when needed. Do not load entire logs/object_info/media metadata into every prompt.

## 9. Paste this into local Qwen
"Read docs/local-qwen-video-director/START_HERE.md. Work only through local files and the configured LAN ComfyUI. First perform read-only setup/preflight, report the exact recipe and GPU occupancy, and propose one small shot with start/action/end/camera/invariants. Do not render until current GPU ownership is confirmed. Use comfyui_client_safe.py, preserve receipts, never resubmit an ambiguous job, and verify actual footage before planning a continuation. Keep director-notes.json checkpoints. Outputs are candidates. Do not modify the production editor, scheduler, models or approved sequences. Report what was actually tested and what still needs human review."

## Verification scope of this document
Written from the actual archived graphs, safe client code/CLI, CLIENT_NOTE.md and current multi-reference checkpoint. Explicit Toast Python3.11.15 and CLI help executed successfully; LAN /queue returned an active job on 2026-11-17. No render, upload, cancellation, service restart, model installation or UI change was performed for this documentation. A complete Qwen-driven autonomous replay has NOT been verified. The older client's offline tests are documented as20/20; that does not prove an end-to-end local-agent run. Read-only preflight outcome is recorded in VERIFICATION.md beside this file.
