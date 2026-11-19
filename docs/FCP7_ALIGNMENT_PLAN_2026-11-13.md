# Film editor vs Final Cut Pro 7 - what to change so it flows

Written 2026-11-13 after the UI treatment. Scope: the Film editor (`frontend/src/FilmEditor.tsx` and its Viewer tools). This is a proposal list, not a record of work done, except section 0.

**How this was produced.** The "now" column comes from reading the current code and driving the running editor. The "FCP7" column is from working knowledge of Final Cut Pro 7; it was not checked against the FCP7 manual, and shortcuts marked (?) should be confirmed before binding. Mac keys are translated for Windows: Cmd -> Ctrl, Option -> Alt.

**Owner tags.** `UI` = can be done in the frontend with today's API and sequence model. `MODEL` = needs a change to the saved sequence document or a backend route, so it goes through dot. `DECIDE` = Boden's call first.

**Size tags.** S = hours, M = a day or two, L = several days.

---

## 0. Done in this session

| Change | Behaviour now |
|---|---|
| Double-click a source in the Browser | Opens it in the Viewer Video tab and makes the Viewer the active window. (Single click still loads it too - see 2.1.) |
| Double-click a shot on V1 | Opens *that shot* in the Viewer, as FCP7 does for a sequence clip: playhead at the shot's In, In/Out show the shot's own range, the scrub bar gets sprocket dots, the header reads "Timeline shot N", and the shot is flagged on the timeline. Mark In / Mark Out (buttons or I / O) now trim that shot in the sequence - an ordinary undoable, unsaved edit. |
| Double-click an audio clip on A1/A2 | Opens that audio source in the Viewer Audio tab for audition. |
| Double-click a sequence in the Browser | Opens it and makes the Timeline active. |

Limits: trimming a shot from the Viewer ripples later shots, exactly like the existing Source in / Duration fields. Alt+X does nothing while a timeline shot is loaded. Audio opened this way is auditioned, but its placement is still edited in the list below it rather than with In/Out.

---

## 1. The five things that most break the FCP7 flow today

1. **There is only one edit: append to the end.** FCP7's whole rhythm is mark a source, mark the sequence, press F9 or F10. Here a take can only be appended, then nudged with Move earlier / Move later. (Section 3.)
2. **The Timeline is a display, not a work surface.** Nothing can be dragged, trimmed by its edge, bladed or selected except by clicking a shot to jump to it. (Section 4.)
3. **Most of the keyboard is missing in Film, although the app already has it.** The older Scene animation editor implements K+J / K+L, Up/Down to edits, typed timecode, sequence In/Out, markers on M, mark clip on X, lift, nudge, overwrite, track height, the View menu and the editable keyboard layout. Film wires about a third of that registry. (Section 5.)
4. **You must save or discard before you can do almost anything else.** Unsaved edits block switching sequences, generating, placing and rehearsing. FCP7 never stops you from moving between open sequences. (Section 6.)
5. **Generation lives beside the editing model instead of inside it.** Destinations, placement and "keep audio / ripple" are their own forms. FCP7 already has the right metaphors - generators, offline clips, the render bar, replace edit - and using them would remove most of those forms. (Section 7.)

---

## 2. Browser

