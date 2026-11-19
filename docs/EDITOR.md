# Scene sequence editor

Start `quickstart.bat` and choose a scene. The editor uses a Final Cut Pro 7
style arrangement: **Browser** on the left, source **Viewer** in the middle,
sequence **Canvas** on the right, and a large **Timeline** below. Drag the
horizontal divider to resize the monitors and timeline. **Library workspace**
opens the preserved earlier tools.

Use **View → All tracks overview** for a large Canvas above a full-width,
compact timeline. **View → Standard layout** returns to the usual workspace
and restores its previous panel height and track density. Standard is the
initial view. These choices affect only the workspace display.

The small **− / +** buttons in the timeline make tracks smaller or larger,
without changing the video preview size or horizontal time zoom. They stop at
Reduced and Large. The **Tracks** list also offers Original, Small and Medium;
Original restores the initial mixed track heights. Drag the lower edge of an
individual track header to resize it, or focus that edge and use Up/Down.
Choose All tracks overview again to reset custom heights and fit the stack.
**Fit sequence** separately fits the whole episode or opened nest horizontally.

## Create, audition and place an action

To add a new subject today, choose **Create action** (or **New action**) and
type a new name in **Who moves?**. The suggestions do not restrict the name.
Saving the motion adds that subject to **Subjects** and its timeline lanes,
even before it has a take. **Save for later** does not request a render.
There is not yet a separate **Add subject** command.

1. Select **Create action**. Name the subject and describe one complete action
   that returns to its starting pose. Mark the whole motion area, including
   handled objects and the path of moving limbs. Include/Protect brushes keep
   the rest of the scene protected.
2. Preview the setup, then **Save for later** or explicitly **Make first take**.
   Generation uses the configured, confirmed ComfyUI workflow. Saving a setup,
   arranging clips and exporting do not generate new motion.
3. Choose the action and a numbered take in the Browser. Play or scrub it in
   the Viewer, compare takes, and inspect first/middle/last frames. **Mask**
   shows its motion region. Where saved raw frames are available, **Adjust
   mask…** creates a separate corrected take for review; it preserves the old
   take and approval.
4. Review the action, identity, props and endpoint joins. Enter matching start
   and end anchors, acknowledge the visual check, then **Approve take**.
   Rejections require a reason. **Make another take** explicitly requests a
   fresh variation; progress and failures appear in **Jobs**.
5. Drag an approved action onto its subject's **Motions** track, or select
   **Place at playhead**. Click a placement to move it by exact start time or
   remove it. The complete take must fit; takes are not trimmed or retimed.

Each subject has a clearly named **Motions** lane above **Automatic idles**.
An explicit motion takes priority; the subject plays one animation at a time.
The idle lane has a gap beneath that motion, rather than playing underneath it.
Other subjects can animate independently when their motion masks are disjoint.

Each uninterrupted idle/hold region is shown as one **nested sequence**, such
as **Reading**. Click that block to open its individual takes and holds in a
separate timeline tab. Click a source take to audition it in the Viewer. Choose
**Episode sequence** to return to the complete timeline. Inside a nest, ruler
and transport times are local; its heading gives the corresponding episode
start time. Playback stays within the opened bed. Opening a nest preserves
the underlying schedule, source clips and saved pacing.

## Subject setup and automatic idles

Open **Subjects**, **Subject setup**, or a subject's track heading. Choose its
approved pool, variation seed and pacing:

- **Continuous idles:** fill available gaps with complete approved takes.
- **Idles with quiet holds:** insert seeded 4–8 second holds between takes.
- **Hold current pose:** use holds without automatic clips.

Select **Apply subject setup** to save and rebuild. An empty pool, or a gap too
short for a complete take, produces a visible hold. After motion, a hold keeps
that subject's actual decoded exit frame; it does not reset to the master.
Alternative takes avoid immediate repetition when another fitting take exists.
The same settings and seeds reproduce the same schedule.
Subject names that differ only by capitalization share a track. Source recipe
records keep their original spelling.

Idle creation and occasional take review live in Subject setup. Idles are not
manually pinned to the action lane. Changing idle settings preserves placed
actions. Apply pending settings before placing or moving another action.

## Canvas, masks and effects

**Build sequence** creates the preview; subsequent changes use **Apply changes**
or the relevant setup button. The Canvas plays the combined subjects. Click the
ruler or scrub to seek; use transport buttons for individual frames. Timeline
zoom and horizontal scrolling expose longer sequences. The full keyboard is
described under **Keyboard** below.

Only approved returning clips with compatible canonical poses, matching states,
scene dimensions and native 24fps timing enter this editor. **Unavailable to
this sequence** explains exclusions. Location changes and different ending
poses are deferred. Approved sources still need creator review at their joins;
the editor does not invent fades or repair unsuitable endpoints.

