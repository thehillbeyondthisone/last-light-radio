# Claude UI handoff: generative NLE with Final Cut Pro 7 familiarity

Updated 2026-11-13. This is the current UI-only assignment, not a request to rebuild the application or generate new media.

## Start here

- **Computer:** Toast (Windows).
- **Project root:** `C:\Users\thisi\OneDrive\Documents\repos\last-light-radio`
- **This handoff:** `docs\CLAUDE_UI_HANDOFF_2026-11-13.md`
- **Open the correct working editor:** `OPEN_FILM_EDITOR.bat`
- **Running URL on Toast:** http://127.0.0.1:8769
- **Persistent working library:** `.local\film-studio`
- **Old scene-animation library:** `.local\studio` (separate; preserve it).
- **Main UI:** `frontend\src\FilmEditor.tsx`, `fcpFilm.css`, with shared `editor.css`.
- **Stack:** React + TypeScript/Vite frontend; Python local HTTP service, SQLite and filesystem assets. This is not a blank design prototype.

Inventory confirmed these paths on Toast. **There is no Git repository at this root as inspected** (`git status` returned “not a git repository”). Do not assume branches, commits or reset are available. Make a dated source checkpoint before UI edits; do not duplicate the entire large media library merely to checkpoint CSS.

## What Boden asked for

“Give it a full UI treatment” while **dot continues working on the videos in the background**. Claude owns UI presentation and usability only. Dot owns creative media generation, recipes, source/reference preparation, model calibration, clip review and sequence assembly.

The goal is a **generative non-linear editor** with familiar Final Cut Pro 7 operation, plus custom tools for:
1. Directed short films / music videos.
2. Last Light Radio: long cozy episodic scenes built from approved idle/action variations in one shared world.
3. FMV games inspired by Titanic: eventually richer interactive narrative/game tools.

Boden knew FCP7 very well. Its familiar mental model is the point of this editor, not a decorative “retro” skin. Earlier changes removed that essence and were explicitly rejected. Do not replace the editing desk with a scrolling form app, chat-first app, card dashboard or wizard. Do not make the user relearn the workflow with each iteration.

**Both modes must work:** Boden can do everything directly in the application, OR dot can drive the same capabilities. Temporary assistant-led production during development is not permission to leave core capabilities hidden behind scripts. Current end-to-end UI/automation parity is not fully verified; audit actual controls instead of claiming it.

## Concurrent work: avoid collisions

The narrow playback correction and J/K/L follow-up are complete, built and tested; the playback worker has released the file. **Claude may now edit `FilmEditor.tsx` for the UI treatment**, preserving this behavior:
- A clean sequence with a completed current export plays one continuous muxed audiovisual source in Canvas rather than remounting a decoder at each cut. Its embedded final mix replaces the separate follower audio, preventing double sound.
- Shot selection follows the rendered timeline without resetting the decoder. The playhead uses requestAnimationFrame updates.
- Space/J/K/L now share non-text focus rules: timeline sliders, Canvas controls and clip buttons accept transport. Text/number inputs, textareas, selects and contenteditable retain typing. Keyboard autorepeat is ignored.
- J reverse and L forward use the existing discrete 1x/2x/4x/8x ladder; switching direction starts at 1x. K immediately pauses media, cancels reverse jogging and resets rate to 1x.
- Reverse is a muted wall-clock-anchored 24Hz seek jog, **not native smooth backward video decoding**. Fast forward above 1x is muted in both monitors. Do not represent reverse as smooth sample-accurate audiovisual playback.
- Unsaved/dirty edits explicitly switch to **Live edit preview**, not a stale completed export. Discard restores the current rendered review mode. Both modes are identified in the UI.

**Important remaining limitation:** unrendered/dirty live editing still uses the original per-shot player and may buffer/flash at cuts. Seamless live editing needs a future prebuffered-decoder or incremental-proxy strategy; it has not been implemented. Preserve this honest distinction rather than implying all editing playback is now seamless.

Evidence: `artifacts/playback-fix-20261113/QA.md`. Chrome tests covered full chorus playback to frame 421 using the same AV URL, Space on timeline and clip buttons, text-field exemption, and dirty/discard mode changes. No sequence data or generation code was changed. Read the current file rather than restoring the source backup over it.