| # | FCP7 | Now | Change | Tags |
|---|---|---|---|---|
| 2.1 | Single click selects; double-click or Enter opens in the Viewer. | Single click opens; double-click also opens and activates the Viewer. | Make single click select only, with Enter and double-click to open. Changes a habit dot's scripts rely on. | UI S, DECIDE |
| 2.2 | One list holds everything: clips, audio, stills, sequences, bins. | Video sources only. Audio is a dropdown inside the Audio tab; reference images are dropdowns inside H3 take; sequences are a separate list. | Put audio sources and reference images in the Browser with type icons. Double-click audio -> Audio tab; double-click a still -> reference viewer. The list routes exist (`audio`, `film/images`). | UI M |
| 2.3 | Bins, and each project is a tab. | Flat list of 69 shared sources; project is a dropdown. | Automatic bins first (by sequence that uses the take, by generation job, "Unused", "Rejected"), since there is no stored folder model. User-made bins need storage. | UI M for automatic; MODEL for user bins |
| 2.4 | List view columns: Name, Duration, In, Out, Good, Label, Log Note, Comment; click a header to sort. | Name, status, duration. Filter box added this session. | Add columns: duration, size, status, seed, recipe/model, created, used-in count. Sort by header. Status filter chips. | UI M |
| 2.5 | Labels (Good Take, Best Take, Alternate Shots...) and the Good tick. | Approved / rejected / candidate, set at the bottom of the Viewer Video tab. | Keep the explicit review gate, but also show and set it from the Browser row context menu, the way Label is set in FCP7. Review notes become the Log Note column. | UI S |
| 2.6 | Icon view and hover-scrub thumbnails. | No thumbnails. | Poster frame per row, captured client-side from the media URL and cached. | UI M |
| 2.7 | Ctrl+F find, Ctrl+B new bin, Ctrl+N new sequence, Ctrl+I import. | Filter box; New project / New sequence / Import are collapsed forms. | Bind Ctrl+F to the filter. Ctrl+N and Ctrl+I are usually kept by the web browser - see 5.4. | UI S |
| 2.8 | Drag a clip from the Browser to the Canvas or Timeline. | Not possible. | Follows from 3.3. | UI |

---

## 3. Viewer, Canvas and three-point editing

| # | FCP7 | Now | Change | Tags |
|---|---|---|---|---|
| 3.1 | Insert (F9) and Overwrite (F10) at the sequence In point or playhead; Replace (F11) swaps the clip under the playhead, matching frames. | Append only. F10 is in the registry but not wired in Film; F9 and F11 are not in the registry. | Implement Insert, Overwrite and Replace on V1. A sequence is an ordered list of source ranges, so all three can be expressed today: insert splices (splitting a shot when the playhead is mid-shot), overwrite trims or removes whatever it covers, replace swaps the asset and keeps the duration. No stored-format change. | UI L |
| 3.2 | Three-point rule: any three of source In/Out and sequence In/Out define the edit. | Source In/Out only, and only I / O in the Viewer. Sequence range is set with buttons inside "Selection & markers". | Let I / O mark the sequence when Canvas or Timeline is active, using the existing `selection` field. Add X (mark clip), Alt+I, Alt+O, Alt+X, Shift+I, Shift+O for the sequence. Then apply the three-point rule in 3.1. | UI M |
| 3.3 | Drag from Viewer to Canvas shows the edit overlay (Insert / Overwrite / Replace / Fit to Fill / Superimpose); three coloured buttons sit under the Canvas. | "Append approved shot" button in the Viewer. | Add Insert / Overwrite / Replace buttons under the Canvas with their F-keys in the tooltip, plus the drag overlay. Leave out Fit to Fill (the project rule is no stretching) and Superimpose (one picture track). Keep Append as "Overwrite at end". | UI M, after 3.1 |
| 3.4 | Viewer tabs: Video, Audio, Filters, Motion. Generators come from a pop-up in the Viewer. | Video, Audio, H3 take, Music cue, FMV, Shot plan. | Keep Video and Audio as the clip tabs. Group the rest as tools: a "Generator" pop-up for H3 take and Music cue (see 7.2), with Shot plan and FMV as their own tabs. Fewer, steadier tabs. | UI S, DECIDE |
| 3.5 | Both monitors have the same transport: play, play In to Out, play around, jog, shuttle, plus mark buttons and editable timecode fields. | Viewer uses the web browser's built-in video controls plus a Play button; Canvas has a Play button and a slider. | One transport strip for both: go to In, play In to Out, play/pause, play around, go to Out, mark In, mark Out, add marker, match frame. Remove the built-in video controls and add a small volume control. | UI M |
| 3.6 | Type in a timecode field, or just type numbers with the window active, to jump or move by an offset. | Timecode is display only in Film. The Scene editor has typed timecode. | Port typed timecode from the Scene editor: digits, `.` for 00, leading + / - for relative. | UI S |
| 3.7 | Match frame F; reveal master clip Shift+F (?). | F works. | Add "reveal in Browser" for the Viewer clip and the selected shot (scroll to and select the row). | UI S |
| 3.8 | Audio tab: waveform with In/Out, level and pan lines, drag hand to edit audio only. | Waveform and audition, then a form of numeric fields per placement. | Give the Audio tab the same In/Out marking as video and let F9/F10 place onto the targeted audio track (4.4). Keep numeric fields in a collapsed "exact values" area. | UI M |
| 3.9 | Item Properties (Ctrl+9) and Sequence Settings (Ctrl+0). | Clip metadata is a disclosure under the review controls; duration is a disclosure in the Timeline. | Ctrl+9 opens a properties panel for the selected clip: source hash, seed, model, recipe, references, review history. Ctrl+0 opens sequence settings: name, size, duration. Same data, expected places. | UI S |
| 3.10 | Viewer and Canvas can be resized against each other; Ctrl+U restores the standard layout. | Horizontal divider added this session; widths are fixed. | Vertical dividers between Browser / Viewer / Canvas, Ctrl+U to reset. | UI S |

