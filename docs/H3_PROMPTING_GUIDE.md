# Prompting MiniMax H3 through ComfyUI

Written 2026-10-27 for this project's creator workflow.

A strong first take starts with a clear action, suitable reference images and a known working graph. The prompt describes the intended motion; the workflow, image preparation, compositing and review make the result usable and repeatable. Better wording improves the odds, but cannot guarantee anatomy, exact timing or a seamless join.

This guide combines the recovered local MiniMax H3 recipe with lessons from saved trials. **Completed candidates are not automatically approved clips.** Examples below describe motion experiments, not new world canon. Public documentation was checked on the date above; the saved local workflow remains the reference for this installation.

## 1. The practical starting recipe

1. Choose one subject and one complete action that fits the clip length.
2. Decide how it ends: return to the starting pose, settle into a different state, or leave the shot.
3. Inspect the actual first and last conditioning images, including their crop and proportions.
4. Write the physical sequence in order, then identify the few things that must stay fixed.
5. Give the motion enough crop space and mask support for its entire path, including handled props.
6. Start with the saved production graph and an explicit seed. Keep the selected VAE and sampling settings unchanged during prompt comparisons.
7. Review both raw generation and the full-scene composite, including every movement passage and both joins.
8. Save the exact executed recipe and media. Approve the specific take only after review.

For the existing returning-action flow, see [Make a motion](GUIDED_MOTION.md). For different end poses and crop details, see [Motion recipes](MOTION_RECIPES.md).

## 2. Write prompts as observable actions

### Identify the subject and its starting situation

Use the subject already visible in the reference: “the resting black-and-white cat on the indoor ledge” or “the seated reader holding the open book.” A short visual anchor helps distinguish subjects. Repeating a complete description of the room is usually unnecessary for a small actor action.

Preserve the source style. Asking for a new cinematic or photorealistic look while trying to preserve a painted scene introduces competing goals.

### Describe the physical sequence

Replace broad intent with visible steps:

| Broad request | More useful direction |
| --- | --- |
| “Make the cat sleepy.” | “The cat lifts its chin slightly, yawns once, closes its mouth and rests its chin on its paws again.” |
| “She interacts with the radio.” | “She leans forward, touches the existing front knob, turns it once, withdraws her hand and resumes reading.” |
| “Someone leaves the shop.” | “One adult exits the doorway, turns right and walks behind the existing corner until fully out of view.” |
| “Make the light cozy.” | “The existing display briefly brightens and settles to its original level; its shape stays fixed.” |

The last example may be better implemented as a brightness effect; see section 8.

Specify contact when it matters: the same mug leaves the table, reaches the lips and returns to its original support. A hand waving near a prop does not satisfy a contact action. Also explain what supports objects during the movement: one hand holds the book while the other reaches.

### Give one action enough time

A five-second take can support a restrained action with a beginning, middle and finish. Packing a sip, page turn, glance, cat stretch and lighting change into it makes the request harder to evaluate and control.

Use “first,” “then” and “finally” for sequence. Text timestamps are intentions, not frame-accurate controls. Leave time to settle at the end. A short technical render verifies the pipeline; it does not establish that a longer action will work.

### Prefer positive constraints

“The radio stays planted on the table” and “the cat's hindquarters remain lying on the ledge” describe the intended image clearly. Keep any failure-specific exclusions brief and relevant rather than accumulating a large ban list.

The production graph uses `BasicGuider` with one conditioning branch and has no separate negative-prompt input. Adding “negative prompt:” to its text does not create one. ComfyUI's current [H3 prompt guidance](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide) also recommends positive descriptions for this guider.

### Make the ending unambiguous

| Ending | What the prompt and references should establish |
| --- | --- |
| Returning action | The subject performs the action and settles back into the supplied pose; handled props return to their supports. Same-pose endpoints are appropriate. |
| Persistent change | The subject or object finishes in the new state, such as looking outside. Use an aligned ending plate showing that state and the corresponding named exit state. |
| Departure | The subject follows a visible route out of view. An empty ending means it has left, even if the opening is also empty. Describe the occluder or frame edge. |

Do not combine a departure with “return to the starting pose.” The guided returning-action flow appends that instruction automatically; inspect the **compiled rendering prompt**, not just the description you typed. Different endings require the appropriate advanced setup or a separately prepared recipe. This guide does not add persistent-state support to the default editor.

## 3. Reusable prompt and brief templates

