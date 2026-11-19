# Brief for dot: gaps on the picture track (V1)

From: the Film editor UI session, 2026-11-14. Boden chose gaps as the first stored-format change (FCP7 plan `docs/FCP7_ALIGNMENT_PLAN_2026-11-13.md`, item 4.9; decision 7).

## Why
V1 is contiguous today: shots are laid end to end from frame 0 and only the tail after the last shot may be empty (black). That blocks three everyday FCP7 edits:
- **Lift** (Delete): remove a shot and leave its space, so later shots don't move.
- **Overwrite / Insert past the end of the picture** with an explicit timeline duration: the UI currently refuses with "V1 cannot hold gaps yet".
- **Leave room for a shot not generated yet**: hold a slot of known length in the cut.

## What exists now (read from `last_light_radio/film.py`)
- `save_sequence` (around line 173) walks `payload['shots']`, requires each to reference an approved asset, and sets `start_frame` by accumulating `duration_frames` (a `cursor`). No item can be empty.
- Black after the picture comes only from `timeline_duration_frames > picture_duration`; the renderer pads the tail (around line 423).
- The plan-fill route (around line 253) raises "Place picture contiguously from frame zero ... gaps and partial overlaps are not supported".
- Saving resets `export` to draft; the export report carries `manifest_hash`, which the UI compares to decide whether the render is current. Please keep both behaviours.

## Suggested shape (your call; tell the UI side what you pick)
A gap is an item in the existing `shots` list, so order and `start_frame` stay as they are:
```json
{ "id": "<uuid>", "kind": "gap", "duration_frames": 48 }
```
- No `asset_id` and no `source_in_frame`; approval checks are skipped for it.
- Shots without `kind` stay video shots, so existing sequences load and save unchanged (no migration).
- `start_frame` keeps accumulating across gaps; `picture_duration_frames` = end of the last item, gap or shot.
- Renderer: a gap renders black of its length, as the tail pad does now.
- Manifest hash: include gaps so a moved gap makes the render stale.
- Validation suggestions: duration >= 1; two adjacent gaps either merged on save or allowed (say which); a trailing gap could be allowed or folded into `timeline_duration_frames` (say which).
- Plan-fill route: allow filling a gap exactly (and splitting a gap when the fill is shorter), if that's cheap; otherwise leave it for a second pass.

## Out of scope for this change
Picture-sound linking (4.6, next), track mute/lock, markers, revision history. Audio tracks keep their own timing.

## Acceptance (no GPU needed)
1. A sequence saved with shot, gap, shot round-trips exactly (ids, order, lengths, `start_frame`).
2. Existing sequences (no `kind`) load and save with identical manifests and hashes.
3. Export of shot, gap(24), shot writes the right total frames, with frames in the gap black, fully decoded, PTS verified.
4. A gap with `duration_frames` 0, or with an `asset_id`, is refused with a clear message.
5. Ten-minute limit counts gaps.

## What the UI will do once it lands
Lift (Delete) leaves a gap; overwrite/insert past the picture end fills with a gap instead of refusing; gaps draw as empty slots on V1 and can be selected, trimmed and filled. The UI session will not touch `film.py` or the API; it only needs the final field names.

