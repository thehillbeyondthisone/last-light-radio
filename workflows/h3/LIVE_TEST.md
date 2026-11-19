# Live H3 smoke test — 2026-10-21

The creator requested live generation using the recovered graph and the generated
technical test illustration. Exactly one job was submitted. It is not canon or
a production-approved motion clip.

| Item | Observed value |
| --- | --- |
| Local job | `0d42247f7f6b4e6da6ed5b034bb35b04` |
| Comfy prompt | `1a5b0bb0-a0fa-4644-b96d-2b32a116c8c4` |
| Output | Animated WebP, 384 x 480 |
| Requested settings | 39 frames, 24 fps, 12 Euler/simple steps, CFG 4, seed 7 |
| Decoded output | 39 frames, 41 ms each, 1599 ms total, 24.39024 effective fps |
| Server execution | 35.925 seconds between execution_start and execution_success |
| Cached nodes | 1, 2, 3, 6 (loaders and sigma-shift path) |
| Peak VRAM | Unknown; before/after device snapshots retained |
| Review status | Candidate; creator approval pending |

The original 11-node workflow was deep-copied. Only the source image, motion
prompt, seed and unique output prefix changed. Both first/last-frame links still
point to the same uploaded image node. Executed history graph hash matches the
prepared workflow snapshot.

## Saved artifacts (relative to project root)

- Candidate directory: `runs/h3-test/candidates/0d42247f7f6b4e6da6ed5b034bb35b04/`
- Animated file: `00-b9a4b7c2e3d377ae729cd5635b15d1bc31e784fdbbf6ab63bc1dd22f09512feb.webp`
- Complete provenance: `candidate.json` in that directory.
- Pixel verification and head/middle/tail samples: its `review/` directory.
- Ownership/request checkpoints and events: `runs/h3-test/records/live_jobs/0d42247f7f6b4e6da6ed5b034bb35b04/`
- Content-addressed request/workflow/definition/history snapshots: `runs/h3-test/records/`

The first download exposed Windows `\\` separators in the server's nested output
folder. The adapter now normalizes safe nested separators while rejecting drive,
absolute and traversal paths. Download resumed from the same accepted job. No
extra prompt, queue clear, interruption or cancellation was issued.

## Verification and visual limits

All 39 frames decoded successfully with Pillow 12.3.0. The dependency-free WebP
container inspector and Pillow agreed on dimensions, frame count and duration.
Before/after SHA-256 of the original still and recovered workflow stayed equal:

- Still: `e70c46495714adb4703d7e9c433ec84f76ed96db72f427da4ee0aa3278d17caa`
- Original workflow file: `b32cdde4361006b82cd4fc9e39484a9106c53eba0d76de0fe8708323a255c556`
- Output: `b9a4b7c2e3d377ae729cd5635b15d1bc31e784fdbbf6ab63bc1dd22f09512feb`

The contact sheet shows broadly stable camera/composition, book, cup, furniture
and cat placement. The reader's head/face pose changes across the take, so this
test is not approved as a seamless loop. Sampling three frames cannot establish
blink quality or absence of every intermediate artifact. The creator should
review playback before any motion-library approval.

This one warm run is not a general performance benchmark. Millisecond WebP frame
timing also explains why encoded effective FPS differs from the requested 24.

## Motion prompt used

> Animate this exact reading-room illustration with a locked camera. The seated
> adult reader breathes very gently and blinks once, then returns to the starting
> pose. Preserve the face, hairstyle, hands resting on the open book, book shape,
> cup placement, sleeping cat, furniture, window geometry, painted colors, lighting
> and framing. No new objects, no text, no camera movement, no scene cuts. Keep all
> props and the sleeping cat still.
