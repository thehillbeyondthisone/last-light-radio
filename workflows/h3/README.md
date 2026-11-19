# Recovered MiniMax H3 workflow

Retrieved on 2026-10-21 from the completed successful ComfyUI job
`ee74331c-af0a-499c-a75a-8b011196f397` at `http://192.168.1.168:8188`.
No new generation was submitted.

## Files

- `workflow_api.json`: the executed 11-node API-format prompt graph.
- `source_history.json`: the original response from `/history/{prompt_id}`.
- `node_definitions.json`: the server's current definitions for the referenced node classes.
- `provenance.json`: retrieval details, workflow SHA-256, execution status and output reference.

The history contains no editor workflow/layout (`extra_pnginfo.workflow`), so
there is no recovered UI-format workflow. The API graph retains all executed
inputs and connections.

## Observed bindings

These IDs describe this recovered graph only. An adapter must inspect each
imported workflow instead of assuming all H3 workflows use these IDs.

| Purpose | Node | Input |
| --- | --- | --- |
| Source image | `4` (`LoadImage`) | `image` |
| Motion prompt | `5` (`MiniMaxH3ImageToVideo`) | `prompt` |
| Dimensions and frame count | `5` | `width`, `height`, `length` |
| First and last image | `5` | `first_frame`, `last_frame` both reference node `4` |
| Seed and sampling | `8` (`KSampler`) | `seed`, `steps`, `cfg`, `sampler_name`, `scheduler`, `denoise` |
| Output name and playback rate | `11` (`SaveAnimatedWEBP`) | `filename_prefix`, `fps` |

The successful job requested 384 x 480 pixels, 39 frames, 12 Euler steps,
CFG 4 and 24 fps. Its output is an animated WebP. The logged execution took
about 12 minutes 56 seconds; this is one historical run, not a performance
benchmark for future requests.

## Dependencies and limits

- Diffusion model: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Text encoder: `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- VAE: `minimax_h3_video_vae_int8_convrot.safetensors`
- Input image: `LivingTable/living-table-b91dc8789d2c.jpg` in the server's input directory.
- Output: `LivingTable/custom-ac2c1489-5327-4e3f-8382-8f83e6023631_00001_.webp` in the server's output directory.

The media and model files remain on the server; they were not copied. A HEAD
request for the original input image returned HTTP 200 (`image/jpeg`, 311217
bytes), confirming it was still accessible despite its absence from the
captured `LoadImage` choices. All referenced node classes were present during
retrieval. Local validation confirmed required inputs, graph links and output
types/indices, exact agreement with the historical graph, and the recorded
SHA-256. A successful historical
execution does not establish visual approval, loop quality, or compatibility
with a new source image. This existing motion prompt is a recovered example,
not approved Last Light Radio canon or a canonical project scene.
