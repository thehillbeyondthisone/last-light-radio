# Offline director prototype
Run from this directory with Python 3 (standard library only):
```
python -B -m unittest -v test_prototype
python -B prototype.py brief "Your small idea"
python -B prototype.py compile example-shotbook.json --out proof-v2
```
The brief command creates an authoring packet for a person or authorized assistant. It does NOT call an LLM or write a screenplay automatically. The included original story is an assistant-authored provisional fixture, not a user-selected creative brief or approved canon.

The compiler validates the authored shot book, emits deterministic prompt candidates and a reduced NLE-style shot-plan projection, and creates a readable review. It never submits jobs or edits an NLE library. The projection intentionally lacks a real sequence/revision and resolved image IDs; it is not a working API save payload.

Verified 2026-11-14 on Toast: 12 unit tests passed, a 6-shot/720-frame book compiled to proof-v1, and a repeated output-directory attempt returned exit 2 while preserving the original compilation hash. No GPU or network use. The initially read-only Python alias could not launch; the authorized write/test execution succeeded.

Read proof-v1/review.md for the original storyboard and proof-v1/compilation.json for six dry-run jobs and seven blocker groups (references, plan review and final audio). These are readiness findings, not broken renders.

Covered: repeatability, invalid timing, FPS/duration, duplicate IDs, scene membership, state mismatch, unresolved approval/reference, recipe length cap, honest no-submit behavior and blank brief rejection.
Not established: arbitrary untrusted JSON hardening, artistic quality, pixel continuity, media generation, audio sync, NLE import, autonomous writing or full application regression. No existing source/UI/project data changed.

Next bounded integration: a versioned writer response contract + semantic review, then an explicit adapter into a disposable NLE sequence after current recipe capabilities are reconciled. Keep model choice injectable and do not require paid cloud inference.