---

## 4. Timeline

| # | FCP7 | Now | Change | Tags |
|---|---|---|---|---|
| 4.1 | Click selects a clip; the playhead moves only when you click the ruler. | Clicking a shot moves the playhead to its start; "selected" just means under the playhead. Audio clips cannot be selected. | Separate selection from playhead. Click selects (shot or audio placement), Shift/Ctrl extend, Ctrl+Shift+A deselects. The bottom strip becomes an inspector for whatever is selected. | UI M |
| 4.2 | Drag a clip to move it; drag with Alt to swap; Shift+Delete ripple-deletes; Delete lifts and leaves a gap. | Move earlier / Move later / Remove shot buttons. | Drag to reorder (a swap edit). Bind Shift+Delete to the existing remove, which already closes up. Plain Delete (lift) needs gaps - see 4.9. | UI M |
| 4.3 | Tools: Selection A, Ripple RR, Roll R, Slip S, Slide SS, Razor B, Zoom Z, Hand H. Drag an edit point to trim. | None; two numeric fields. | In order of value: Roll (move a cut, both shots change, length stays), Ripple (one side, length changes), Slip (move the source range under a fixed shot), Razor and Add Edit (Ctrl+V), Extend Edit (E). All are arithmetic on the current list of ranges. Slide and the Trim Edit window can wait. Show a small tool palette beside the Timeline. | UI L |
| 4.4 | Track header: source/destination patching, lock, visibility or mute, auto-select. | A label only. | Add a target control on A1 / A2 (where audio edits land), a mute toggle and a lock. Mute and lock at track level are new stored state. | UI S for target; MODEL for mute/lock |
| 4.5 | Snapping (N) to cuts, markers and the playhead. | None. | Needed as soon as anything drags. | UI S, with 4.2 |
| 4.6 | Linked selection (Shift+L): picture and its sync sound move together. | Production sound from a generated take is an independent placement. Insert offers "Keep audio timing / Ripple later audio" per placement. | A stored link between a shot and its production-sound placement, so trims and moves keep sync, with one toggle that says whether edits ripple audio. Removes a choice the user currently makes take by take. | MODEL M |
| 4.7 | Clip overlays (Alt+W): level line on audio; drag to change gain. Fades via transitions. | Gain and fades are numeric fields in the Audio tab. | Draw the gain line and fade ramps on the audio clip and make them draggable. The values already exist. | UI M |
| 4.8 | Audio meters beside the Timeline. | None. | Meter the Canvas output. Works directly for rendered playback; live preview already mixes in the page. | UI S |
| 4.9 | Gaps and slugs; black where nothing is. | Picture is contiguous; only the tail may be uncovered. | A gap/slug item in the shot list so Lift, non-rippling moves and "leave room for a shot I have not generated yet" all work. The single most useful stored-format change. | MODEL M |
| 4.10 | Render bar above the ruler: red needs rendering, green or grey is done. | A badge in the Canvas says Rendered playback or Live edit preview. | Draw that state as a bar on the ruler as well. See 6.3. | UI S |
| 4.11 | Up / Down jump between edits; Shift+M / Alt+M between markers; M adds a marker, M again edits it. | Not wired in Film. Markers are added from a disclosure. | Port from the Scene editor. Double-click a marker to rename it. | UI S |
| 4.12 | Shift+T cycles track height; zoom slider; Alt+Ctrl+W waveforms on or off. | Fixed heights; - / + / Fit. | Port track height. Waveform toggle is cheap. | UI S |
| 4.13 | Several sequences open as tabs. | Every sequence in the project is a tab. | Tabs only for sequences you opened, with close buttons. | UI S |
| 4.14 | More than one video track; transitions. | One picture track, straight cuts. | Leave for now. Dissolves need render support. A V2 only earns its place with compositing. | MODEL L, later |

