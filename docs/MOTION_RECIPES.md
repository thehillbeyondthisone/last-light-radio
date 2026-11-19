# Scene setup and reusable motion recipes

The default **New motion** flow is now a simpler Describe → Mark area → Make a
take guide. It supports painted areas and correction of existing takes without
another GPU request. Start with [`GUIDED_MOTION.md`](GUIDED_MOTION.md).
The instructions below describe the established advanced pose editor, retained
for historical recipes and actions with a different ending pose.

Open the local studio at http://127.0.0.1:8765/.

1. **Import scene**, or select an existing scene and choose **Set up motion**.
2. Name the actor or region. Drag a box, click around its silhouette, or enter
   box coordinates. Include room for the intended movement. Adjust the soft edge
   and context margin; an outline controls the compositing mask, while context
   gives H3 more of the surrounding scene.
3. Choose **Quiet idle**, **One small action**, or **Change pose**. Describe one
   restrained motion. Idle/returning actions use the same pose and state at both
   ends. A pose change requires two different, aligned full-scene images and
   different named states. You can import an ending pose here; its original is
   preserved in Scenes. Pose dimensions and framing must match the master.
4. Choose 39 frames for a short test, 90 for a small action, or 124 for a full
   take, at 24 fps. Save the seed and explicitly select the video VAE. The INT8
   model is the currently authorized comparison variant; FP16 still requires
   its original model file on the worker.
5. **Prepare preview**. Original colors show the region that may move; pale
   areas show the protected scene. Inspect the actual grayscale mask and both
   768-square conditioning inputs. This uses no GPU.
6. **Save recipe & open generation**, then **Generate actor motion**. The
   result enters the review room as an unapproved candidate. Use **With static
   holds** to watch a one-second freeze of the decoded first and last frames.
   These are browser review holds, not an exported production timeline.

The scene's **Saved motion recipes** list provides **Use recipe** and **Edit
revision**. Reusing a recipe restores its poses, geometry, prompt, seed, timing
and model. **Choose a new variation seed** changes the next take's seed without
editing the saved recipe. Generation-time prompt/seed/model changes are pinned
in that job. To keep changed defaults, edit and save a recipe revision.
Revision edits preserve older recipes and candidate media. The scene list
shows the latest revisions; the generation selector retains an older revision
when explicitly opened by its ID.

## Image geometry and provenance

Scene originals retain their exact imported bytes. EXIF orientation is applied
to separate working images so outline coordinates match the displayed photo.
Every authored recipe pins the master hash, source pose hashes, working PNGs,
polygon, feathering, context crop, fit transform, seed, prompt, model, timing,
workflow template hash, hold policy and revision parent.

The automatic context crop can have arbitrary dimensions, including smaller
than 768 pixels. It is fitted into H3's proven 768-square input with Lanczos
resampling and replicated-edge padding, preserving proportions. Assembly removes
that padding and maps generated pixels back into the original crop before
applying the feathered mask over the fixed master background. Pixels outside
the effective mask remain exact in lossless assembled frames. MP4 is lossy;
odd image widths/heights receive one extra encoded edge pixel for yuv420p.

The recovered presets continue to use their exact original 768-square crops.
They are not resampled through the authored recipe transform.

The manual outline is not automatic segmentation. A tight mask can clip a
planned motion; a broad mask gives the model more visible room to change.
First/last conditioning does not ensure exact generated endpoints. Check the
silhouette, palette, identity, props and both boundaries before approving a take.
Matching named states alone does not prove a clean join to another clip.

Approved existing media can be reused byte-for-byte. Regeneration is traceable
to pinned inputs; changes in GPU/runtime/model versions can still change its
pixels. The wizard does not author cooldowns, weighted behavior pools, world
canon or episode exports.

## Implementation and verification

`recipes.py` prepares previews without writes and saves content-addressed recipe
snapshots. `POST /api/motion/preview` and `POST /api/motion/recipes` use the same
validation and transform. Saved recipes use the existing owned H3 generation,
download, mask assembly and review pipeline. Saving or previewing a recipe never
submits a render or changes approval.

Offline checks cover small/odd image sizes, portrait EXIF orientation, geometry
round trips, protected pixels, invalid outlines/parameters, distinct transition
poses, idempotent saves, immutable revisions, job pinning, model/template checks,
HTTP media contracts and an encoded candidate using a fake worker.

Live browser test: `c4d984275e894538bb515b4a1fa57ebe`, Comfy prompt
`76053bbb-6889-4e84-a100-96c62ad5d1fe`, recipe revision one
`105a1e267a2dc2f586f26be4be12bfbc`. A manually drawn reader outline produced
39 frames at 24fps, 1920×1080, 1.625s; recorded worker runtime 55.969s.
All 39 raw PNGs decoded, the MP4 passed full decoding, and three lossless samples
had zero differences outside the effective mask. Revision two
`3d8659f8e35fb0bfabdf094f82c3b006` changes the saved name and duration to 90
frames; the completed test retains revision one. It remains unapproved.
The eight historical approvals and original library database hash are unchanged.

Evidence: `artifacts/recipe-wizard/validation.json` and browser screenshots.
