# Production reference system: backend slice and UI handoff

2026-11-15. User means reusable technical visual canon INSIDE the editor, not a decorative collage. Takes must derive from defined characters and locations rather than repeatedly inventing “a camper.”

## Implemented, not yet deployed in the running service
- `last_light_radio/film_references.py`: project-scoped character/location/prop records, named imported image views, visual guidelines, optimistic revision checks and retained immutable revisions. Image checksums verified on read/use.
- GET/POST `/api/film/projects/{project_id}/references`: list latest/save revision. POST uses existing X-LLR-Client: studio header.
- POST same route + `/compile`: explicit action/camera direction + pinned bindings + choice of actual first-frame reference. Returns generation brief, first_frame_id, last_frame_id=null, production_reference_bindings and exact conditioning limitations. Does not render, approve, or modify a sequence.
- Existing shot-plan save accepts optional `production_reference_bindings`. Planned generation anchor embeds resolved pinned records in its frozen configuration. Updating a reference does NOT silently update old shots/takes.
- Previous source copies: artifacts/production-references-20261115/. No frontend files, live project records, running service, existing timeline or GPU queues changed.

## API examples
Save payload:
```json
{"expected_revision":0,"kind":"location","label":"Mara van","guidelines":"Window left, counter and turquoise kettle right; rear doors behind.","views":[{"name":"interior-master","image_id":"image.<imported-sha256>","description":"Actual authored master, not invented reverse angle"}]}
```
For revision use returned id + expected_revision. Separate character record for Mara; use real source image IDs. API-authored record does not imply user approval of a candidate.

Compile payload:
```json
{"bindings":[{"id":"reference.<id>","revision":1,"view":"interior-master"}],"conditioning_reference_id":"reference.<id>","action":"Precise action and camera direction"}
```
Save returned brief + frame IDs + production_reference_bindings into a planned shot. Existing generation uses saved brief/frame IDs; pinned records travel in `planned_shot.production_references` receipt. The compiler is explicit: bypassing it can omit its textual guidelines; bindings alone are provenance, NOT automatic visual enforcement.

## UI integration proposed, NOT implemented
Keep FCP7 Browser/Viewer/Canvas/Timeline unchanged. Add Browser Characters/Locations/Props bins and an inspector tab for selected record. Show actual named views, per-view use, fixed layout/object rules, revision, and linked shots. A shot selects Mara revision and van/setup revision, then an explicit Conditioning View. Show “sent to model” versus “reference only” clearly. Compiling populates existing generation/shot-plan controls; changing a selection requires recompile/preflight. Never silently discard production_reference_bindings when saving plans. A take inspector shows the frozen sources/revisions it actually used. Do not rebuild editor layout.

## Critical model limit
Current local editor H3 adapter consumes FIRST/LAST frames, not an arbitrary character/location image bundle. Selected first frame is a real image tensor; additional references here provide textual constraints and inspection only. This does not guarantee shared 3D geometry, identity, hidden objects, novel camera angles or spatial outpainting. A new view must be generated/constructed and visually checked against the master before becoming an intentional reusable view. A collage should not be supplied as a video first frame. Shared depth/geometry or a verified multiview-conditioned image stage is a later stronger layer.

## Mara migration
Use original canonical reference, not drifted generated aisle/bed/cab. Window with cream curtains left, cedar counter/kettle right, rear double doors behind, ochre blanket lower right. Mara chestnut curls, rust headband, ochre shirt/denim overalls, cream mug. Confirm actual image observations before registering more views. Current Harbinger renders continue independently and are not retroactively connected by this code.

## UI + deployment completion, 2026-11-15
Supersedes backend-only status above. ProductionReferences.tsx is now integrated in the existing Shot Plan panel. FilmShotPlan preserves bindings on save; FilmEditor only passes project ID. TypeScript/Vite build succeeds (index-BoqEMCOB.js). 28 Python image/generation/plan/reference tests pass including selected image -> actual H3 graph and frozen job lineage; 29 frontend edit checks pass.

Observed user's existing Mara tab showed Saved, disabled Save/Discard and no playback. APIs showed four successful generation jobs, no music jobs, no active exports. Backed up database, restarted only identified idle film service PID25024 -> PID20908. No Harbinger process touched.

Live browser verification in separate tab and labeled isolated project: created named visual location definition with real imported test image; selected it, compiled explicit action + continuity text into shot draft, saved plan revision2, prepared generation. H3 setup visibly locked brief and first reference image. No Generate clicked. Test project `Reference system - isolated UI verification`, sequence `Reference binding test - no GPU`; exact IDs in artifacts/production-references-20261115/ui-fixture.json. Existing Mara/FABLE records untouched. Closed test tab; original user tab not reloaded.

User path: refresh editor when ready -> Shot plan -> Production references. Current real Mara registry still needs seeding with verified source images; test fixture is clearly marked and is not production canon. Reverse-camera views should be consciously authored/verified, never silently canonized from drifted takes.

## Real Mara references seeded
Original `van-mara-reference-20261115.png` recovered read-only from Harbinger Comfy input, visually inspected, imported with exact SHA256 87961c482be50b1a079cf0b5f6cad011d7e3de6a18fecf084f5e2933cf9cf177. Mara character + van location v1 definitions now exist in the real Mara project. Both intentionally refer to the original full-frame image, with separate character/layout guidelines and named context views. No fabricated independent angles or generated reverse view has been declared canonical. Both bindings compile correctly to the selected actual image. No timeline edits. Live browser verified populated panel and left it open in a new tab; original user's tab untouched. Final build includes navigation-race guards and honest draft labels: index-5ZyzfGB3.js.