Dot will continue creating/importing videos and assembling cuts. Therefore:
- Never delete/reset/seed the live database or media store.
- Never replace current project/sequence JSON or source files with fixtures.
- Do not migrate schemas, change APIs, worker/model settings, generation graphs, frame/timebase conventions, import/export semantics or provenance to accommodate a redesign.
- Do not submit generation jobs or change approvals as part of UI testing.
- Do not kill ComfyUI/ACE-Step or change their dependencies.
- Do not restart the local editor service or refresh away an unsaved cut without coordination.
- Avoid changing `last_light_radio\`, `workflows\`, `.local\`, `assets\`, `runs\`, and existing `artifacts\` except deliberate new UI QA artifacts.
- If a UI feature truly needs a backend contract change, document the proposed interface and let dot coordinate it rather than silently implementing it.
- Preserve element hooks, command IDs and API payload contracts while refining markup/styles. If refactoring a large component, separate behavior-preserving work into small verifiable steps.

This document is a file handoff for the user to give Claude. It does not send instructions to an external agent or authorize unrelated work.

## Read these before changing code

1. `AGENTS.md`
2. `PROJECT_TRUTHS.md`
3. `HANDOFF_PLAN.md`
4. `MVP_TASKLIST.md`
5. `docs\FILM_EDITOR.md`
6. `docs\EDITOR.md`, `docs\EDITOR_LEARNING_NOTES.md`
7. `docs\FMV_EDITOR.md`
8. `artifacts\fable-chorus-native-20261113\QA.md`

The first handoff was written October 18 as a reconstruction plan. Its “no working code verified” statement is **historical**, not the state today. Later dated sections and actual code/evidence supersede early limitations. For example, earlier film notes say “no FMV” and “no audio-first,” then later sections document those additions. Read chronology carefully.

Example lore such as bus 271 / UMBRA FM 88.3 remains illustrative, not approved canon. Do not invent names or lock story details during UI work.

## Familiar editing desk to preserve

- **Browser left:** projects, named sequences, bins/source takes; creation/import tools can be contextual or collapsed.
- **Viewer center:** source audition, source In/Out and contextual generation/audio/shot-plan/FMV tabs.
- **Canvas right:** the actual sequence/program picture, kept visible while using generative tools.
- **Timeline across the bottom:** proportional video and audio tracks, time ruler, playhead, markers and track controls.
- Distinct source vs sequence timecodes and clearly indicated active pane.
- Compact, readable information density. Use a coherent restrained chrome, good typography, clear selection/focus, usable split sizes and obvious transport.
- New custom tools should fit within this shell. Polish them, do not bury them or remove them.
- Keep playback state separate from selection state; selecting a clip/bar should not make keyboard transport inexplicably stop.
- Error, pending, failed, unreviewed, approved and completed states must be distinguishable without relying only on color.

Keyboard registry is `frontend/src/shortcuts.ts`. Film reuses the saved keymap but not every historical Scene animation command is implemented in Film. Do not advertise nonexistent commands.

Current Film commands documented: Ctrl+1 Viewer, Ctrl+2 Canvas, Ctrl+3 Timeline, Ctrl+4 Browser; Q Viewer/Canvas; Space transport, K stop, J/L shuttle; arrows frame-step; I/O source marks; F match frame; Ctrl+S save; undo/redo; timeline zoom/fit. Preserve text entry, native text undo and arrow behavior in actual text fields. Space/J/K/L should not be swallowed merely because a range input/timeline control is focused. No fake ripple/roll/slip buttons.

## Data model and non-negotiable preservation rules

- **Project** owns independently named **Sequences**.
- **Sequence** owns ordered picture **Shots** and independent audio placements, explicit duration, markers/selection, saved revisions and exports.
- **Source take** is immutable imported/generated media with hash, provenance and review state.
- A shot references a source frame range. Trimming never edits source bytes.
- **Scene animation** is the preserved single-environment composition tool, not another word for a project or sequence. Its result can become a film source.
- Reference images are immutable originals/derivatives with lineage; first/last conditioning roles are explicit.
- Accepted generation is not production approval. Completed jobs become candidates; review/placement remains explicit.
- Maintain save/discard/dirty navigation guards, separate story/shot-plan/sequence dirty state, undo/redo and revision conflict protection.
- Keep original media intact, avoid implicit time stretching/looping, and never overwrite the baseline cut to present a nicer mockup.
- Keep continuous soundtrack timing fixed unless the user explicitly chooses ripple behavior. Source embedded audio is muted when program audio uses separate lanes, so sound must not double.

## Features already present: polish, do not lose

### Core Film editing
Project/sequence selection, source Browser, source audition and In/Out marks, frame-based contiguous shot assembly, source trimming and ordering, named independent cuts, source match-frame, undo/redo, save/reopen, export, V1 picture/A1 production/A2 music, proportional timeline and active-pane keyboard navigation. Current Film edits are still bounded straight-cut operations, not a complete FCP7 clone.

### Audio-first
Sequence duration without picture, audio import/review, canonical PCM waveforms, independent audio start/trim/gain/fades, markers and selection. Audio-only exports WAV; picture can be added later without shortening the sound bed. Waveform represents source amplitude, not necessarily post-fader mix. Streamed WAV imports support up to 256 MiB/600 seconds when server capability is present. Do not confuse a bounded technical capacity with tested production quality.

### Generative video
H3 take brief and seed; worker/recipe preflight; explicit Generate; durable jobs and receipts; status/elapsed time; immutable exact workflow/model/reference provenance; separately reviewed picture and sound; designated timeline destination placeholders; revision-safe candidate placement. Show real stages, not invented percentage completion/ETA. Do not queue on page load.

First/last reference slots accept imported images or captured source frames. “Continue this shot” starts from the actual last used rendered frame and preserves lineage. These are generative constraints, not guaranteed seamless native rolling edits.

### Audio-led shot planning
A timeline range can become a shot assignment with brief, references and candidate takes. Picture-only fitting preserves the soundtrack. Longer sources require explicit trim; too-short takes are rejected rather than automatically stretched or looped. Preserve distinctions among a source, candidate, planned shot, placed shot and finished export.

### Music
ACE-Step adapter with preflight, explicit jobs, receipts and review. A short instrumental cue was tested; 180/210/240-second recipe controls exist, but do not imply every long/vocal mode is musically calibrated. Connection may use a dynamic local Pinokio port; do not hardcode a newly guessed service.

### FMV
Project-owned story nodes bound to saved sequences, end-of-clip choices, start/terminal nodes, validation, frozen revision-pinned exports, and rehearsal in Canvas. Not yet a complete Titanic runtime: no verified timed/spatial hotspots, inventory, variables/conditions, dialogue interruption or game packaging. Do not style placeholders as finished capabilities.

### Scene animation / Last Light Radio
Preserve the separate library and operational composer: canonical stills, subject motion areas/masks, approved idle/action variants, deterministic scheduling, nested sequences, rain/steam/texture controls and historical pilots. Long-term: shared-world continuity and configurable hour-scale episodes without a runtime LLM inventing new behavior. Do not hardcode FABLE or Claudia as the application.

## Current creative state and visible test case

The private FABLE benchmark uses source film frames, documentation and original soundtrack as references:
- https://claudia.gallery/record/fable/readme/
- https://claudia.gallery/agents/
- https://claudia.gallery/kit/

This is calibration, not a public release. Original soundtrack/stems are not cleared for re-release. Preserve source provenance and the distinction between source film reference frames and original production stills.

An overnight roughly four-minute assembly exists and is preserved. A newer **17.583-second first chorus** has 8 shots in source order, seven new H3 takes plus one approved reuse:
`C11, A11, C12, A12, C13, A13, C14, A14`.

- Project: **FABLE - private local calibration**
- Sequence: **FABLE - chorus native audio guidance (work in progress)**
- ID: `sequence.f2b890ca528e46f5a61658fb49a20afd`
- Snapshot: revision 5, 422 frames, 24 fps, 672x384.
- Full original chorus soundtrack continuous on A2.
- Overnight baseline: `sequence.51e664c316674d1786a3a3e8485cb859`, revision 100 at last check.
- Evidence/media/provenance: `artifacts\fable-chorus-native-20261113\`.
- Prior overnight review guide: `artifacts\fable-overnight-20261113\START_HERE.md`.

Boden selected the **native H3 vocal-guided tighter face take** as nearly flawless at first glance and rejected the extra EDTalk lip-sync pass. The full chorus uses H3 native guidance, **no EDTalk**. Do not casually swap the rejected take into a thumbnail, default selection or showcase.

The model-side generation is on Harbinger; Toast hosts the NLE. New video work continues in parallel and may change catalog/sequence revisions. Treat IDs above as a useful checkpoint, not permission to revert newer changes. The winning vocal-guided pipeline was run externally and imported with provenance; do not imply all of that recipe is already exposed end-to-end as a polished native GUI mode. The goal is UI access parity, still to be checked.

## Code map

- `frontend/src/App.tsx`: workspace navigation; Film editor is the default.
- `FilmEditor.tsx`: main Film desk, sequence/source/transport state and operations. Playback correction complete; preserve rendered/live-preview mode behavior.
- `fcpFilm.css`: FCP-style Film shell; `editor.css` shared with legacy scene editor; `styles.css` broad base styling.
- `FilmGeneration.tsx`, `GenerationFlow.tsx`: take controls, destinations, job state and metadata.
- `FilmReferences.tsx`: reference-image controls.
- `FilmShotPlan.tsx`: audio-led shot assignments.
- `AudioWorkspace.tsx`, `AudioImport.tsx`, `AudioWaveform.tsx`, `useProgramAudio.ts`: audio tools/transport.
- `MusicGeneration.tsx`: ACE-Step music UI.
- `FilmStory.tsx`: bounded FMV authoring/rehearsal.
- `EditorView.tsx`, `SequenceTimeline.tsx`, `EditorCanvas.tsx`: older Scene animation editor, preserve.
- `shortcuts.ts`, `KeyboardLayout.tsx`: saved command map and reference.
- `api.ts`: shared /api calls with X-LLR-Client header; preserve payload/error behavior.
- `last_light_radio/server.py`: HTTP routes.
- `film.py`, `audio_tracks.py`, `film_generation.py`, `generation_timeline.py`, `film_shot_plan.py`, `film_story.py`: backend contracts; not Claude's UI-only scope.
- `.local/film-studio/studio.sqlite3` plus film/audio/masters/candidates/exports/etc.: live creator data, not test fixtures.

## Run and verify

`OPEN_FILM_EDITOR.bat` invokes quickstart with port 8769 and `.local/film-studio`. Plain quickstart defaults to a different library/port, so do not accidentally show an empty/older studio and call it data loss.

Frontend:
```powershell
cd C:\Users\thisi\OneDrive\Documents\repos\last-light-radio\frontend
npm run check
npm run build
```
Build is TypeScript then Vite. Existing packages are React 19/TypeScript/Vite. Preserve lockfile/runtime choices; no framework rewrite or dependency install without a specific need.

Backend regression when appropriate, with the project's working Python environment:
```powershell
python -m unittest discover -s tests
python scripts/check.py
```
Read run scripts if Python/npm are not on PATH. Do not substitute a random interpreter and assume a missing dependency is missing everywhere. Last dated broad evidence was 302 tests with one existing Windows skip, not a fresh result for your changes.

Acceptance checks after UI changes:
1. Correct working library opens with current real projects; no data/approval/revision loss.
2. Browser/Viewer/Canvas/Timeline remain stable at the user's window size; no inaccessible clipped controls.
3. Play full chorus across all cuts: no black/white flash, sound restart/double-up or unexpected skip. Distinguish live-preview issues from exported media.
4. Space works with timeline bar/clip/button focus and leaves actual text editing alone; source vs sequence transport is understandable.
5. Select source, mark In/Out, append on a disposable cut; trim/save/reopen, undo/redo, switch with dirty edits and cancel safely.
6. Audio-only sequence remains usable; waveform, markers, audio controls and continuous bed survive adding picture.
7. Open generation/ref/reference/shot plan/music tools without displacing Canvas or hiding timeline. Do not generate merely to test layout.
8. Pending/failed/completed/review/place states are honest; metadata such as seed, model, time and references is reachable.
9. FMV rehearsal and return-to-editor preserve the cut/playhead; legacy Scene animation still opens.
10. Exported chorus still decodes/playbacks; inspect console/network errors and report actual checks, not “looks good” alone.

## Suggested UI treatment order

1. Inventory real screenshots and existing operations, read the completed playback-fix QA, and checkpoint current source.
2. Improve spacing, hierarchy, typography, pane sizing, selection/focus and timeline legibility within the familiar shell.
3. Unify custom tool panels without flattening technical metadata or hiding advanced controls.
4. Improve generation progress/candidate comparison/placement clarity.
5. Test the above real workflows and provide before/after screenshots plus a concise changed-files list.

Do not spend the UI pass generating more content, reworking backend semantics, migrating data or rebuilding a new editor beside this one. Finish with a short handoff back: changed UI files, behavior preserved, tests actually run, known gaps, and any proposed backend work that needs coordination.



