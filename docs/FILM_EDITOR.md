# Film editor - first linear assembly milestone

Open `OPEN_FILM_EDITOR.bat`, or http://127.0.0.1:8769 while it is running. This is a persistent working library at `.local/film-studio`, not the earlier audio-test fixture. Original Last Light Radio library `.local/studio` remains separate and unchanged.

## Hierarchy
- **Project** contains independently named sequences.
- **Sequence** contains an ordered list of shots plus independent production sound and music placements. Saving one cut does not replace another cut using the same sources.
- **Source take** is immutable imported MP4 media with a hash, provenance and review decision. A shot references a frame range from that source; trimming never edits source bytes.
- **Scene animation** is the preserved Last Light Radio single-environment composer. It is not a project or film sequence. Its completed export can be imported as one source shot through the completed-scene import in the same library, or as an MP4 between libraries.

## First working project
`Film pipeline - first cut` contains `Reading + page turn` (two existing approved moving takes, 214 frames / 8.917 seconds) and an independent shorter alternative. The first cut uses the actual ACE-Step discovery cue. Imported video approvals carry forward the exact source hashes and existing approved candidate IDs; the music records the user's acceptance of that tested output, not final soundtrack approval.

These are existing local assets, not a newly scripted/generated short film. The later actual H3 proof below adds the manually transferred bell test.

## Current workspace: stable FCP7 editing desk

The restored operational layout is **Browser left / Viewer center / Canvas right / full-width Timeline below**, using the original editor pane styling and keyboard registry. The earlier scrolling/card arrangement is superseded. Existing sequence IDs, source hashes, revisions, generation adapters and exports are unchanged.

1. Choose a project and named sequence in **Browser**. New-project/sequence forms and import tools are collapsed there; source takes remain in the Browser bin.
2. Audition a source in **Viewer > Video**. Source **I/O** marks define the real frame range used by **Append approved shot**; they do not change the sequence until appended. Explicit review still gates production placement.
3. **Canvas** always displays the sequence. Viewer **Audio**, **H3 take**, and **Music cue** tabs expose custom tools without replacing Canvas or moving the Timeline. Audio library audition/review works without any picture sequence.
4. The bottom Timeline displays proportional **V1 picture / A1 production / A2 music** positions. Select a shot and edit its source In/duration or order. Music/production lane selection opens audio controls in Viewer. Named sequence tabs switch cuts, with dirty-edit protection.
5. Save the sequence and Export film. The exported file remains the exact timing/mix reference; browser picture cuts and streaming audio sync are approximate.

### Supported keyboard behavior
The existing saved FCP7 keymap is reused. Commands follow the highlighted active pane: **Ctrl+1 Viewer, Ctrl+2 Canvas, Ctrl+3 Timeline, Ctrl+4 Browser; Q Viewer/Canvas**. Text inputs retain typing, native undo and arrow behavior; window-focus commands and Ctrl+S remain available.

- **Space** plays/pauses the active source or sequence at 1x. **K** stops. **L** shuttles forward 1/2/4/8x; **J** reverse-reviews picture by frame stepping. Shuttle sound is muted outside 1x; reverse is not sample-accurate audio playback. Combined K+J/K+L is not implemented in this Film adapter yet.
- **Left/Right** step one frame; **Shift+Left/Right** one second; **Home/End** go to boundaries.
- With Viewer/Browser active, **I/O** mark source frames, **Shift+I/O** seek those marks, **Alt+X** clears them. Sequence range marking is not yet implemented.
- **F** matches the current sequence frame into its source Viewer, including source trim offsets and final-frame clamping.
- **Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y** undo/redo sequence edits; **Ctrl+S** saves the dirty sequence.
- **Ctrl+= / Ctrl+-** zoom the timeline; **Shift+Z** fits it. Zoom does not change media duration.

No fake overwrite/slip/ripple commands are exposed. Current shot assembly is contiguous straight cuts; those deeper operations need real document-model support. The preserved scene-animation toolset retains its own richer established keyboard behavior. Do not treat every command in that registry as implemented in Film.

### Restoration verification
Checkpoint: `artifacts/film-fcp7-restore-20261113/before-frontend`. Browser verified the restored pane geometry, persistent Canvas while H3 tools were open and playing, V1/A1/A2 in the actual bell proof, source marks 1..25 producing an appended 25-frame range starting at frame1, dirty-switch guard, undo restoring the unchanged two-shot cut, one-frame Canvas steps, reverse review, 2x rate selection, match-frame to source second1, and 150%/100% timeline zoom/fit. Test source append was undone without saving. ACE-Step preflight passed read-only in Viewer, with blank-seed blocking and edit invalidation; no Generate was clicked. Existing two-shot and bell proof revisions remain unchanged. Screenshot: `artifacts/film-fcp7-restore-20261113/restored-fcp7.jpg` (visually inspected at 1036x854). This is not subjective soundtrack listening approval.

