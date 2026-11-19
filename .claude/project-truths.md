# Project truths (verified; keep short)

Long-form record: `PROJECT_TRUTHS.md` at the repo root. This file holds what a new session needs first.

## Shape
- Not a git repository. Checkpoint by copying source into a dated `artifacts/<name>/` folder before editing.
- React 19 + TS + Vite frontend in `frontend/`; Python HTTP service `last_light_radio/` serves `frontend/dist`; SQLite + files under `.local/`.
- Film editor (default view): `frontend/src/FilmEditor.tsx` + `fcpFilm.css`. Logic above `// ---- Presentation only below`, then render. Lines are very long; splice by exact substring or line range. `film.py` uses CRLF.
- Library storage: SQLite `settings` rows (`film.project.*`, `film.sequence.*`, `film.asset.video.<sha>`, `audio.<sha>`, `film.image.*`, `film.generation.*`, `film.plan.*`, `film.deleted.*`...) + `jobs` table + content-addressed files (`film/assets/<sha>/original.mp4`, `audio/<sha>/{original,canonical}.wav`, exports, `records/`).

## Running and checks
- Live editor: http://127.0.0.1:8769, library `.local/film-studio` (creator data). Runs hidden via Start-Process (`.local\venv\Scripts\python.exe -u -m last_light_radio studio --port 8769 --data <abs path>`), logs `.local/film-editor-8769.*.log`. server.py/film.py changes need a restart; `npm --prefix frontend run build` updates dist without one.
- LAN gateway `%LOCALAPPDATA%\AstridStudioLan\gateway.cjs` (https://192.168.1.68:8771) forwards to :8769 with a route allowlist; new routes are refused over LAN until added.
- `/astrid-shot-controls/*` bridges to `artifacts/astrid-local-director-sd-20261119/shot_controls.py` on :8773 (not started on reboot).
- Launch configs: `film-ui-dev` (Vite :5199 → live :8769, UI only) and `film-ui-test` (Vite :5198 → a throwaway service on :8790 you start on a scratch library; seed script in `artifacts/clip-delete-prompt-20261118/`). Use `film-ui-test` for anything that writes.
- API GETs need header `X-LLR-Client: studio`; a JSON body makes it a POST.
- Python: `.local\venv\Scripts\python.exe -m unittest tests.test_film_delete tests.test_film tests.test_film_generation tests.test_film_shot_plan tests.test_generation_timeline` (all OK). Running every module: 7 old modules fail to import (sibling `import test_pilots`) and test_shortcuts fails on F11 - both predate 2026-11-19. System python lacks PIL; pytest not installed.
- Frontend: `npm --prefix frontend run check` (tsc); `node frontend/checks/{filmEdits,menus,shortcuts,guideSteps,clipLength}.check.ts` (45 / 63 / 5 / 22 / 23).
- Server and UI changes that depend on each other: rebuild dist only together with a :8769 restart (ask Boden first).

## Rules that bite
- dot (another agent) and other Claude sessions edit these files in parallel: re-read right before editing; never save, export, approve, place, generate, import, delete or reseed live data during UI tests.
- Keep the FCP7 desk: Browser left, Viewer centre, Canvas right, Timeline below. New tools go in Viewer tabs.
- Preserve button text and aria-labels; dot's browser tests find controls by them.
- Example lore (bus 271, UMBRA FM 88.3) is not approved canon.
- O on a cut keeps FCP7 behaviour (Out includes the frame under the playhead), Boden's decision 2026-11-17.
- `;` = Lift In-Out (gap), `'` = Extract In-Out (close up); both cut V1 and all audio. Prev/next edit is Up/Down.

## Editor internals
- Saving a sequence resets `export` to `draft`; server refuses saves on an older revision.
- Unsaved edits live in `drafts` ref per sequence; replacing `sequence` needs `stashCurrent()` then `resetForSequence()`.
- Commands run through `exec(command,event,pane)` (`execRef`); menus are data in filmMenus.ts, and menus.check fails if an id has no case.
- Right-click menus: one ContextMenu from `ctxMenu` + `menuModel()`; Browser bins section from `binMenuSection`. Icons by id in menuIcons.tsx.
- V1 holds gaps; `activeShot` is video only. Edit logic in filmEdits.ts.
- Generate tab opens on New generation; Selected take only when pressed. The guide drives the form via `genControl`/`genSnap`; never write `llr.film.generation.draft.v1` directly. FilmGeneration/FilmHistory stay mounted when hidden.
- Multi-line edits to the long one-line TSX files: an exact-substring Python swap script (unique match, keeps CRLF) is more reliable than PowerShell string escaping.
- Clip prompt: `promptOf.ts` (job brief, then provenance brief/prompt variants). Opening Generate with a clip in the Viewer fills an empty or auto-filled brief only.
- Clip delete: `POST /api/film/assets/<id>/delete` (`film.delete_asset`, dry_run is lock-free). Blocks on any settings row holding the sha except `film.asset./audio./film.image./film.generation.import./film.deleted.`. Deletes only the clip's own content-addressed files. UI: `DeleteClips.tsx`.
- No approve/reject in Film (Boden 2026-11-19, overrides AGENTS.md guardrail 7): any imported clip/sound places; saves check source sha only. Finished jobs auto-import. Old editor/pilots keep their gate.
- Browser rows drag onto V1 (Insert) and A1/A2 (`binDropOn` in FilmEditor). Browser "Use" column = in sequence / used / unused.
- H3 take length `length_frames` 48-240 step 4 (only 124 proven); creator limit `llr.film.generation.lengthLimit.v1` (browser-local, default 124). `clipLength.ts`.
- Viewer tab "Queue" (panel id `history`, FilmHistory.tsx) = jobs rendering / failed / waiting to place.
- Requested-take striped blocks come from `film.generation.destination.<job>`; no withdraw route (B5).
- User bins are browser-local (`llr.film.userBins.v1`, module store in FilmBin.tsx).
- Upper desk is a 5-track grid with inline columns (`llr.film.cols.v1`). Shuttle label is an overlay; nothing may appear in the transport row during playback.

## Gotchas
- PowerShell 5.1 shows UTF-8 as mojibake; write files with .NET `UTF8Encoding($false)`. Native `python -c` mangles quotes: write a script file instead.
- Don't name files differing only by case (Windows resolves `clipPrompt.ts` and `ClipPrompt.tsx` to one module).
- The Edit tool trims a trailing space at the end of old/new strings; check class names after such edits.
- Browser pane ~800x500. `type` sends no keydown; script keys with `window.dispatchEvent(new KeyboardEvent('keydown',{key,code}))`, ~35 ms apart. Native HTML5 drag needs scripted `DragEvent`. Hidden pane throttles timers.
- React-controlled inputs: set value via the prototype setter + `input` event in scripted tests.
- The keyboard layout dialog closes itself under the Vite dev StrictMode; test it on the built bundle.
- Video `currentTime = n/24` floors to frame n-1; Canvas seeks add 0.001 s. Playhead may park at `total` (`parkedFrame`).
- Harbinger ComfyUI http://192.168.1.168:8188 is shared; coordinate before any POST. Don't click Generate/Import/Reroll in tests unless Boden authorised a run.
- ffmpeg: `.local/vendor/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe` (no ffprobe).