Independent subjects use the pinned binary support of their saved masks. The
approved full-scene videos already contain feathered edges, so the compositor
selects those finished pixels once instead of applying the feather again. All
selected masks are combined per subject and checked for overlap with other
subjects. An overlap blocks saving rather than guessing occlusion. The locked
master supplies the background, and protected pixels remain unchanged before
lossy MP4 encoding.

**Effects**, or the named FX tracks, expose available saved window-rain and
fixed-mug-steam regions and strengths. Apply settings to update the saved plan
and preview. These effect regions are fixed in this version; arbitrary effect
mask authoring and moving-plume tracking are pending. Rain excludes selected
subject-mask support. Effects use absolute sequence time across cuts and holds.
Procedural steam is conservatively suppressed during every action-role clip,
including one explicitly assigned to an automatic pool, and resumes at the
current sequence phase. The plume painted into the canonical master remains.

The 2026-10-30 rain playback fix keeps weather advancing while the next
character take loads or seeks. Routine canceled play requests no longer stop
the sequence. Reopen or refresh the studio to load the rebuilt interface;
saved effect strengths and sequence placements are preserved.

## Video texture track

Select **FX3 · Video texture** at the top of the episode timeline, or choose
**Effects → Video texture** in the Browser. Its controls cover the whole picture:

- **Enable video texture** switches the finishing layer on/off.
- **Strength**, from 0–100%, has a slider and exact numeric entry.
- **Grain size**, from 1–8 pixels, controls fine or coarse texture.
- **Pattern seed** fixes a reproducible pattern; **New pattern** changes it.
- **Reset** restores the initial controls, with texture disabled.

Adjust while playing to see the look immediately. **Apply texture settings**
saves the settings into a new sequence revision for export; unsaved adjustments
are labeled and export stays disabled until applied. Undo/redo includes texture
settings. Saved settings reopen with the scene. Existing sequences start with
texture off until enabled.

Texture moves on the absolute episode clock across takes and holds. It is a
procedural monochrome grain layer blended over the completed scene, including
rain and steam. Masters and source takes retain their original bytes. Preview
and export use the same seeded pattern and frame offsets; browser blending and
lossy MP4 encoding can introduce small pixel differences.

## Keyboard