## Heads-up: UI changes on 2026-11-14 that may affect your browser tests
- Browser rows (sequences and sources) now **select on single click and open on double-click** (or Enter). A test that clicks a sequence row once to open it must double-click. Button text and aria-labels are unchanged.
- **Export film** (Render, Alt+R) now saves unsaved edits first, then exports. It is enabled while there are unsaved edits.
- Sequence timecode **displays** from 01:00:00:00. Stored frames and the API are unchanged; typing 1419 or 01001419 both go to 14 s 19 f.
## Heads-up 2: Browser changes (step 4, 2026-11-14)
- The Sources list now holds video, audio and stills. Bin chips sit above it: "Video 69", "Audio 67", "Stills 59", "All", "In sequence", "Unused", "Candidates", "Rejected 7". They come **before** the Viewer's Video/Audio tabs in page order, so a finder for the first button containing "Audio", "Video" or "Reject" may now hit a chip. Scope finders to `.ed-tabs` (Viewer tabs) or `.fcp-review` (Approve take / Reject take).
- The bin choice is remembered per browser profile (`localStorage` key `llr.film.bin.v1`). Click the "Video" chip first if a test needs video rows.
- New column header buttons: Name, Type, Status, Duration, Size, Created, Used, Seed, Model.
- Source rows are still `button`s in `.film-assets.fcp-bin` with the label in `<strong>`, plus `data-kind="video|audio|still"`. Filter keeps aria-label "Filter sources". Sources heading count is now the whole library (195), not video only.
- Right-click / Shift+F10 on a row opens a small menu (Open, Review in Viewer…, Reject). Reject asks to confirm and is disabled for sources in the open sequence.
## Heads-up 3: transport strips (step 4 slice C, 2026-11-14)
- The Viewer `<video>` no longer has built-in `controls`; clicking the picture plays/pauses. Use the strip buttons or keys instead of the native controls.
- Each monitor has a transport strip. New buttons carry `data-command` (e.g. `[data-command="nav.in"]`) and their accessible name is the `aria-label` (e.g. "Go to In (Shift+I)"), not the visible short text ("In", "Out", "Match").
- Unchanged text: "Mark In", "Play / pause", "Mark Out" (Viewer); "Play sequence" / "Pause sequence" (Canvas).
- New "Monitor volume" slider (aria-label) on each strip; it changes what you hear only.
- Play In to Out now stops exactly on the Out frame.
## Heads-up 4: the UI now edits gaps (step 5 slice A, 2026-11-14)
- Thanks for landing gaps. The UI uses exactly `{id, kind:'gap', duration_frames}` and never sends source fields on a gap.
- **The running service (python PID 22584, started 2026-11-13 11:52) predates your `film.py` change (2026-11-14 11:56)**, so saving a gap is refused until it is restarted. Nothing with a gap has been saved.
- Delete now **lifts** (replaces the selected shot with a same-length gap) instead of showing an error. Shift+Delete still ripple-deletes (shots or gaps).
- Overwrite/Insert past the end of the picture now pad with a gap instead of refusing.
- Gaps draw on V1 as `button.fcp-gap[data-kind="gap"]` inside `.fcp-track-video .fcp-track-clips`, aria-label "Gap, N frames". **A clip count by `.fcp-track-clips > button` now includes gaps**; filter with `:not([data-kind="gap"])`.
- Adjacent gaps are merged in the UI. Generation placement (`insert_index`) counts gaps as items; the plan-fill route still refuses gaps (film.py ~308).
## Heads-up 5: trim tools (step 5 slice B1, 2026-11-15)
- New keys in the Film editor: A Selection, B Razor, R Roll (R again = Ripple), S Slip, V select nearest edit point, U cycle edit side, `[` / `]` trim or slip 1 frame (Shift = 5), Ctrl+V add edit at playhead, E extend edit to playhead. A browser test that types these letters with focus outside a text field will now change tools or cut V1.
- Tool palette sits in the timeline bar: `.fcp-tools button[role=radio][data-tool=...]` with `aria-checked` (not `aria-pressed`, so `.fcp-timeline button[aria-pressed]` selectors are unaffected).
- With the Razor tool, clicking a V1 clip cuts it instead of selecting it.
- When an edit shortens the picture and the sequence has no explicit duration, the UI now keeps placed audio whole by setting `timeline_duration_frames` to the audio end, drops markers past the new end and clamps In/Out, so saves are not refused.
## Heads-up 6: mouse trims (step 5 slice B2, 2026-11-15)
- With the Roll or Ripple tool, every V1 edit point gets a drag handle: `.fcp-track-video .fcp-track-clips > i.fcp-edge` (an `<i>`, not a button, so clip button counts are unchanged). Handles sit above the clips, so with those tools a pointer at a cut hits the handle, not the clip.
- With the Slip tool, pressing on a video clip starts a slip drag. The edit applies on release; while dragging, V1 shows a preview and a `.fcp-drag-readout`.
- With Selection (A, the default) nothing changed.
## Heads-up 7: drag to move + snapping (2026-11-15)
- With the Selection tool (default), pressing on a V1 video clip and moving more than 4 px starts a move. A plain click still only selects. Overwrite move: lifts the clip (gap left behind) and overwrites at the drop point; trailing gaps are dropped. Alt at release: rearrange (close up the origin, insert at the nearest cut).
- Snapping (N, on by default; toggle button `.fcp-snap` in the timeline bar) snaps the clip start or end to cuts, the playhead, markers and In/Out.
- Also see `docs/GENERATION_FLOW_REVIEW_2026-11-15.md`, section B: four server-side items for the generate / audition flow (job flags after import, auto-import as candidate, continuations without a full render, gap-aware placement).
## Heads-up 8: H3 take panel reorganised (generation review A1-A3, 2026-11-15)
- Order: Shot brief, Take label, references / continuation / plan, Destination, **Generate video + sound**. Worker URL, seed, recipe details, "Refresh recipe & jobs" and "Check worker & recipe" moved into a folded `details.generation-settings` ("Settings · worker, seed, recipe"). Open it before reaching those inputs.
- **Generate video + sound** is enabled without a prior check: it runs the worker check itself and submits only if the check passes. "Check worker & recipe" still exists (optional, in Settings).
- Changing the take label or destination no longer clears a passed check (the server binds a check to brief, seed, worker, recipe and references only).
- Jobs are cards (`article.generation-card`, heading "Takes"): by default only this sequence's takes plus unimported library jobs; "Show all (n)" checkbox shows the rest. Placed takes fold under "Done (n)". "Import video & production sound" and "Check existing job (no resubmit)" now appear only when they apply (not after import). Button texts unchanged.
- Still for dot (review B1): `ready_to_import` / `can_resume` stay true after import; the UI now ignores them once `video_asset_id` exists.- Addendum: if a passing check has warnings, Generate shows them and its text becomes 'Generate video + sound anyway'; the next click submits.

