# Codex Instructions — Last Light Radio

Read **`PROJECT_TRUTHS.md`**, **`HANDOFF_PLAN.md`**, and **`MVP_TASKLIST.md`** before writing or replacing code. This is the authoritative handoff package for a potentially lost project; it is **not evidence of an existing working codebase**.

## Mission
Build a Windows-first, creator-operated, **model-agnostic** application that makes long, believable animated scenes from creator-supplied canonical stills and approved motion libraries, with **shared-world continuity across linked episodes**. Last Light Radio is the first creative world, **not a hard-coded application limitation**.

## Operating guardrails
1. **Inventory before changing anything.** If working in an existing folder, list it, identify its runtime, check Git status, read existing docs and preserve useful work. Do not overwrite, delete or rearrange existing assets without approval. Do not assume any repository path or machine connection.
2. **Build incrementally.** Start with M0/M1 in `MVP_TASKLIST.md`: inspect environment, establish tests and canonical data model, then implement a mockable ComfyUI connection. Do not jump into the entire editor or 90-minute GPU render before a 10-minute deterministic pilot works.
3. **Design for user's actual Comfy setup.** User can run H3 locally via ComfyUI on RTX 4070. Request/import their working **API-format workflow JSON** before binding node IDs or model-specific parameters. No mandatory cloud API. Use HTTP/WebSocket ComfyUI API and gracefully fall back to polling.
4. **No live AI agent directing episodes.** Clip generation may use AI models; scheduling, continuity, variation selection and final assembly must be deterministic ordinary code.
5. **No invented canon.** Candidate lore (UMBRA FM 88.3, bus 271, etc.) must remain marked as provisional until creator approves it. Never mutate canon when drafting/testing.
6. **Treat the canonical image as immutable.** Derivatives, masks, candidates and exports have separate locations. Preserve provenance and checksums.
7. **Maintain visual/state continuity.** Only approved clips can enter a production timeline; full-frame AI clips cannot overlap independently without validated masks/compositing.
8. **Make failures visible.** Always log queued/completed/failed renders; report absent models/nodes, state mismatches, missing clips and fallback choices instead of guessing or silently skipping.
9. **Never add dependencies or resource-heavy steps without reason.** Recommend rather than demand a technical stack where a project already exists. Keep tests independent of a physical GPU/Comfy installation.
10. **Update `PROJECT_TRUTHS.md` for proven facts and `MVP_TASKLIST.md` for progress** at milestone boundaries. Keep dated notes concise.

## First Codex execution request
- Inspect the available directory and report whether source code, media, or a Git repository already exists.
- Implement **M0 and the first vertical slice of M1** only: project skeleton (if absent), data model and validation, test fixtures, deterministic schedule test, and a stub/mock ComfyUI adapter. Produce a runnable demo that needs **no GPU**, showing a seed-based schedule of scene idles/actions.
- Present a short progress report: files created/modified, tests and results, blockers, and the next 3 tasks.
- Before attempting real H3 submissions, obtain the user's exported working ComfyUI API workflow or inspect a user-provided one. Never guess the custom nodes.

## Milestone completion definition
A milestone is done only when the described acceptance test passes, artifacts can be reproduced from instructions, and existing user files are preserved. Incomplete tasks remain unchecked.