The editor uses **Final Cut Pro 7 default shortcuts**. Open **Keyboard…** in the
menu bar (or press **Alt+H** / **Ctrl+/**) to see every command on a
color-coded keyboard and change any of them. Ctrl also accepts Cmd on a Mac.

Keys act on the **active window**, whose title bar is highlighted, as in FCP7.
Click a window or press **Ctrl+1** Viewer, **Ctrl+2** Canvas, **Ctrl+3**
Timeline, **Ctrl+4** Browser; **Q** switches between Viewer and Canvas. With
the Viewer or Browser active, transport keys play the auditioned take;
otherwise they play the sequence. Text fields keep their own keys.

| Task | Keys |
|---|---|
| Play / pause | Space |
| Shuttle reverse / stop / forward (press again for 2×, 4×, 8×) | J / K / L |
| Step one frame while holding K | K+J, K+L |
| Frame / one second | ← → / Shift+← → |
| Previous / next edit (cut) | ↑ ↓ |
| Start / end | Home / End |
| Mark In / Out · go to In / Out | I / O · Shift+I / Shift+O |
| Clear In / Out / both | Alt+I / Alt+O / Alt+X |
| Mark clip (In/Out around the segment under the playhead; selects a placed action) | X |
| Play In to Out · play around current frame | Shift+\ · \ |
| Loop playback on/off | Ctrl+L |
| Add marker · previous / next marker | M · Shift+↑ / Shift+↓ (also Alt+M / Shift+M) |
| Delete marker at playhead · all markers | Ctrl+\` · Ctrl+Shift+\` |
| Match frame (open the take under the playhead in the Viewer at that frame) | F |
| Previous / next take | Page Up / Page Down |
| Overwrite: place the Viewer take at In, or the playhead | F10 |
| Lift the selected placed action | Delete or Backspace |
| Nudge selected action 1 / 5 frames | , . / Shift+, Shift+. |
| Deselect | Ctrl+Shift+A |
| Undo / redo | Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y |
| Save (apply settings or build) | Ctrl+S |
| Timeline zoom in / out · fit | Ctrl+= / Ctrl+− (or Alt) · Shift+Z |
| Cycle track height | Shift+T |
| Standard / All tracks layout | Ctrl+U / Alt+U |
| Find an action · import scene | Ctrl+F · Ctrl+I |

**Typed timecode:** over a monitor or the Timeline, type digits (or + / −)
to jump. Digits fill from the right as HH:MM:SS:FF, `.` means `00`, and a
leading + or − is relative: `1419` is 14 s 19 f, `+1.` is one second later,
`-48` is two seconds earlier. Enter applies; Esc cancels.

Repeated nudges are shown immediately and saved as **one** revision when you
pause, so holding `.` does not create dozens of revisions. Nudges, overwrite
and lift follow the same rules as dragging: approved returning actions only,
complete takes inside the sequence, and changed settings applied first.
Zooming keeps the playhead in place, and navigation scrolls it into view.

In/Out points are workspace aids and reset when you change scene. Markers are
kept per scene **in this browser only**; neither is part of the saved
sequence, manifest or export. Not offered, because takes are never trimmed or
retimed and audio is pending: Insert (F9), Replace, Ripple delete, Blade,
trim/slip/slide tools, snapping, linked selection, render and audio levels.

**Changing keys:** choose **+** beside a command and press the new key. A key
already in use asks before moving it; **Default** restores one command and
**Restore Final Cut Pro 7 defaults** restores all. Tab, Shift+Tab and Esc are
kept for focus and closing. Keys marked **!** (such as Ctrl+W or Ctrl+T) are
usually kept by the web browser. Changes apply immediately and are saved in
this browser; **Export…** / **Import…** move a layout to another browser or
machine as `last-light-radio-keyboard.json`.

## Saving and export

Edits create immutable manifest/configuration snapshots and advance the scene's
saved revision. Earlier source media, reviews, manifests and completed exports
remain intact. A conflicting edit from another window is rejected visibly.
Reopening restores the latest saved sequence; unsaved settings need applying.

This version supports 1–600 seconds at 24fps. **Export sequence…** queues a CPU
render; follow it in Jobs and download the MP4, manifest and event log. Export
is silent H.264 at the source dimensions, padded by one pixel when necessary.
Audio mixing remains pending despite the labeled Audio lane.

The worker checks pinned source hashes and approvals, streams masked subjects
with exact exit holds, then fully decodes the output to verify frame count,
geometry, rate and timestamps. Changed approvals block publication, including
revocation during rendering. Failed/interrupted exports stay visible and can
retry the same plan. Files are stored under
`.local/studio/exports/pilots/SEQUENCE_ID/`; `export_report.json` records timing,
checksums, holds and renderer details. Draft sequences do not change canon.

## Film audio integration - 2026-11-13

The existing editor now has a **Viewer > Audio** workspace and **A1 Production sound / A2 Music** lanes. Import a WAV, audition it, explicitly approve it, and place it at the playhead. Start, source In, duration, gain, fades and enabled state are editable; **Apply audio to sequence** uses the existing revision/undo system. Export the saved sequence to hear the mix with picture.

Original WAV bytes and hashes remain immutable; imported audio is canonicalized to 48 kHz stereo PCM for deterministic mixing. Optional recipe JSON remains attached to the source. Placement revisions pin source hashes and approval version; revoked or changed approvals require rebuilding before export. Empty audio configurations retain the legacy silent export behavior. No new generation dependency or GPU work is needed.

**Current limits:** WAV uploads under 20 MiB; sequences up to ten minutes; no automatic music generation connection, waveform editor, audio looping or synchronized live Canvas mix yet. Canvas is explicitly picture-only; the source player and exported movie provide audio audition. H3 audiovisual media can supply a separately extracted WAV, but H3 package transfer to Toast was blocked by the Library helper's Windows extended-attribute support, so that exact clip has not been verified in this editor.

## Film Browser selection — 2026-11-19

Click to select one source or sequence. Hold **Ctrl** (Command on macOS) while clicking to add/remove items, or **Shift** to select a range in the displayed order. Ctrl+Shift-click adds a range to the existing selection. Double-click or Enter opens one item in the Viewer/Timeline.

With a source row focused, **Ctrl+A** selects sources in expanded groups matching the current filter/bin. **Escape** or **Ctrl+Shift+A** clears selection. Text inputs retain their native Select All behavior. The source footer shows the selected count; its **Bin** menu and **+ Bin** operate on all selected sources matching the current filter/bin. Right-clicking a selected source preserves the selection and offers bulk bin moves. Other context-menu commands apply to the named source. Bin membership remains browser-local.

Verification: 220 offline tests ran (219 passed, one Windows symlink permission skip), 64 Python files passed project checks, and TypeScript/Vite build passed. The isolated six-second/144-frame test export combines the actual ACE-Step trial music with an explicitly synthetic production sound, not H3 audio. Evidence: `artifacts/audio-milestone-20261113/backend-verification.json`; full regression log: `artifacts/film-audio-20261113/full-tests.log`. Production scenes, original media and their approvals were not changed. UI verification is reported separately.