## Earlier linear-assembly scope (historical checkpoint)
This is a first cut editor: contiguous straight cuts, frame-based source ranges, 24 fps, 720p/1080p output, explicit review, saved revisions, export manifests. WAV and MP4 imports are limited to 20 MiB per file and sequences to ten minutes. It is not yet a full NLE: no draggable/ripple trimming, transitions, waveform editing, script/storyboard manager, direct ACE-Step job adapter or FMV branching. Existing H3 scene generation remains in Scene animation. Nothing generates new story decisions during deterministic assembly.

Backend proof: the first export fully decodes all 214 frames at24fps, 1280x720 with verified presentation timestamps and mixed48kHz audio. Report: `artifacts/film-sequences-20261113/real-demo.json`. Source hashes match the untouched originals. Final regression/UI evidence is recorded in the milestone notes.

## Existing H3 take bridge and live audio preview

Film now offers a route to the existing H3 generation workspace and a completed-take import selector. This reuses existing owned jobs, exact saved recipes and receipts rather than introducing another queue. Completed same-library MP4 takes are imported through hash-verified copies with full generation receipt snapshots and remain pending Film review. Nothing queues a GPU job just by opening this interface.

At the take-bridge checkpoint the new film library had no motion recipes; the later reference-recovery checkpoint below restores one exact existing recipe. Import/select a canonical reference and create or select a recipe in the existing workspace before an explicit Generate action. The recovered installed recipe is VIDEO-ONLY H3 motion, not the newer joint audiovisual bell-test workflow. That exact audiovisual workflow still needs separate transfer/validation. No new creative generation was submitted in this milestone.

Program audio streams approved production/music placements with trim/start offsets, gain/fades and pause/end behavior. Original embedded video sound remains muted to avoid doubling. Browser preview is approximate and resource-bounded (32 enabled audio placements); export supports the validated full mix. Live sync is not a substitute for exported timing checks.

Backend regression:228 tests ran,227 passed and one existing Windows permission skip;66 Python files checked clean. Eight focused Film tests include two no-generation take-bridge tests. Evidence: artifacts/film-take-bridge-20261113/full-tests.log. Browser observations include a real cut crossing with video/audio timestamps approximately1ms apart at the sampled moment, correct-9dB gain, both sources pausing, and source-In/timeline-offset trim behavior. This is not a universal latency guarantee or subjective audio-quality review.

## Reference recipe recovery - 2026-11-13
One existing image-conditioned recipe is now available in Scene animation / Motion studio for the Film library's reading-room reference: the previously tested 39-frame sleeping-cat breathing recipe, seed29401, explicit INT8 video VAE. Its immutable profile, canonical reference and mask assets were copied and hash-verified unchanged from the original library. No job was submitted and no creative/source approval was added. This is the separate video-only reference-conditioned path, not reference conditioning for the joint-AV bell recipe. Evidence and destination database checkpoint: artifacts/film-reference-recipe-20261113/verification.json and before.sqlite3.

## Joint video + sound generation
In **Viewer > H3 take**, expand **Generate a film take - H3 video + sound**. Enter a take label, a shot-and-sound brief and a seed. **Check worker & recipe** is read-only on the worker; it does not queue a render. A successful check enables **Generate video + sound** for those exact settings for ten minutes. Editing settings requires another check. Only the explicit Generate action creates an owned job.

This first recipe is the inspected successful H3 text-to-audiovisual graph: 672x384,124frames at24fps,eightsteps. It does not condition on a reference image. For image-controlled motion, use the separate Scene animation / Motion studio path and its saved pose/mask recipe. Do not confuse the two workflows.

Jobs retain an immutable brief, seed, resolved graph, model names, worker evidence, accepted prompt and completion history. Interrupted polling resumes the accepted prompt, never resubmits it. An uncertain submission without a receipt is blocked rather than guessed. Completed video stays byte-identical; its embedded sound is decoded into a separately reviewable PCM source, with recorded AAC-tail clock adjustment. Import explicitly, review video and sound separately, then append the shot and place production sound in Sound & music. The Program video stays muted so the separate production lane is not doubled. Imported output is not automatically placed or approved.