## Heads-up 9 + request: requested-take blocks and the generation guide (2026-11-16)
- **Request (B5): a way to withdraw a timeline request.** A `film.generation.destination.<job>` record keeps a striped block on its sequence until the take is placed. Rejecting the take does not clear it, and there is no route to withdraw it, so a request you no longer want stays forever. Suggest `POST film/generations/<job>/withdraw` (expected_revision optional) that marks the destination withdrawn (keep the job, assets and provenance), and have `listing()` skip withdrawn records. Until then the UI offers "Hide from timeline", stored per browser only.
- Clicking a striped block now opens a small card (`.generation-block-card`) instead of jumping straight to the H3 take tab: Guide me / Show me: next step / Open its card / Hide from timeline. Hidden blocks: "Show hidden (n)" in `.generation-queue-status`.
- New optional floating guide (`aside.generation-guide`, opened by "Guide me" in the queue line, the block card, the H3 take panel and each take card). It never generates, imports, approves or places; "Show me" switches tab and highlights a control (`.guide-flash` for ~2.6 s).
## Heads-up 10: one review per take, History tab (2026-11-17)
- **One review for a generated take (Boden: picture and sound don't need separate approval).** In the Viewer, a take with linked production sound shows one tick "I watched and listened to this take"; **Approve take** calls the video review route, then the audio review route (fresh `version`), so both end up approved; **Reject take** does the same and is disabled until Review notes has text (both routes require notes to reject). If the second call fails, the UI says the picture is done and the sound is not, and the button becomes "Approve its sound too". Server unchanged.
- Browser row Reject (step 4) sent `notes: ''`, which the server refuses; it now asks for a reason (window.prompt) and rejects the linked sound too.
- **New Viewer tab "History"** (between Music cue and FMV) lists every H3 and music job as cards (`.film-history .generation-card[data-kind=take|music]`), this sequence by default, "All sequences" checkbox, type filter, Done fold. The job lists were removed from the "H3 take" and "Music cue" tabs (they now show a link to History). Button texts kept: "Import video & production sound", "Import music candidate", "Check existing job (no resubmit)". Placement cards show one "Review take" instead of "Review picture" + "Audition / review sound" when the take has a picture.
- Next (not built, please pause edits to `FilmGeneration.tsx` and `MusicGeneration.tsx` while it is done): one "Generate" tab replacing "H3 take" and "Music cue", with destination choices before/after a clip, at the playhead, at the end, or library only.
## Heads-up 11: Generate tab, take spots, client-side placement; ; and ' keys (2026-11-17)
- Viewer tabs are now: Video, Audio, **Generate**, History, FMV, Shot plan. "H3 take" and "Music cue" became one **Generate** tab with a `.generate-mode` switch (`button[role=radio]` "Picture + sound" / "Music cue").
- **New picture + sound takes are requested without a server destination** (library-only). "Where it goes" (`select[aria-label="Where the take goes"]`: playhead / after or before the selected clip / end / library) is stored in the browser (`localStorage llr.film.takeSpots.v1`, keyed by job id, clip ids not frames) and drawn as a flag on V1 (`span.take-spot`, not a button). Continuations and planned shots still use the server destination and place routes.
- **Placing such a take is a client edit**: History card (`.take-placer`) "Place at its spot / at playhead / after or before selected clip / at end" runs `insertEdit` for the picture and adds the take's production sound on A1 at the same start (role production, source in 0, length min(picture, sound)); "Existing audio" Moves with the picture (ripple, default) or Keeps its timing. It is an unsaved edit; the server's `film.generation.destination` record is not involved, so no striped block and no `placed_revision` receipt.
- Server B4 (gap placement) and B5 (withdraw) are less urgent now; B5 still matters for the 3 existing striped blocks.
- Keys: `;` = previous edit, `'` = next edit (FCP7), in addition to Up/Down.- Addendum to heads-up 11: keyboard layout files now carry `defaults_rev` (2). Older saved layouts get newly added default keys (`;`, `'`) unless the key is already bound. Wording 'H3 take' in FilmShotPlan.tsx and ProductionReferences.tsx changed to 'the Generate tab' (one line each).

## Heads-up 12: ; and ' corrected (2026-11-17)
- `;` is now **Lift In to Out** and `'` **Extract In to Out** (commands `edit.liftRange` / `edit.extractRange`), not previous/next edit. They split V1 shots at In and Out, then leave a gap (lift) or close up (extract); A1 production placements in the range are cut too (extract moves later A1 sound earlier); A2 music is untouched; In/Out is cleared. Keymap `defaults_rev` is now 3: layouts saved at rev 2 have ; and ' moved off previous/next edit.
- Addendum to heads-up 12: Lift / Extract now cut **all** audio placements in the range, music (A2) included (Boden's choice). A placement crossing the range is split into before-In and after-Out parts; Extract moves later audio earlier.

## Heads-up 13: audition dialog, thumbnails, menu bar (2026-11-17)
- **Audition in context**: `div.audition[role=dialog]` over the editor (Esc closes; Space plays/pauses; keys inside it do not reach the editor). Buttons "Audition here" (History take cards, flag card) and "Audition in context" (Viewer review panel of a generated take). It plays copies; nothing is written.
- **Thumbnails**: `span.fcp-thumb > img[alt=""]` (aria-hidden) inside Browser rows (new 48 px column; header row has one extra empty span) and V1 clips (`.fcp-clip-thumb`, hidden on clips under ~90 px). Button text and the `<strong>` label are unchanged. Captured in the browser and cached in `localStorage llr.film.thumbs.v1` (max 300).
- **Menu bar** in the title bar: `div.film-menubar[role=menubar]` with File, Edit, Mark, Sequence, Tools, Playback, View, Window, Help. Menu items (`.film-menu-list button[role=menuitem]`) exist only while a menu is open, so text finders for "Save sequence" etc. still hit the toolbar buttons. Items run the same commands as their keys.- Addendum to heads-up 13: the Browser rows gained a thumbnail child (second child, after the status mark), so child-index selectors on `.film-assets > button` shift by one. Title bar: below 1280 px the app name is hidden to make room for the menus.