### Motion prompt for the existing local graph

Replace the brackets with details visible in your supplied image:

```text
One continuous locked-camera shot in the supplied image's style.
The [existing subject] begins [starting pose and prop support].
First [action onset], then [physical motion/contact], finally [ending state].
The movement is [small/slow/calm] and occurs once.
[Relevant planted body parts and untouched props] remain in place.
Preserve [identity, composition, important geometry and palette].
```

This is a practical writing scaffold for our tested concise-prompt path, not a special syntax the node parses. Fill in the action first; add constraints that address real scene risks.

MiniMax's [official base-mode guide](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt) also provides a structured format: an image-alignment instruction where applicable, then `integrated_multimodal_description`, `overall_soundscape` and `non_diegetic_music`. It distinguishes first-frame development from the path between two endpoint images. That structured format is a documented alternative; it has **not** been compared against our concise prompts locally. Test it as its own revision rather than assuming it improves an existing take.

Our saved production graph outputs PNG frames and has no audio decoding/output path. Audio instructions in text do not add an audio deliverable. Reference-video motion, depth and pose conditioning likewise require a graph that actually connects those inputs; our recovered graph receives endpoint images and text.

### A complete generation brief

This is useful when asking a collaborator to prepare a take. Keep operational instructions outside the text sent to H3:

```text
Source: [existing master/scene and saved recipe revision].
Goal: [one observable action].
Starting state: [pose, presence and supported props].
Ending state: [return / new pose / fully out of shot].
Motion path: [direction, contact points and occluders].
Keep fixed: [camera, identity, key geometry and unaffected subjects].
Use: the confirmed production workflow and [explicit VAE variant].
Timing: [frame count] at 24fps. Generation seed: [integer].
Scope: [number of takes and allowed variables].
Deliver: raw and composite previews, full-scene/detail review and saved provenance.
Pass criteria: [specific action, anatomy, contact, containment and join requirements].
```

For a correction, describe the observed failure and its location: “the tail is cut off during its early leftward sweep; check the unmasked frames before choosing a fix.” That gives a much clearer next step than “make it better.”

## 4. Examples grounded in this project's takes

### Cat yawn: one action and a stable body

The saved creator description for seed `884001` was:

```text
The same black-and-white resting cat on the indoor window ledge slowly lifts its chin a little, opens its mouth for one small sleepy yawn, closes its mouth and lowers its chin back onto its front paws in the exact supplied resting pose. The torso and hindquarters stay lying in the same spot. One gentle yawn only; no standing, walking, exaggerated teeth or changing face markings.
```

The app added its camera, preservation and return instructions. The [exact submitted prompt](../artifacts/cat-variations-20261026/sleepy-yawn-generation-request.json) is the reproduction reference. Passage samples show the intended action; anatomy and exact joins still need creator review. The candidate remains unapproved.

### Radio adjustment: specify the mechanics

An illustrative shorter rewrite of the [saved radio request](../artifacts/radio-compositing-20261024/adjust-radio-generation-request.json):

```text
The seated reader pauses, keeps the open book supported on her lap with one hand, and leans forward. Her free hand reaches the existing radio's front knob, makes one small turn, withdraws and returns to reading. The radio stays planted and the mug stays on the table. She settles into the supplied reading pose. Keep the camera, source style and surrounding scene fixed.
```

This rewrite has not been rendered. The actual seed `883831` request is longer and includes explicit contact and anatomy guidance. Its completed candidate shows the reach and return in samples; completion does not prove correct finger contact. The later synchronized display flicker was a separate CPU effect, not an H3 prompting result.

### Departure: empty endpoints can hide different stories

“Start and finish with an empty street” leaves the motion ambiguous. The [one-way departure request](../artifacts/departure-lighting-20261024/shop-departure-generation-request.json), seed `883821`, explains the rightward route, existing corner/tree occlusion and why the person is absent at the end. It also uses doorway-relative adult scale.

The trial shows one-way travel in samples, but late shrinking/disappearance still needs review. Neither a scale description nor an empty ending image guarantees a believable exit.

## 5. Preserve the known working ComfyUI recipe

The baseline below comes from [the recovered production recipe](../workflows/h3/production/README.md) and its [API-format graph](../workflows/h3/production/workflow_api.json). These are local facts, not universal settings for every H3 variant.