Compatibility was checked read-only against Harbinger with no errors/warnings and zero submitted jobs. Mocked lifecycle tests cover output ownership, exact settings, retry/uncertain submission and interrupted import. No new creative generation has been run through this integration. The original successful bell-test media remain on Harbinger because the supported Windows file-transfer helper failed; they have not been imported into Film. ACE-Step's accepted WAV is already in the Film library, but direct music job submission remains future work. FMV branching is not implemented.

## Actual H3 audiovisual proof - 2026-11-13
The user manually saved h3-bell-editor-package-20261113.zip to Downloads, resolving the transfer blocker. The five expected files passed ZIP CRC/path checks; source workflow raw hash matched the inspected Harbinger workflow, and its canonical graph matched the installed adapter. Original MP4 and extracted WAV are now imported with full package metadata and an explicit note that this is the previously completed test, not a new Film-owned job. Tested-source acceptance carries forward the user's earlier 'both things worked fine', not approval of a final film.

A separate named sequence, **H3 bell + music - pipeline proof**, combines the original bell picture, production sound and accepted ACE-Step cue. It exports124frames at24fps,672x384, with48kHz stereo mix. The original embedded sound stays muted; only the two separate lanes mix. Complete decode/presentation timestamps passed, source MP4 remains byte-identical and both prior cuts are unchanged. Browser playback completed5.166667seconds without media error. This is a technical pipeline proof, not a directed short film. No new GPU job was submitted.

Evidence: artifacts/h3-real-av-20261113/verification.json. The supported automatic Library transfer limitation remains, but it no longer blocks these manually downloaded inputs.


## Integrated FMV toolset (current bounded milestone)
Use **Viewer > FMV** without changing the Browser/Viewer/Canvas/Timeline shell. Each project owns one named story document. Add named nodes, bind each to a saved sequence in that same project, choose the start node, and either mark a terminal ending or add up to eight end-of-clip choices targeting other nodes. Cycles are allowed; unreachable or invalid graphs cannot become playable exports. Save/discard and story undo/redo are distinct from sequence edits. Unsaved story edits block project/sequence navigation even after switching Viewer tabs.

**Freeze playable export** uses already completed, verified sequence renders. It pins the sequence revisions, media hashes and review provenance; it does not render, generate, or overwrite source media. **Rehearse in Canvas** reads the frozen manifest, plays its mixed movie, and exposes choices only after playback ends. Native replay/seek hides those choices until a new ending. Terminal nodes show completion. Restart returns to the start; Exit returns to the ordinary sequence editor and its playhead. Timeline editing is disabled during rehearsal. Loops stop after at most 256 transitions. Missing, revoked or tampered sources fail visibly rather than substituting another clip.

This is sequence-level branching, not a full Titanic runtime: no timed/spatial hotspots, inventory, game variables, conditional choices, dialogue interruption, or game packaging yet. Generation controls remain separate explicit actions.

Browser verification uses the isolated **FMV branch rehearsal - verification** project, not the creator's original cuts. Saved story revision 1 links Opening test to Bell test (terminal) or Alternate test (return to Opening). The frozen manifest is retained in that project; source media and the three original Film pipeline sequences are unchanged. Checkpoint and fixture/export evidence: `artifacts/film-fmv-20261113/`.

FMV frontend QA: artifacts/film-fmv-20261113/frontend-qa.json; inspected screenshot fmv-rehearsal.jpg in the same folder. Native replay at time0 had no choices; exit restored Canvas to01:00 paused with both story/sequence clean. The 256-transition bound is implemented but was not manually exhausted. Final tested frontend: index-BV6O6Pq5.js.

## Reference-frame controls (current, 2026-11-13)
The unchanged Viewer H3 take tab now includes optional first/last reference slots. Choose an immutable image from the reference library, import PNG/JPEG/WebP, or select a video in Browser, position its Viewer playhead, then Capture selected Viewer frame. Frame numbering uses Film's 24fps source clock, not a native camera frame number. The slots show thumbnails and provenance. No slot means text-only generation.

Reference changes invalidate preflight. Only explicit Generate uploads selected references to the worker and submits a job; image import/frame capture only creates local immutable sources. Last-frame verification follows the recipe's tested flag and shows an experimental warning when false. Final generation and imported clip metadata retain references. Saved project/sequence edits are unaffected by setting reference drafts.

Actual QA and limitations: artifacts/film-reference-ui-20261113/QA.md. Generation destinations use real striped pending blocks, separate technical review, and explicit placement; they are not approved clips until placed.