---

## 5. Keyboard

### 5.1 Works in Film today
Space, J, K, L (1x/2x/4x/8x), Left / Right, Shift+Left / Right, Home, End, I / O / Alt+X / Shift+I / Shift+O in the Viewer, F, Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y, Ctrl+S, Ctrl+= / Ctrl+-, Shift+Z, Ctrl+1-4, Q.

### 5.2 In the app's registry and working in the Scene editor, but not wired in Film
Port these first; the key handling already exists in `EditorView.tsx`.

| Keys | Command |
|---|---|
| K+J, K+L | Step a frame while holding K |
| Up, Down | Previous / next edit |
| I, O, Alt+I, Alt+O, Alt+X, Shift+I, Shift+O with Canvas or Timeline active | Sequence In / Out |
| X | Mark clip |
| Shift+\, \ | Play In to Out; play around current frame |
| Ctrl+L | Loop playback |
| M, Shift+M / Shift+Down, Alt+M / Shift+Up | Add marker; next / previous marker |
| Ctrl+`, Ctrl+Shift+` | Delete marker; delete all markers |
| F10 | Overwrite |
| Delete, Backspace | Lift (needs 4.9; until then bind Shift+Delete to ripple delete) |
| , . Shift+, Shift+. | Nudge / trim selected by 1 or 5 frames |
| Ctrl+Shift+A | Deselect all |
| Shift+T | Track height |
| Ctrl+U | Standard layout |
| Ctrl+F | Find in Browser |
| Alt+H or Ctrl+/ | Keyboard layout window |
| Page Up, Page Down | Previous / next take (see 7.5) |
| Typed digits, + and - | Timecode entry |

### 5.3 FCP7 defaults not in the registry yet

| FCP7 (Windows form) | Command | Depends on |
|---|---|---|
| F9 | Insert | 3.1 |
| F11, Shift+F11 | Replace; Fit to Fill (do not add Fit to Fill) | 3.1 |
| Shift+Delete | Ripple delete | exists as Remove shot |
| Ctrl+V | Add edit at playhead | 4.3 |
| E | Extend edit to playhead | 4.3 |
| A, R, RR, S, SS, B, Z, H | Tools | 4.3 |
| [ and ], Shift+[ and Shift+] | Trim selected edit by 1 or several frames | 4.3 |
| V, U | Select nearest edit; toggle which side (?) | 4.3 |
| N | Snapping | 4.5 |
| Shift+L | Linked selection | 4.6 |
| Ctrl+B | Enable / disable clip | exists as audio Enabled |
| Alt+W, Alt+Ctrl+W | Clip overlays; waveforms | 4.7, 4.12 |
| Alt+R, Ctrl+R | Render all; render selection | 6.3 |
| Ctrl+9, Ctrl+0 | Item properties; sequence settings | 3.9 |
| Shift+F | Reveal master clip (?) | 3.7 |
| Ctrl+U (Mac Cmd+U) | Make subclip - clashes with the registry's Standard layout on Ctrl+U | DECIDE |

