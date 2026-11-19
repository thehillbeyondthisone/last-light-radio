# Local-only Mara video operator: start here
Version 2026-11-15. This is a reproducible experiment handoff, not a promise of spatially correct generation. Read this file first; load ONE workflow at a time. Keep a short state ledger outside your chat context.

## Mission and authority
Use an on-device LLM to plan/control the user's existing local H3/ComfyUI generation. Reproduce the useful Mara coffee-down / rear-door exit sequence without cloud inference. Do not start any GPU job just by reading this file. Coordinate the GPU with the current operator first. Preserve originals, FABLE footage, existing editor sequences and UI code. Outputs are candidates, not automatically approved production takes.
This is a user-requested local-controller experiment, separate from the deterministic Last Light Radio episode scheduler. Do not replace that scheduler with a live LLM. Do not modify project canon or UI to conduct this test.

## What actually made the cohesive shot
It was NOT one long generation and NOT an explicit 3D scene:
- Five local H3 image-to-video outputs, mostly sharing the same camera direction.
- A01 and A02 both started from the original image.
- A03 started from the observed mug-down image after A02.
- A04 started from the observed at-rear-doors image after A03.
- A05 started from the observed outside-rear image after A04.
- These were trimmed into a 32.5-second cut. Endpoint images carry appearance and state, not persistent geometry or motion history.
- A04's prompt asked her to stay inside, but the result exited. A05 was correctly rewritten to match the ACTUAL outside state. Do not blindly chain the planned state.
The smooth impression does not prove continuity under a reverse angle. The user explicitly wants that tested separately.

## Machines, paths and prerequisites
Toast repository: C:\Users\thisi\OneDrive\Documents\repos\last-light-radio
This package: docs\local-llm-mara-20261115
Harbinger source: C:\Users\thefo\Documents\film-pipeline-tests\2026-11-15-van-character\action-v2
Harbinger Comfy root: C:\Users\thefo\AppData\Local\Comfy-Desktop\ComfyUI-Shared
Comfy on Harbinger: http://127.0.0.1:8188
Comfy from Toast: http://192.168.1.168:8188 (verified read-only on 2026-11-15; LAN addresses can change).
Harbinger FFmpeg: C:\dev\ffmpeg\bin\ffmpeg.exe
Do not expose this unauthenticated LAN service publicly. Do not restart it or clear its queue.
Required controller: a LOCAL LLM runtime with a trusted file/HTTP/shell tool bridge. A chat-only model cannot execute these commands by itself. No particular local orchestration model/runtime has been verified in this package. The Qwen model below is H3's encoder, NOT the orchestration agent.
Historical video inference was local; historical planning was by dot. Replacing planning/control with a local model is the new experiment, not an already proven all-local run.

## Exact pinned generation recipe
The five adjacent A01..A05.workflow.json files are API-format graphs recovered from the actual action-v2 renders. They contain the exact complete prompts; do not reconstruct them from prose.
Common recipe:
- MiniMaxH3ImageToVideo, 672 x 384, 24 fps.
- A01..A04: 192 frames / 8 seconds. A05: 144 frames / 6 seconds.
- Seeds A01..A05: 2026111701 through 2026111705.
- res_multistep sampler, simple scheduler, 8 steps, denoise 1.0.
- Turbo LoRA strength 1.0.
- Video and generated audio latents separated, decoded, and muxed. No external audio guide in this recipe. Prompted sound effects are not independently verified audio facts.
Models (must exist exactly; do not substitute silently):
minimax_h3_fl2va_pruned_int8_convrot.safetensors
qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
minimax_h3_video_vae_int8_convrot.safetensors
minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
minimax_h3_audio_vae_fp32.safetensors

Graph bindings: node6 prompt/width/height/length; node8 noise_seed; node18 LoadImage filename; node14 output prefix. Keep the other graph links intact. Node13 fps=24. Node14 saves H264 MP4 CRF20. These bindings apply only to these archived graphs, not arbitrary newer workflows.

