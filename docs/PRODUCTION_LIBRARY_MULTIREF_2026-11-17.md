# Production Library multi-image conditioning checkpoint (2026-11-17)

## Implemented
The existing Shot Plan / Production references panel can select multiple named views of character, location, and prop records. A shot pins each record ID, revision and view. Existing first-frame mode remains available and still uses exactly one image.

Explicit experimental reference-image mode compiles an ordered 1-9 image list with descriptive roles. Both those roles and `<Picture N>` labels enter the actual H3 prompt. Every selected image is verified, uploaded separately at Generate, and wired into `MiniMaxH3ReferenceToVideo` as `ref_images.ref_image_0` through `_8`, with the video VAE connected and image sizing `match`. These are reference images, not first/last frames.

Preflight, saved shot assignments, submitted workflow, upload receipts and imported take metadata retain ordered image IDs, roles, immutable image hashes, and pinned production-reference revisions. A changed order/role/recipe/assignment invalidates preflight. Revision edits do not silently rewrite prior takes. Candidate generation is not approval.

## Important model limitation
Harbinger currently has FL2VA weights and FL2V Turbo8, not specialized REF2VA weights. The inspected successful lighthouse L02 used those FL2VA weights with the ReferenceToVideo node and one image. The new recipe is explicitly labelled experimental FL2VA reuse. It is not evidence that two or more references produce consistent identity or geometry. Roles are prompt instructions, not hard constraints. No new GPU generation was performed for this infrastructure change.

## API contract
Compile: `POST /api/film/projects/{project_id}/references/compile` with bindings `[ {id, revision, view} ]`, `action`, and `conditioning_mode: "reference_images"`. Returns `recipe_id`, `reference_images: [{image_id,role}]`, null first/last frames, compiled brief and pinned bindings. First-frame mode supports precise `conditioning_binding: {id,revision,view}`, or unambiguous legacy `conditioning_reference_id`.

Save these values into the shot plan. Generation state exposes `recipes` plus legacy `recipe`. Preflight and Generate accept the exact recipe and ordered references from the plan. Reference-image conditioning cannot be mixed with first/last-frame or continuation conditioning. Empty lists, more than nine images, duplicates and mismatched pinned image lists are rejected.

## Verification and deployment boundary
- Focused existing reference/image/generation/shot-plan regressions: 28 pass.
- Multi-reference test module: 10 pass, including six inherited image tests and four new multi-reference cases. Mock lifecycle covers separate uploads, graph inputs, roles, checksum receipts, import as candidate, revision pinning, stale order, unsupported worker schemas, and invalid inputs. This is not GPU output validation.
- Live Harbinger read-only preflight with two synthetic sources: ready=true, zero errors, two expected upload-on-Generate warnings; zero jobs created and zero images uploaded. Receipt: `artifacts/production-reference-multi-20261117/live-preflight.json`.
- TypeScript check and isolated Vite production build passed. Existing deployed `frontend/dist` and shared film service :8769 were NOT replaced/restarted.
- **Retired 2026-11-18:** the isolated :8771 editor was stopped at Boden's request; :8769 is the one editor. The two Astrid projects (and their sequences, media, exports, shot plans, references and 16 generation jobs) were copied add-only into `.local/film-studio`; see `artifacts/astrid-migration-20261118/`. The LAN gateway (https://192.168.1.68:8771) now forwards to :8769. The test-studio folder is untouched. The native-viewer "Selected take" / reroll UI (`native-viewer-src`: ShotGeneration, OwnedTake, ReadOnlyReceipt, `/astrid-shot-controls` bridge to :8773) was ported into the main editor the same day (Generate › Selected take; server bridge `last_light_radio/shot_controls_bridge.py`, without `/api/use`).
- (historical) Isolated browser test service :8771 uses `artifacts/production-reference-multi-20261117/test-studio` and synthetic references, no Studio background worker. Build is in sibling `dist`. It is not the production editor.

Backups: `artifacts/production-reference-multi-20261117/before` and `artifacts/production-library-ui-20261117`.

## Next gated checks
1. Finish isolated browser smoke and record full regression result.
2. Coordinate with Claude / owner before replacing shared dist and restarting idle :8769 service; check pending jobs first. Do not overwrite unrelated UI changes.
3. Once the chosen character views are reviewed, import and register that specific approved pack separately from location views.
4. Run an explicitly labelled multi-reference candidate through the real editor lifecycle; compare identity, clothing, object positions and reverse angle. Keep baseline and references unchanged. Do not call schema success visual consistency success.

## Final isolated verification
Browser smoke passed on :8771: selected character front + profile and location room; compiled Picture 1/2/3 roles; saved shot plan revision 2; Prepared generation with all three images, correct experimental recipe, no first/last frame. The persisted plan has three reference images, and jobs remained zero. Evidence: artifacts/production-reference-multi-20261117/browser-saved-plans.json. No Generate clicked.

Full CPU regression: 330 tests, 328 pass, one skip and one known pre-existing F11 shortcut registry expectation failure in test_shortcuts (also recorded in prior gap-backend checkpoint). This is not an entirely green suite. Final targeted run after metadata review: 18 tests passed. The extra regression covers nine maximum-length Unicode reference roles; compact imports now retain full ordered roles through immutable receipts without exceeding the 12 KB import envelope. Full log in artifacts/production-reference-multi-20261117/full-tests.log.

Lineage scope: Production references flow requires Save shot plan -> Prepare generation, as the UI states. Pinned record/revision/view tuples are carried by that planned assignment. A direct unplanned API job only has immutable image IDs, roles and hashes, not production-library registry revision lineage.

No production deployment performed. Isolated service was restarted only to load final metadata code, on :8771 with synthetic data preserved. Astrid testing is coordinated separately by its worker; do not duplicate GPU work.