### 5.4 Keys the web browser keeps
F11 (full screen), F12 (developer tools), Ctrl+N, Ctrl+T, Ctrl+W and, in a normal tab, possibly Ctrl+1 to Ctrl+8. Not tested this session. Opening the editor as its own app window (Chrome `--app=http://127.0.0.1:8769`) usually frees several of these; worth trying before choosing alternative keys. The keyboard layout window already marks reserved keys with "!".

### 5.5 Small fixes found while testing
- With the timeline playhead slider focused, Left / Right and Shift+Left / Right do nothing, because non-transport commands are skipped inside any input. Exempt range inputs, as was done for Space and J/K/L. `UI S`
- The status bar advertises only keys that work. Keep that rule as commands are added.
- Film has no entry point to the Keyboard layout window. Add it. `UI S`

---

## 6. Saving, rendering and export

| # | FCP7 | Now | Change | Tags |
|---|---|---|---|---|
| 6.1 | Unsaved changes never stop you switching sequences; Ctrl+S saves the project. | Unsaved sequence, story or shot-plan edits disable sequence switching, project switching, generation, placement and rehearsal. | Keep each sequence's unsaved draft and undo history in memory while you move around; mark dirty tabs with a dot; add Save All. Server-side actions that need a saved revision say so at the button instead of greying the whole desk. | UI M |
| 6.2 | Revert Project; Restore Project from the Autosave Vault. | Discard edits. Revisions exist on the server. | Rename to Revert. A revision list per sequence with open-as-copy needs a route. | UI S; MODEL for history |
| 6.3 | Edit freely; the render bar goes red; Alt+R renders; playback is then smooth. Export is a separate File command. | "Export film" does both jobs: it produces the file used for smooth Canvas playback and it is the deliverable. It is disabled until you save. | Present it as two commands on one mechanism. **Render** (Alt+R): save if needed, then build the review render; the ruler bar turns from red to green. **Export**: reveal or download the finished file and manifest. Same backend call. | UI M, DECIDE on save-then-render in one step |
| 6.4 | Sequences start at 01:00:00:00. | 00:00:00:00. | Display option only. | UI S, DECIDE |
| 6.5 | Menu bar: File, Edit, View, Mark, Modify, Sequence, Effects, Tools, Window. | A toolbar with six buttons; everything else is scattered through panels. | A real menu bar that lists every command with its shortcut, greyed when unavailable. This is where an FCP7 editor looks first, and it makes the command set discoverable without a manual. The Scene editor already has a View menu to build from. | UI M |

---

## 7. Fitting generation into FCP7's own ideas

FCP7 has no generative tools, but it has places where "media that is not here yet" already makes sense. Using them keeps new tools inside the desk instead of beside it.

| # | FCP7 idea | Use it for | Change | Tags |
|---|---|---|---|---|
| 7.1 | **Offline clip** - red "media offline", still has a name, duration and place in the edit. | A requested take that has not finished, or failed. | Show pending and failed jobs as offline clips in the Browser and on the Timeline (the striped block already does the Timeline half). When the job completes, the clip comes online as a candidate. | UI M |
| 7.2 | **Generator** - chosen from a pop-up in the Viewer, set up in a Controls tab, then edited in with F9 / F10 like any clip. | H3 take and Music cue. | Open them from a Generator pop-up. Drop the separate Destination form: the destination is the sequence In point and the targeted track, exactly as for any other edit. "Generate" then places an offline clip there. Payload stays the same (`insert_index` or `start_frame` derived from the In point). | UI M, after 3.2 |
| 7.3 | **Replace edit (F11)** | Fitting a reviewed take into a planned interval; swapping one take for an alternate. | "Fit picture to interval" and "Place reviewed clip" become Replace on the selected slot or shot. The trim-consent and too-short rules stay as the dialog. | UI M, after 3.1 |
| 7.4 | **Log and Capture / batch list** - log shots first, capture them later in a batch. | Shot plan. | Present planned intervals as logged, offline clips: a bin in the Browser and slugs on V1. "Prepare generation" is capturing one; a batch command queues several, each still needing an explicit go. | UI M; batch needs dot |
| 7.5 | **Multiclip** - several angles of one moment, viewed side by side, switched with a key. | Alternate takes of one shot. | Group candidates for a shot; show them as a grid in the Viewer; Page Up / Page Down cycles the take in place in the cut (non-destructive, undoable). The Scene editor's take comparison is the starting point. | UI L |
| 7.6 | **Render bar** | Rendered playback vs live edit preview. | See 4.10 and 6.3. | UI S |
| 7.7 | **Nested sequence** | A finished Scene animation used as a shot; an FMV node. | Show these with the nested-sequence icon; double-click opens the source sequence or the Scene animation tool. | UI S |
| 7.8 | **Markers with a type and comment** (chapter, scoring...) | Future FMV timed choices and hotspots; lip-sync or beat cues. | Give markers a type and note, edited by pressing M twice. End-of-clip choices stay as they are; timed ones would hang off typed markers. | MODEL M |
| 7.9 | **Continue this shot** has no FCP7 twin. | - | Keep it, but move it to the shot's context menu and the Modify menu rather than the inspector strip. | UI S |