## Visual references and immutable state
Reference names already present in Harbinger Comfy input at inspection:
A01/A02: van-mara-reference-20261115.png
A03: mara-mug-down.png
A04: mara-at-rear-doors.png
A05: mara-outside-rear.png
Resolve under Comfy root\input. Never overwrite them. Hash before use and record that hash with each job. On another installation, transfer these exact files before attempting reproduction; prose descriptions are NOT replacements.
Inspect each image using local vision before planning. Main identity: thirty-four-year-old woman, chestnut curls, rust headband, silver earrings, ochre shirt, denim overalls. In the original view: rectangular window LEFT, cedar counter/turquoise kettle RIGHT, rear double doors behind; cream mug initially in hands. Screen directions are camera-relative, not a universal floor plan.
A different angle requires a validated reference showing the same place from that direction, not simply a prompt saying "another camper." Keep location identity, furniture relationships, mug location, wardrobe, door state, and exterior direction in a versioned reference/state record. Unseen sides are unknown, not permission to invent canon.
This is image conditioning, not a calibrated multi-view reconstruction, scene mesh, Gaussian splat, or spatial outpainting system. A reference board reduces ambiguity; it does not enforce 3D consistency.

## Operational protocol (no GPU work was launched to make this package)
1. Read the selected workflow and reference. Inspect latest queue/history and check with whoever owns current renders. A momentarily empty queue does not mean a separate worker won't submit next.
2. Choose a NEW experiment directory and unique output prefix. Copy workflow; never edit archived originals. Record one intended variable, source workflow hash, image hash, model/seed/fps/frames and expected action.
3. Validate required node classes through GET /object_info and model names in their loader input choices. Fetch reference via /view as a read-only existence check. Check /system_stats.
4. Submit only with explicit authorization for this experiment and GPU availability. Persist the response prompt_id IMMEDIATELY.
5. Poll GET /history/{prompt_id}; log status. If connection drops or polling times out, resume this ID. NEVER blindly resubmit a timed-out POST: first reconcile queue/history to avoid duplicates.
6. A successful HTTP response or a disappearing queue item is not success. Require history status success, output metadata, nonempty video, full decode, expected duration/resolution, and visual/audio review.
7. Download the saved output using the history's filename/subfolder/type. Keep it under your candidate directory; reject path traversal. Preserve workflow, request receipt, full history and SHA256.
8. Stop/report errors. Do not cancel somebody else's prompt, clear queues, restart services, install replacements or change settings to conceal a failure.

### Read-only PowerShell preflight (Toast)
```powershell
$base = 'http://192.168.1.168:8188'
Invoke-RestMethod "$base/system_stats"
Invoke-RestMethod "$base/queue"
$info = Invoke-RestMethod "$base/object_info"
$g = Get-Content '.\A02.workflow.json' -Raw | ConvertFrom-Json
foreach ($n in $g.PSObject.Properties.Value) {
  if (-not $info.PSObject.Properties[$n.class_type]) { throw "Missing node: $($n.class_type)" }
}
# Read loader entries in $info to verify model choices; do not guess replacements.
```

### Submit example (NOT automatic; changes external GPU queue)
Use PowerShell 7. Run only after preflight and GPU coordination. Run from this package folder, with a new candidate directory:
```powershell
$base = 'http://192.168.1.168:8188'
$run = 'local-mara-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$out = Join-Path $PWD $run
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
$g = Get-Content '.\A02.workflow.json' -Raw | ConvertFrom-Json
$g.'14'.inputs.filename_prefix = "$run/A02"
$g | ConvertTo-Json -Depth 60 | Set-Content (Join-Path $out 'workflow.json') -Encoding utf8
$q = Invoke-RestMethod "$base/queue"
if ($q.queue_running.Count -or $q.queue_pending.Count) { throw 'GPU queue occupied; coordinate, do not clear it.' }
$body = @{prompt=$g} | ConvertTo-Json -Depth 60
# Exactly ONE POST. A network failure here is ambiguous; inspect queue/history before retrying.
$r = Invoke-RestMethod "$base/prompt" -Method Post -ContentType 'application/json' -Body $body
$r | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $out 'receipt.json') -Encoding utf8
if (-not $r.prompt_id) { throw 'No prompt ID; inspect receipt and node errors.' }
$id = $r.prompt_id
# Poll this ID without submitting again:
$h = Invoke-RestMethod "$base/history/$id"
$h | ConvertTo-Json -Depth 60 | Set-Content (Join-Path $out 'history.json') -Encoding utf8
```
Repeat the history GET at a modest interval, not the submit block. Until history contains your ID, the job may still be running. In the observed version, successful output was under history[id].outputs['14'].images[0], even though it is a video. Inspect rather than assuming all plugin versions use this structure.
Download URL shape:
GET /view?filename=<URL-encoded filename>&subfolder=<URL-encoded subfolder>&type=output
Reference URL shape:
GET /view?filename=van-mara-reference-20261115.png&type=input
Do not send image/video content to a cloud model for the all-local test. A local visual-capable model or the human must assess frames.