| Component | Recovered production setting |
| --- | --- |
| Diffusion model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| Turbo LoRA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`, strength 1 |
| Guidance and noise | `BasicGuider` and `RandomNoise` |
| Sampling | `res_multistep`, `simple`, 8 steps, denoise 1 |
| Generated crop | 768 × 768 |
| Common duration | 124 frames at 24fps = 5.166667 seconds |
| Other saved durations | 90 frames = 3.75 seconds; 39 frames = 1.625 seconds |
| Original template VAE | `minimax_h3_video_vae_fp16.safetensors` |
| Recorded authorized comparison VAE | `minimax_h3_video_vae_int8_convrot.safetensors` |
| Graph output | Lossless PNG sequence; the app composites and encodes review video |

The last saved worker checks found the FP16 VAE absent. INT8 is an explicit execution variant, not an invisible fallback, and this document does not establish today's worker availability. A missing model/node should fail preflight visibly.

The [earlier smoke-test graph](../workflows/h3/README.md) uses a different KSampler/Euler/12-step/CFG-4 setup, smaller dimensions and animated WebP. Keep the recipes separate. There is no production CFG knob to increase in this `BasicGuider` graph, and changing Turbo steps independently is an experiment, not a guaranteed quality upgrade.

For another installation, inspect its exported API-format workflow and actual node definitions before binding controls. Node IDs are graph-specific. Newer ComfyUI documentation describes additional H3 modes; their existence does not make them inputs to this saved graph.

## 6. References, crops and masks determine what is possible

Keep the canonical image immutable. Prepare separately stored endpoint plates and crops, with matching framing and dimensions. A distinct ending plate must agree with the requested ending state. Conditioning encourages an endpoint; it does not prove generated pixels exactly match that plate.

Give H3 enough surrounding context to understand the contact and movement. For a radio reach, include the torso lean, full head/hair/headphones, arm, hand and radio. For a cat stretch, include the complete tail arc and paw travel. Preserve proportions when fitting the crop; our authored recipes use a saved fit/padding transform rather than stretching arbitrary crops to square.

The **context crop** is what the model can generate. The **compositing mask** determines which generated pixels become visible over the canonical background. In our workflow the mask is applied afterward; it is not H3 motion conditioning.

- If a limb exists in raw frames but disappears in the composite, inspect mask support and foreground protection. A separate CPU recomposition may solve it without a new GPU job.
- If motion extends outside the generated crop, widening a mask cannot recover those missing pixels. Prepare a larger context and a new take.
- If raw frames contain a malformed hand or the wrong action, mask editing cannot repair that generation.
- Keep foreground rails, frames and other occluders in front. A larger mask can expose unwanted generated changes, so inspect its entire support.

The [cat stretch correction](../artifacts/cat-stretch-correction-20261026/README.md) and [radio headroom correction](../artifacts/radio-headroom-20261025/README.md) reused existing raw frames. The first cat correction missed an earlier tail sweep: checking only start/middle/end would have missed the problem.

## 7. Repeatability requires more than a seed

| Desired result | What to preserve |
| --- | --- |
| Use the exact same approved clip | Retain the original media and verify its checksum. |
| Repeat a generation recipe | Retain every input, parameter, graph and environment detail; verify a fresh run rather than promising identical pixels. |
| Reproduce an episode schedule | Pin approved clip/review versions, world/state data, rules, scheduler version and the episode seed. |

PyTorch explicitly does not guarantee identical results across releases or platforms, even with identical seeds. Runtime details therefore belong in the record. See [PyTorch reproducibility](https://docs.pytorch.org/docs/2.14/notes/randomness.html). The reliable way to retain a specific approved performance is to keep its media.

For every generation, record:

- Exact source bytes/hashes, prepared first/last PNGs and their hashes.
- Crop coordinates, fit/padding transform, mask/feathering and recipe revision.
- Exact final prompt, including automatically appended instructions, plus all effective noise seeds.
- Diffusion, encoder, VAE and LoRA identities; retain model checksums when available. A matching filename alone does not prove matching weights.
- Submitted and executed API graphs and hashes, steps, sampler, schedule, denoise, dimensions and frame count.
- ComfyUI/core/custom-node revisions, Python/PyTorch/CUDA/driver versions, GPU, attention backend, precision, launch options and relevant optimizations.
- Accepted Comfy prompt ID, status/error history, raw output hashes and assembly/encoding settings.

Freeze any dynamic prompt choices and seed randomization during comparisons. In our app, **Make another take** chooses a fresh variation seed; use **Repeat this seed** for a controlled repeat and check the actual submitted value. Keep the generation seed separate from the episode scheduler seed.

A small experiment plan:

| Take | Change | Purpose |
| --- | --- | --- |
| A | Saved baseline, seed 884001 | Establish the comparison |
| B | One wording change, seed 884001 | Test that wording on the same seed |
| C/D | Same revised wording, seeds 884002 and 884003 | Check whether it works beyond one seed |

Those numbers are experiment labels, not quality settings. One successful seed is weak evidence of general reliability. Stop when the take meets the written criteria; rerolling indefinitely is not a substitute for fixing a contradictory brief or insufficient crop.

When automating, save job ownership before and after submission, use unique input/output paths and resume the accepted prompt through history polling or supported WebSocket tracking. A lost connection is not evidence that submission failed. Do not blindly POST again after an ambiguous response; do not clear a shared queue. Our existing adapter retains prompt IDs and resumes polling/downloads without resubmitting.

## 8. Use ordinary code for exact effects and long episodes

Use H3 for candidate motion. Use deterministic processing where the requirement is a specific brightness envelope, exact cue timing, seeded ambience or approved-clip scheduling.

The [radio display cue](../artifacts/radio-sync-proposal-20261026/README.md) was attached to frames 34–68 of the adjustment take through a saved CPU transform. Its synchronization is not evidence of frame-accurate prompting. Cue scope approval also did not approve the combined take or its production placement.

The [passing-car trial](../artifacts/passing-car-20261026/README.md) requested restrained headlights but still produced overly bright reflections. A CPU comparison reduced them and exposed uneven lamp strength. “Subtle” alone did not enforce the desired lighting.

For a long episode, build reviewed motion variants and reuse them with validated holds, state transitions and ambience. Schedule them with ordinary deterministic code. A ten-minute timeline can use sparse meaningful events; it does not require ten minutes of novel diffusion output. Overlapping logical schedules do not make unrelated full-frame AI clips safe to composite.

## 9. Review against explicit pass criteria

Check the raw crop and composite at normal speed and frame by frame around risky passages:

- **Action:** correct subject, one intended action, believable speed, correct path and finish.
- **Anatomy/contact:** continuous limbs, preserved identity/markings, grounded feet and convincing hand/prop contact.
- **Scene:** stable camera, palette, architecture, prop placement and foreground occlusion.
- **Containment:** full motion support with no clipped head, tail, paw or carried prop; protected pixels remain unchanged in lossless composites.
- **Boundaries:** actual generated entry/exit frames, last-to-first replay for loops, and joins to the intended next clip or hold. Matching state names alone are insufficient.
- **Media:** decode every frame; verify count, dimensions, frame rate and timestamps. Check the delivered MP4 as well as PNGs. Exact protected-pixel equality is a lossless-frame property; MP4 can add compression differences.
- **Disposition:** save specific notes and approve/reject the individual take. Corrections and new seeds require their own review; approval does not transfer automatically.

## 10. Diagnose the failure before changing the prompt

| Symptom | First check | Useful next step |
| --- | --- | --- |
| Head, tail or mug is cut off | Raw frame versus composite; full movement arc | Correct mask support if raw pixels exist; otherwise widen context for a new take |
| Departure reverses or returns | Appended return instruction and endpoint meaning | Remove the semantic conflict in the appropriate recipe; describe route and exit |
| Hand misses the knob or mug | Raw contact frames, crop detail and time budget | Simplify the action, improve context and specify support/contact |
| Person is too small | Prepared input scale and doorway proportions | Correct references/context; use a visible scale anchor and review again |
| Camera or background drifts | Raw crop, references and mask exposure | Reinforce a fixed shot, reduce action scope and protect unaffected pixels |
| Replay differs despite the seed | Effective prompt, noise seed, graph, models and runtime | Compare saved records; reuse approved media when exact retention matters |
| Endpoint snaps | Actual generated exits and the next entry | Review another take or explicit transition; do not silently replace endpoints |
| Lights change shape or overwhelm the scene | Whether shape motion is needed | Try a separately reviewed deterministic light effect |
| Node/model is missing or a job fails | Preflight and owned job/history logs | Report the specific incompatibility; preserve the recipe and avoid silent substitutions |

The reusable habit is to save the recipe that produced the result, identify which stage caused a failure, and change one relevant variable at a time.