## Audio-first and continuation tools (current)
In the existing Timeline, expand **Sequence duration / audio-first** and set a duration before adding picture. Save it, then use Viewer Audio to import/review/place A1/A2 sources. Audio-only sequences play without a picture placeholder clip and export a real WAV. Adding approved picture preserves the explicit duration; uncovered time is black while sound continues. Source and track waveforms are calculated from actual canonical PCM samples. Click the Viewer waveform to seek its original audition. Waveforms display source amplitude, not gain/fade-adjusted mix amplitude.

**Selection & markers** stores an exclusive-Out range and named cue frames in the sequence. These do not trim media or perform lip-sync. Current audio-only transport supports normal play/pause/seeking; fast/reverse audio scrubbing is not implemented.

**Continue this shot** in the existing shot controls requires a clean saved cut with a current completed export. It prepares the actual rendered last USED frame, preserving trims, image hash and source revision. The H3 Viewer receives a locked first reference and adjacent destination; edit the brief and explicitly check/generate. New picture and sound still require separate review and explicit placement. Continuation placement skips one generated picture frame and starts paired sound at the same one-frame offset. This is conditioned reconstruction, not pixel-identical continuity or a roll edit. Changed source revisions require fresh preparation, never silent retargeting.

For ordinary generated-picture placement, **Keep audio timing** versus **Ripple later audio** is explicit. Audio-only cuts default to preserving the existing sound bed. Anchored continuations retain their fixed ripple policy. This is not a general overwrite/slip tool.

QA: artifacts/film-audio-first-ui-20261113/STAGED.md, audio-first-verified.jpg and continuation-running.jpg. Existing FCP7 panes remain fixed.

## Audio-led shot assignments (current)
Use Timeline Selection & markers to mark a range, save the sequence, then **Make shot from selection**. The existing Viewer **Shot plan** tab stores ordered contiguous intervals from frame0, each with a brief and optional first/last reference roles. Save the plan. After unrelated sequence changes, explicitly review/re-anchor the plan before fitting or generating.

**Prepare generation for this interval** opens the existing H3 tool with the exact saved assignment bound. Brief/reference roles stay locked to that plan revision; edit them in Shot plan and prepare again. Preflight is read-only; Generate remains explicit. The current124frame recipe cannot generate longer intervals, so choose a longer existing take or split the assignment instead. Planned jobs show V1-only interval placeholders, never implied A1 sound placement.

Add existing sources as alternatives or review owned generated takes. **Fit picture to interval** requires approved video and explicit permission to trim a longer take. Short sources are rejected, never stretched or looped. Fit appends at the next contiguous picture boundary or replaces one exact interval. Existing audio, overall explicitduration and markers remainfixed. Generated source audio is not required or automatically placed. These are not general overwrite or gap-editing tools.

Verified15s example: FABLE - audio-led shot planning / FABLE - planned picture over fixed music (15s excerpt), sequence revision6, planrevision3. It reuses actualapproved calibrationmedia over an explicitly excerpted15sACEcue. QA/screenshots: artifacts/film-shot-plan-ui-20261113/QA.md and shot-plan-verified.jpg.

### Whole-song import and music controls (2026-11-13)
The existing Audio Viewer WAV chooser supports original WAV files up to256MiB/600s when the server advertises binary upload. It sends the File directly, reports transferred bytes, then reports decoding/verification without a guessed percentage. A stopped/lost connection can leave processing completed: Refresh audio library before retrying. Originals are content-hash deduplicated; no import approves or places a source. Old servers retain the20MiB fallback.

The Music cue Viewer retains the proven30s instrumental recipe and adds a separate180/210/240s versioned recipe. Whole-song duration and vocals are API-compatible, not yet live-render-verified. Enter full lyrics/section tags and optional structure in the same pane; Instrumental sends no lyrics but preserves your draft for switching back. Every relevant edit invalidates preflight. Generation is always explicit. Source/job metadata separates requested, provider-reported and decoded duration and elapsed request time.

Verification: UI preflight/draft/invalidation passed without generation; binary HTTP180s import independently passed and candidate metadata was inspected in the browser. Browser file-picker upload remains unverified because the Chrome extension lacks file-URL access; no extension setting was changed. Evidence artifacts/film-whole-song-ui-20261113/QA.md. No existing timeline changed.

## UI treatment (2026-11-13)
The desk arrangement, commands and tool tabs are unchanged; presentation was refined. New conveniences, all UI-only: a source filter in the Browser, a draggable divider between the monitors and the Timeline (double-click resets), a zoom percentage, and sequence selection/markers drawn on the ruler. The Canvas header names the playback mode (Rendered playback vs Live edit preview); the full explanation remains beneath the transport. Status is always given as a word or glyph as well as a colour. Details and what was and was not tested: `artifacts/ui-treatment-20261113/QA.md`.