## Reproduce versus continue
Reproduction uses the archived references unchanged; it tests exact old inputs.
A NEW chain must extract a frame from the NEW previous output and inspect it. Reusing the old downstream references after generating a new preceding take is not a genuine continuation test.
With locally installed FFmpeg, select the intended boundary frame by frame number:
ffmpeg -i candidate.mp4 -vf "select=eq(n\,FRAME_INDEX)" -frames:v 1 new-reference.png
Use an explicit new filename, verify output, and upload/copy it to Comfy input under a new name. The standard multipart POST /upload/image can accept image plus type=input and overwrite=false, but that upload step was not exercised in this handoff. Confirm server response name and reference hash before pointing LoadImage at it.
One endpoint has no velocity history. A visual match may still jump in motion. A video-tail conditioning experiment would be a DIFFERENT workflow; do not claim these five graphs use it.

## Editing: action and pace, not end-to-end concatenation
Observed source trim manifest (seconds, out exclusive):
A01 1.00..8.00, 7.00s: notice window/man.
A02 2.50..7.25, 4.75s: place mug and begin rise.
A03 0.00..7.50, 7.50s: move to rear.
A04 0.00..7.50, 7.50s: open doors/exit as actually rendered.
A05 0.00..5.75, 5.75s: outside investigation.
TRT 32.50s. Do not stretch this mechanically to 50s. This is useful master coverage, not the final multi-angle scene. Duration/fps metadata is evidence of timing, not proof of physical action.
Review real mug contact/release, empty hands, walking, door swing, threshold crossing, and screen direction. Trim on compatible body phase and avoid repeated actions at joins. Listen at cuts; generated ambience may jump. Do not claim sound is seamless without listening.
For new coverage, establish camera position, direction and eyeline relative to the same van. A tighter crop is not a new camera direction.

## QA gates and experiment ledger
Full decode: ffmpeg -v error -i candidate.mp4 -f null -
Probe with local ffprobe if available: streams, codec, width/height, frame count/fps, duration, audio presence. Preview full sequence, not only first/last images. Inspect cut-adjacent frames plus every key action.
Record:
experiment_id, input image/hash, workflow/hash, seed, model names, prompt, width/height/fps/frames, output/hash, prompt_id, elapsed time, planned start/end state, OBSERVED start/end state, selected in/out, failures, candidate/approved status.
Keep factual state separate from interpretation. "Door open in end frame" is observable; "perfect coherent 3D van" is not. Facial identity, kettle/bed/aisle geometry and exterior geography can drift despite successful execution.
For one-variable tests change one thing, retain a baseline and identical comparison passage. Do not label a winner by metadata alone. Preserve failed results and reasons.

## Context budget for a small local model
Always keep: this mission, current shot's exact graph/prompt, chosen reference, compact state ledger, tool contract and last receipt.
Retrieve only when needed: other shot prompts, histories, detailed model information, older experiments. Do not paste the entire project history into every turn.
After each shot, write a short checkpoint: completed artifact, prompt_id, actual state, next action, blockers. Before resuming, read checkpoint and query that ID. Do not rely on conversation memory.
Suggested local controller opening prompt:
"Read START_HERE.md. Operate only through local files and the specified LAN ComfyUI. First perform read-only preflight and summarize the exact existing A02 recipe and its reference. Do not submit yet. Explain the five-shot construction and how you will keep actual state, receipts and review separate from assumptions. Then execute only the explicitly authorized experiment, with no duplicate jobs and no production/UI changes."

## Verification and limitations of this package
Source graphs and input filenames were inspected on Harbinger. Toast reached /queue read-only. No new inference, model download, reference regeneration, UI edit or timeline replacement was performed for this documentation task. Commands are examples, not a claim that a full local-agent replay has been run. LAN service availability and model files must be rechecked before future execution.
