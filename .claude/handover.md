# Handover - 2026-11-19: no approve/reject, clip length, Queue tab

## What changed (Boden asked)
Backup of everything before editing: `artifacts/no-approval-length-20261119/` (last_light_radio, frontend_src, frontend_checks, tests, docs).
- **No approve/reject in Film.** Server: `film.save_sequence`, `place_picture_interval`, `validate_manifest` and `audio_tracks.validate_tracks/validate_pinned(require_approval=False)` check only the content-addressed source (sha/path + file verify). `generation_timeline`: every finished job auto-imports (no destination needed); imported = `ready_to_place`; place() no longer checks status. Older editor (`editor.py`) and pilots keep the gate. Overrides AGENTS.md guardrail 7 (recorded in PROJECT_TRUTHS.md).
  UI: removed Viewer review box, Browser Reject, Review menu items, Audio tab Approve/Reject (`AudioWorkspace noReview`), guide review step, shot-plan approved check, cleanup "rejected" ticks. Browser "Status" is now **Use** (● in sequence / ◐ used / ○ unused); Candidates/Rejected chips gone.
- **Drag to timeline.** Browser rows drag onto V1 = Insert at the drop point (past the end appends, snaps when N is on; a single generated take brings its sound to A1 via `placeTakeNow`); sound drops on A1/A2. Drop marker with timecode. FilmBin drag `effectAllowed='copyMove'`.
- **Clip length.** `h3_joint_av_recipe.frames()` 48-240, step 4, default 124; `length_frames` in preflight/job params; `_soundtrack`/`inspect_video` use the job's length (old jobs default 124). UI `clipLength.ts` + Generate "Clip length" slider/seconds; "Longest clip (coherence limit)" in Generate › Settings, browser-local, default 124 (only proven length). Shot-plan takes get the shortest length covering the interval.
- **History → Queue** (panel id still `history`): shows jobs rendering / failed / import failed / waiting to be placed; finished fold under "Finished, in the Browser".
- Follow-ups: jobs expose `import_error` (film + music) and `metadata.length_frames` (settings.frames = real length); Queue card shows the import error; striped request blocks use the job's length; the editor refetches the Browser when a job names a clip it doesn't have and re-polls ~30 s while a finished job's import lands; placing a take whose sound isn't loaded yet refuses with a message instead of going in picture-only.
- Renamed buttons (dot's tests may look for old text): Append approved shot → Append shot; Place reviewed clip → Place clip; Review take → Open in Viewer; tab/menu History → Queue; Show in History → Show in Queue; Review planned picture → Open planned picture in Viewer; Listen / review → Listen.

## Tested
- Python: all Film/audio/generation/timeline modules OK (incl. new `test_take_length_is_bound_into_graph_and_validated`). Full run: 7 old modules fail to import (`import test_pilots` etc. need tests/ on sys.path) and `test_shortcuts` fails on F11; shortcuts.ts is unchanged from the backup, so both are pre-existing.
- Frontend: tsc OK; filmEdits 45, menus 63, shortcuts 5, guideSteps 22, clipLength 23 (new).
- Browser on scratch library (`film-ui-test` :5198 → :8790, seeded with the clip-delete seed script): dropped a *rejected* clip on V1 mid-shot and saved (rev 2 accepted); sound onto A1; clip past end appended; sound on V1 refused with a message; length 3 s → 72 frames (untested note), 9 s capped at 5.17 s, limit 8 s → 192; Queue tab text; right-click menu without Review/Reject; no console errors. Servers stopped.
- End to end on the scratch library with a fake-worker job at 72 frames (`artifacts/no-approval-length-20261119/seed_job_72.py <repo> <data dir>`): graph length 72, frame + audio clock checks passed, auto-imported with no click, dragged onto V1 with its sound on A1, Queue card folded under Finished, Recent takes shows In the Browser.
- Not tested: a real H3 run at a non-124 length; a real import failure showing on a Queue card.

## Not done / open
- **Live (Boden: "Yes, restart it").** Rebuilt dist and restarted :8769 hidden (no jobs or exports active; now pid 29800). Restarted a second time after adding `import_stage` to jobs, so pre-change finished jobs say "Finished before automatic import existed. Import it…" instead of a false "copying…". Checked read-only on :8769: no Approve/Reject buttons, Queue tab (1 card: "cloak test", never imported, not touched), Browser chips Video/Audio/Stills/All/In sequence/Unused, length control at 124 frames, no console errors. Nothing saved, dropped or imported on live.
- Whether H3 returns exactly N frames for N != 124 is unverified; `inspect_video` is strict, so a mismatch fails the job visibly (MP4 kept under `candidates/<job>/`).
- Older finished jobs never imported stay as "Import" cards in the Queue (no startup sweep).
- LAN gateway allowlist unchanged (no new routes added).
- Older: requested-take blocks for deleted takes (B5); shot-plan candidate rows block deletion.

## Next step
Boden: hard-reload :8769, try dragging a clip onto the timeline, and run one H3 take at 96 frames (4 s) to settle the longest-clip limit. Decide whether "cloak test" should be imported.
