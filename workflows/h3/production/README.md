# Recovered actor-motion recipe

`workflow_api.json` is a byte-for-byte copy of earlier candidate 1's workflow,
SHA-256 `bffa313797075b91bda1e7bca76890a1599058b13b9c77edfc586ca1b609dadf`.
The original database, media and workflow remain unchanged on D:.
`bindings.json` maps the actual recovered node inputs, independently of the
preserved graph. The creator authorized restoration and a comparison test.

## Prepared inputs and states

The imported working-store snapshot supplies eight immutable presets, including
the original prompts, seeds, first/last state references, mask and crop:

| Actor | Crop in the 1920 × 1080 master | States |
| --- | --- | --- |
| Reader | x=200, y=230, 768 × 768 | reading, looking_outside |
| Cat | x=430, y=190, 768 × 768 | resting |

Separate first and last PNG crops are prepared without resizing or modifying
their source plates. A same-state action uses identical poses; a transition
uses different ones. Both are uploaded into a unique owned job subfolder.
The full-scene mask is used by the local compositor after H3 generation; it is
not a mask-conditioning input to this workflow.

## Model and sampling recipe

- Diffusion: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`.
- Text encoder: `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`.
- Turbo LoRA: `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`, strength 1.
- Original video VAE: `minimax_h3_video_vae_fp16.safetensors`.
- BasicGuider, RandomNoise, eight simple-schedule steps, `res_multistep`, denoise 1.
- 768 × 768, normally 124 frames at 24fps (5.167s). The successful page-turn
  preset uses the recorded 90-frame fallback (3.75s).
- VAEDecode → SaveImage PNG sequence. Actual generated endpoints are retained.

The current worker lacks the original FP16 video VAE. The creator explicitly
authorized testing `minimax_h3_video_vae_int8_convrot.safetensors` while waiting
for FP16. This is an execution override, never a change to the recovered
template. Requests and candidates record `execution_variant` and the selected
VAE. A missing model fails preflight rather than selecting an automatic fallback.

## Assembly and review

Each PNG must match the owned output prefix, expected frame count, RGB mode and
crop dimensions. Downloaded frames have checksums and can resume independently
of submission. The engine requires the executed history graph to match the
submitted workflow. Interrupted polling/download/assembly never submits again.

The recovered full-scene grayscale mask is cropped to the actor rectangle.
Its feathered alpha blends the generated crop into the fixed canonical reading
background, including for window-state actions. Reader-mask overflow beyond
the crop is clipped. Direct RGB assembly guarantees unchanged pixels outside
the effective mask before lossy MP4 encoding.

The encoder uses libx264, slow preset, CRF15, yuv420p, and explicit BT.601
limited-range conversion, based on old-file bitstream and pixel analysis.
The exact earlier color-correction implementation is unavailable. A full control
reassembly of old candidate 1 is close to the approved v2 output, with sampled
whole-frame mean RGB differences around 1.1/255 after encoding; it is not exact.
No undocumented fade, opacity attenuation or endpoint replacement is invented.

Working-store artifacts include prepared input crops, mask, exact request and
workflow, worker history, raw PNGs and their manifest, raw crop MP4, assembled
full-scene MP4, and lossless first/middle/last PNGs. Review offers the matched
historical take with shared playback controls. Candidates remain unapproved
until the creator explicitly approves them.