### FCP7 editing commands (2026-11-13)
- Click a V1 shot or audio clip to select it; it no longer moves the playhead (use the ruler, Up/Down or typed timecode).
- F9 Insert, F10 Overwrite, F11 Replace (also buttons under the Canvas); Shift+Delete ripple delete; Delete removes a selected audio placement.
- Alt+R Render (same as Export film; saves unsaved edits first, refused if the library has a newer revision). Browser rows: click selects, double-click or Enter opens. Sequence timecode reads from 01:00:00:00 (display only). Ctrl+Alt+S Save all. Unsaved sequences keep their edits while you switch; the ruler's top bar is red when the cut needs rendering, green when rendered.- Gaps and trims (2026-11-15): Delete lifts (leaves a gap), Shift+Delete ripple-deletes. Tools: A Selection, B Razor (click a clip to cut), R Roll / R again Ripple, S Slip. V selects the edit nearest the playhead, U cycles Out side / both / In side, `[` `]` trim by a frame (Shift: 5) or slip the selected shot with the Slip tool, Ctrl+V cuts at the playhead, E moves the selected edit to the playhead. Audio placements stay put on trims and slips. If an edit shortens the picture of a sequence without a fixed duration, markers past the end are removed, In/Out is clamped, and placed audio holds the length.- Mouse trims (2026-11-15): with Roll or Ripple, drag the handle on any edit point (Ripple: left half = Out side, right half = In side; at the sequence start or end, Roll also ripples because there is only one side). With Slip, drag a shot to slip its source. Drags preview live, stop at the take's limits, and are one undo step.
- Drag to move (2026-11-15): with the Selection tool, drag a shot more than 4 px to overwrite-move it (its old place becomes a gap; it covers what is at the drop point). Hold Alt at release to rearrange instead (old place closes up; it goes in at the nearest cut). Snapping (N, on by default, magnet button in the timeline bar) pulls the shot's start or end to cuts, the playhead, markers and In/Out. A plain click still selects; double-click still opens the shot in the Viewer.
- H3 take panel (2026-11-15): brief and references first, worker / seed / recipe under Settings. Generate video + sound runs the worker check itself and submits only if it passes; if the passing check has warnings, they are shown and the button becomes 'Generate video + sound anyway' (second click submits). Takes are cards with a stage and the next step; this sequence's takes by default, Show all for the rest, placed takes under Done.
- Generation guide (2026-11-16): click a striped requested-take block for what it is and what to do next, or Guide me (queue line, block card, H3 take panel, take cards) for a step-by-step panel whose Show me buttons open the right tab and highlight the control. Hide from timeline tidies a block on this computer only (Show hidden brings it back); the request itself can only be cleared by placing the take until the server gets a withdraw route.
- Takes and History (2026-11-17): a generated take is reviewed once in the Viewer: one tick, Approve take approves the picture and its production sound together; Reject take needs a reason in Review notes and rejects both. Every generation run (picture + sound takes and music cues) is listed in the Viewer's History tab with its next step; the H3 take and Music cue tabs no longer list jobs.
- Generate tab (2026-11-17): one Generate tab (Picture + sound / Music cue). For a take, choose Where it goes: playhead, before or after the selected clip, end of sequence, or library only. A flag marks the spot on V1 (click it to place, move or remove). After you approve the take, Place in History (or on the flag) inserts the picture and its sound together as an unsaved edit; choose whether existing audio moves with it.
- Decision (Boden, 2026-11-17): O at a cut keeps FCP7 behaviour (marks the frame under the playhead, so Down, I, Down, O includes the next shot's first frame). Use X to mark a shot exactly.
- Lift / Extract In to Out (2026-11-17, Premiere keys): mark In and Out (I, O), then `;` lifts the range (shots are split at In and Out, a gap is left, later shots stay put) or `'` extracts it (split, removed, later shots close up and the sequence gets shorter). Production sound (A1) and music (A2) in the range are cut the same way (Boden: cut music too). In/Out is cleared afterwards; Ctrl+Z undoes. Previous / next edit stays on Up / Down.
- Audition, thumbnails, menus (2026-11-17): Audition here / Audition in context plays a take at its spot between its neighbours (2 s either side) with its sound, without placing it (Space, Esc). Browser rows and V1 clips show poster frames. A menu bar (File, Edit, Mark, Sequence, Tools, Playback, View, Window, Help) lists every Film command with its current key.
