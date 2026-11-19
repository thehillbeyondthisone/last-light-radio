# Authoring Director: first design slice
2026-11-14. Proposal and data prototype, not an implemented autonomous filmmaker.

## What we are building
A small idea becomes an editable treatment, script, continuity bible, audio plan and shot book. The same artifacts are editable by Boden or an agent. Generating footage is a later, separately authorized step. This is an AUTHORING assistant, not an LLM improvising during Last Light Radio playback. Runtime episode assembly remains deterministic.

## Current evidence
Toast source inspected: film_shot_plan.py stores revisioned, contiguous frame intervals with brief and first/last image IDs, candidate lineage and approval-gated placement. film_story.py supplies bounded sequence-end FMV choices. film_continuations.py carries rendered endpoint references. These are useful building blocks, not a scriptwriter.
Important gap: film_shot_plan.anchor caps generated assignments at 124 frames, and h3_joint_av_recipe.py is the earlier 672x384 joint-AV workflow. The successful external Harbinger singing workflow cannot simply be assumed available inside the editor. Implement a versioned capability adapter before connecting it.
No Git repository detected in this checkout. No source/UI/library changes made.

## Separation of responsibilities
1. Writer: develop premise, protagonist want, obstacle, change and ending. Draft dialogue only when it reveals character or changes events. For music-first input, preserve the chosen audio and write pictures around its actual phrases. For idea-first, write before selecting/generating final audio.
2. Director: turn story beats into visual evidence, not a mood montage. Each shot must cause, reveal or pay off something. Specify what the viewer learns and the changed state.
3. Script supervisor: track character/wardrobe, geography, screen direction, prop location/ownership, time/light and unresolved promises. Flag contradictions; never silently change canon.
4. Production compiler: resolve references and exact audio windows; translate intent into a model-specific recipe. It owns framing/duration/prompt constraints, not story invention.
5. Editor: assemble selected takes and original audio into a review sequence. Preserve prior takes, timing and provenance; repair only flagged material.
6. Reviewer: separate technical validation, visual/performance judgment and owner acceptance. None implies another.

## Draft package contract
brief: user's words, audience, format, duration range, tone, constraints, must-have and forbidden elements.
treatment: logline, theme, start/end emotional state, causal beat outline, alternative pitches.
bible: stable IDs and approved revision for cast, settings, props, wardrobe and reference assets.
script: scene headings, action, dialogue/lyric-line IDs, source provenance and revisions.
audio: master asset/hash, sample rate, stems, line IDs, measured ranges and confidence. Never derive exact boundaries solely from text.
shotbook: stable shot ID, scene/beat IDs, narrative purpose, duration, framing/camera motivation, action, state-in/out, references, audio assignment, transition intent, risk and review.
take ledger: shot/recipe revision, prompt, seed, model/workflow hashes, inputs, output hash, timestamps, runtime, status, rejection reason.
edit: source in/out and sequence frames with rational fps, soundtrack placement, approved picks and candidate cut version.
review: specific timestamp, defect category, evidence, remedy hypothesis and owner feedback.

Use stable semantic IDs upstream. Translate to existing plannedshot.<32hex> IDs only in a future import adapter. Keep the rich director package beside the reduced editor projection, not crammed into a brief string.

## The creative loop
Small brief -> 2-3 distinct concepts -> one treatment -> causal beats -> script/audio -> reference bible -> storyboard/rough animatic -> shot book -> capability preflight -> SD tests -> candidate cut -> targeted fixes -> final resolution.
Allow explicitly delegated approval batches, but record what was delegated. Proposed story facts are not approved world canon. The user can take over at any stage without learning a different application.

## Model-specific calibration
Local experiments establish hypotheses, not universal laws. FABLE reconstruction proves rendering, not original writing.
Current feedback: opening cleanup candidates work well; book performance remains bad. Chain baselines had bad lip sync, so they do not establish an optimal duration or superiority. Mouth opening correlation is only a rough motion proxy.
A proper experiment keeps content/audio/ref/seed/recipe fixed and changes one factor, using a baseline the user considers good. Compare multiple seeds and at least two distinct shots. Review first/last syllables, bilabial closures, expression, identity and seam in playback; retain failed examples.
Never apply a Seedance-specific timing or image-binding rule to H3 without checking the installed node/workflow. Record support for first/last frame, audio input, motion history, duration and multiple reference images separately.

## Editorial quality gates
Structural: all beats have a visual cause/payoff, no shot without purpose, scene exit state matches next entry or has a motivated transition.
Technical: assets exist/hash-match, frame math valid, no uncovered picture unintentionally, exact soundtrack timing, supported recipe, no duplicate submission.
Perceptual: identity, gesture, mouth/syllables, continuity and pacing watched in motion. Frame sheets cannot certify lip sync.
Owner: explicit feedback selects changes. Do not rerender good shots because an automated score is lower.
For FMV, write branches with explicit state conditions and rejoin compatibility; current graph supports end-of-sequence choices, not general inventory/hotspots.

## First implementation slice
Keep Claude's UI untouched. Build a standalone authoring-package validator and dry-run exporter into a disposable sequence, then test save/reopen/revision conflict and no-GPU behavior. Add a writing stage only after the package contract is useful. Existing app should display scripts/shot plans through its familiar Browser/Viewer tools eventually, not a new parallel editor.
Next proof: a 30-second ORIGINAL scene with no singing, using the attached provisional shotbook, before adding dialogue/audio synchronization and branching. This is a proposed proof, not a render job.

## Sources and bounded lessons
- https://claudia.gallery/wiki/recipe/ : staged creative decisions, identity references, prompt economy, human playback review. Provider-specific rules are not local guarantees.
- https://claudia.gallery/kit/ : shot books, lineage and repeatable stages demonstrate an adapter-friendly architecture; it is not our local runner.
- https://claudia.gallery/record/fable/readme/ : FABLE is a documented authored production, not evidence that one prompt autonomously delivers an original film.
- https://claudia.gallery/agents/ : read-only recipe/record/tool interfaces, not an authorization to invoke external agents or paid generation.


## User requirement captured 2026-11-14: synchronized take audition
Boden wants to audition multiple synchronized alternatives (for example four-up), then swap the chosen take into the sequence while retaining the others. This is a provisional workflow requirement, not a settled UI design. Align alternatives to the same sequence/audio interval with explicit source offsets; make duration mismatch and missing coverage visible rather than stretching silently. Keep immutable takes and lineage, preserve soundtrack timing, and make replacement undoable/revisioned. Do not let a metric silently choose or approve the winner. Integration should reuse the existing shot candidate groups and interval placement where possible. No four-up UI or production replacement implemented by this note.