Honesty rules that stay regardless of metaphor: no invented progress percentages, a generated clip is a candidate until reviewed, nothing generates without an explicit command, nothing is stretched or looped to fit.

---

## 8. FCP7 features to leave out on purpose

- **Fit to Fill, speed changes, time remapping** - conflict with the rule that media is never stretched.
- **Superimpose, composite modes, Motion tab** - one picture track; compositing belongs to Scene animation.
- **Filters tab, colour correction** - nothing in the renderer backs them.
- **Capture, Edit to Tape, Media Manager** - no tape, and provenance is handled by hashes and receipts.
- **Transitions** - until the renderer supports them (4.14).

---

## 9. Suggested order

1. **Keyboard parity and small fixes** (5.2, 5.5, 3.6, 4.11, 4.12, 3.7). All UI, mostly porting. Makes the editor feel familiar before anything structural changes.
2. **Sequence In/Out and real selection** (3.2, 4.1), then **Insert / Overwrite / Replace with Canvas buttons** (3.1, 3.3). This is the change that makes it an editor rather than an assembler.
3. **Unblock the desk** (6.1) and **Render vs Export with the render bar** (6.3, 4.10).
4. **Everything in the Browser** (2.2, 2.4, 2.5, 2.3 automatic bins), and one transport for both monitors (3.5).
5. **Direct manipulation** (4.2, 4.5, 4.3 roll / ripple / slip / razor, 4.7).
6. **Generation through the edit model** (7.1, 7.2, 7.3), then shot plan as logged clips (7.4) and alternates as multiclip (7.5).
7. **Menu bar** (6.5) can start any time and grow as commands land.
8. **Stored-format work for dot**, in value order: gaps/slugs (4.9), picture-sound link (4.6), track mute/lock (4.4), typed markers (7.8), revision history route (6.2).

Each step should end with the same read-only checks used for the UI treatment plus, for anything that edits, a save / reopen / render pass on a disposable sequence.

---

## 10. Decisions needed from Boden

1. Browser single click: select only (FCP7) or keep opening on single click? (2.1)
2. Group H3 take and Music cue under a Generator pop-up, or keep them as tabs? (3.4)
3. Should Render save the sequence for you in one step? (6.3)
4. Sequence timecode starting at 01:00:00:00? (6.4)
5. Ctrl+U: Standard layout (current registry) or Make Subclip (FCP7's Cmd+U)? (5.3)
6. Is it acceptable to launch the editor as its own app window to free browser-reserved keys? (5.4)
7. Which stored-format change should dot take first - gaps, or picture-sound linking? (4.9, 4.6)

### Answers (Boden, 2026-11-14)
1. Select only on single click; open on double-click.
2. Keep tabs (we are not implementing all of FCP7).
3. Yes: Render saves first, unless the draft conflicts with a newer revision (then refuse as now).
4. Broadcast convention: sequence timecode starts at 01:00:00:00 (display only; stored frames stay 0-based).
5. Ctrl+U stays Standard layout.
6. Yes: launch the editor as its own app window.
7. Open - Boden's call, then passed to dot.
