# Generating and auditioning new / extended clips: review (2026-11-15)

Read from `FilmGeneration.tsx`, `GenerationFlow.tsx`, `FilmShotPlan.tsx`, `FilmEditor.tsx` (Continue button, pending blocks), `generation_timeline.py` (stages), plus the live library (6 jobs, recipe "H3 joint video + sound", 124 frames). Nothing was generated, imported or approved.

## How it works today

There are three ways in, and they all end in the same long form in the Viewer's **H3 take** tab.

| Path | Start | Steps to a clip on the timeline |
|---|---|---|
| **New clip** | Viewer > H3 take | Label, brief, worker URL, seed, optional first/last reference frames, destination (sequence + "insert before shot N") > **Check worker & recipe** > **Generate video + sound** > wait (job list polls) > **Import video & production sound** > **Review picture** (Viewer Video tab: tick "I reviewed", **Approve take**) > **Audition / review sound** (Audio tab: review, approve) > back to H3 take > pick boundary + audio policy > **Place reviewed clip on V1** |
| **Extend a shot** | Select shot > inspector **Continue…** (only when the cut is saved *and* rendered) | Same as above, with the form prefilled from the shot's last rendered frame and locked to "insert after this shot, skip 1 generated frame". Becomes unusable if the sequence changes at all ("no automatic retargeting"). |
| **Planned interval** | Timeline In/Out > Shot plan > Make shot from selection > brief + references > Save plan > **Prepare generation** | Then the H3 take form (brief locked) > check > generate > import > review in Viewer > back to **Shot plan** > **Fit picture to interval** (picture only). |

The minimum for a new clip is about 9 actions across 3 tabs. Extend and Planned add a precondition each (render first; save a plan first).

## What makes it unclear or slow (with evidence)

1. **One 2,000 px form in a monitor a few hundred px tall.**
   - The H3 take panel measured 2,078 px.
   - The fields you need (brief, references, Generate) sit between a recipe header and a job list that grows forever.
   - You scroll constantly.
2. **Finished jobs look unfinished.**
   - All 6 jobs in the library are `success` and imported; 5 were sent to a sequence, of which 2 are placed and 3 are waiting for review.
   - Yet every one still shows **Import video & production sound** and **Check existing job (no resubmit)**: the server keeps `ready_to_import` and `can_resume` true after import.
   - In the job list it is impossible to tell which take needs you.
3. **Check, then Generate.**
   - Generate stays disabled until a separate worker check passes.
   - The check expires and is cleared by any field change, even the seed or label.
   - It reads as two buttons for one intent.
4. **Import is a manual step, and the "what next" lives in one tab.**
   - A finished job waits for **Import** before anything can be reviewed.
   - The timeline does draw a striped block for each request with its stage (for example "Needs review"), but it is not clickable into the next step. The actions (import, review, place) are only in the H3 take job list, and only for the open sequence's blocks.
5. **Audition is split across tabs and away from the cut.**
   - Picture is approved in the Video tab and sound separately in the Audio tab.
   - Placement happens back in H3 take, or in Shot plan for planned intervals.
   - You never see the candidate *in context* (the outgoing shot's tail, the take, the incoming shot's head) before it goes in. That is the question you are actually answering.
6. **Placement runs beside the editor's own tools.**
   - Generated clips go in through their own "insert before shot N" control and an audio-policy dropdown.
   - An approved take *can* already be edited in from the Browser with Insert / Overwrite / Replace, but picture only: its production sound does not come with it.
   - So "generate something to fill this gap" and "put this take in with its sound at my In point" have no direct route.
7. **Extend is fragile.**
   - **Continue…** needs a saved *and* rendered cut, and the prepared continuation dies on any later edit.
   - The edit could be a marker or a trim elsewhere.
   - The button is disabled with a tooltip, not explained.
8. **Draft state leaks.**
   - The form persists label, brief, references, continuation and plan binding in `localStorage` across sequences and sessions.
   - A continuation or plan binding prepared earlier reappears on a different sequence. It is then flagged stale, but only in red text inside the form.
9. **Job list is library-wide.** Jobs for every sequence appear together, newest at the bottom, each with an expanded metadata block.
10. **Alternates are not first-class.** Several takes of the same moment are only comparable inside Shot plan. There is no "next / previous take" on a timeline clip (the Scene editor has PageUp/PageDown for this).
11. **Words drift.** "H3 take", "film take", "candidate", "source", "take" and "clip" are used for the same thing in different panels.

## Proposal

The review gate stays: picture and sound are still approved explicitly, by a person, after watching. Nothing auto-approves or auto-places.

**A. UI-only, can be done now (no server change)**
1. **Job cards that say what to do next.**
   - One line per job: stage chip (Generating · Ready to audition · Approved · Placed · Failed) and a single next-action button.
   - Hide Import and Check once `video_asset_id` exists.
   - Filter to this sequence by default, with a "Show all" toggle.
   - Collapse metadata.
   - Done and placed jobs fold away.
2. **Generate does its own check.**
   - Generate runs the preflight and, if it passes, submits in the same click.
   - On failure it shows the check's errors and submits nothing. The worker is still never contacted without a click.
   - Seed and label changes no longer void a check.
3. **Split the form.** The brief, references and Generate go at the top. Recipe details, the worker URL and the seed move under "Settings".
4. **Audition in context.**
   - "Audition" on a ready take plays outgoing tail (2 s) > take with its own sound > incoming head (2 s) in the Viewer, without placing anything.
   - Approve picture + sound sits beside it as one panel with the existing "I reviewed" tick. It still records two approvals.
5. **Place with the editor's tools.**
   - "Use this take" loads the approved take into the Viewer as a source, so you place it with Insert / Overwrite / Replace (F9/F10/F11) at the In point, playhead or into a gap.
   - The linked production sound comes with it as today's audio placement.
6. **Entry points from the timeline.**
   - Right-click (or a key) on a gap gives **Generate to fill this gap**, which prefills duration, destination and the neighbouring frames as first/last references when the recipe supports it.
   - On a shot it gives **Extend this shot**, which runs today's Continue.
7. **Drafts per sequence.** Key the localStorage draft by sequence, and drop a stale continuation/plan binding with a visible note instead of carrying it over.
8. **One vocabulary.** "Take" for a generated or imported source; "clip" for a take placed on the timeline.

**B. Needs dot (server)**
1. **Clear the job flags.** Set `ready_to_import` / `can_resume` false once imported, so A1 doesn't rely on a client-side guess.
2. **Auto-import on success**, as a server-side step that is still a candidate, never approved. This removes the manual Import click.
3. **Continuations without a full render.** Extract the boundary frame from the saved source shot (source frame = In + duration − 1) when no current render exists. Allow retargeting when only unrelated parts of the cut changed.
4. **Placement into a gap / at a frame.** Today placement takes an `insert_index`. A gap-aware destination would let "fill this gap" place by frame range.

## Suggested order
A1, A2, A3 first: small and immediately less confusing. Then A4 and A5, which change how takes get into the cut. Then A6 and A7. B1 and B2 go to dot alongside.

## Status
- 2026-11-15: A1, A2, A3 built. A2 was not exercised live (a Generate click was blocked by the permission check); a passing check with warnings needs a second click. A4-A8 and B1-B4 open.
- 2026-11-16: optional Generation guide and requested-take block card added (partly covers A6). Server B5 requested: withdraw a timeline request.
- 2026-11-17: one review per take (picture + sound together, Boden) and a History tab for all runs. Next: one Generate tab with destination before/after a clip, at the playhead, at the end, or library only.
