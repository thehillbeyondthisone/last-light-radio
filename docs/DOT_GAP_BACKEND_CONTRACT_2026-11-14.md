# V1 gap backend contract — 2026-11-14
Optional backend capability, no migration or live-library mutation.
## Payload
A gap in shots is exactly { "id": "<stable nonempty id>", "kind": "gap", "duration_frames": 48 }.
Video items without kind preserve the existing format and hashes. Explicit kind "video" is accepted and canonicalized to that legacy shape. Other kinds are rejected.
Gaps must have integer duration 1..14400 and no asset_id, source_in_frame, source, approval_version or provenance keys (even null). Total timeline remains at most 14400 frames. IDs remain unique across all items.
Adjacent and trailing gaps are retained, not merged or folded. Their order and identities survive saves. start_frame accumulates normally in the pinned manifest; picture_duration_frames includes gaps.
Gap-only picture lists export black MP4; empty picture lists with explicit duration retain audio-only behavior.
Audio timing, markers and selection are unchanged by storing gaps.
## Placement and integrations
Existing exact-interval picture placement can replace one whole gap. It retains explicit duration and audio; shorter sources are rejected and longer sources need trim_to_fit.
Partial gap splitting and automatic gap insertion before late placements are NOT implemented. The UI can compose gaps via save_sequence; partial placement still returns the existing clear refusal.
Continuation preparation rejects gaps explicitly. FMV export keeps gap timing in its frozen sequence but collects video-source provenance only for actual media. Candidate/idempotency checks tolerate gaps without asset_id.
## Hash/export rules
Legacy no-gap manifests retain film-cut-v1 and exact pre-change hashes.
Gap manifests use film-cut-gaps-v1. Gap order/length/IDs affect their hash. Saves still mark export draft and preserve optimistic revision guards.
Both renderer versions are accepted; a gap in a legacy renderer manifest is rejected. Rendering produces real black frames and verified frame count, rate and presentation timestamps.
## UI handoff
No UI files changed. The current frontend must not yet be assumed able to display/edit gap-containing sequences. Wire the union type through selection, preview, edit math, match-frame and source actions; a gap has no source to audition or match. Keep prior video payloads unchanged.
The running server was NOT restarted; source changes load on the next coordinated restart. No production gap sequence has been saved. Do not create one with the old frontend.
## Verification and rollback
12 focused tests pass in disposable libraries, including black export, gap-only export, legacy hash equivalence to backed-up code, exact filling, audio/marker/selection preservation and FMV provenance.
Full-suite outcome is recorded separately in regression.log; no GPU jobs.
Backups: artifacts/gap-backend-20261114/before/ (five modules).
Changed: film.py, film_continuations.py, film_story.py, film_shot_plan.py, generation_timeline.py; added tests/test_film_gaps.py.
Restore individual modules from before only if no later changes have been made; do not blindly copy over future edits.


## Verified outcome
Focused suite: 12 tests passed. Full regression (collected before the last two focused tests were added): 312 tests, 310 passed, one existing Windows-permission skip, one failure. The failure is test_shortcuts.test_fcp7_defaults_are_unique_valid_and_cover_core_commands: untouched frontend/src/shortcuts.ts defines Replace as F11 and also lists F11 in BROWSER_RESERVED; the test rejects all reserved defaults. This test imports the TS registry directly and does not exercise modified backend code. It was not fixed here because Claude owns UI/keyboard decisions. Final source check: 88 Python files, zero problems.
Gap export uses the existing full-decode inspect_video path, which validates frame count, rate, geometry and every presentation timestamp. Black samples and frame order were independently checked in the test.
No server restart or live database writes occurred. Backend source is ready for coordinated UI integration, not a claim that the running editor already exposes gaps.
