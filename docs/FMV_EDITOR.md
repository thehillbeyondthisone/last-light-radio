# FMV story tool (first integrated slice)

The Film workspace remains an FCP7-style editing desk. Its **FMV** Viewer tab adds an interactive story layer above existing saved sequences; it does not change the linear timeline or the separate Scene animation composer.

## Authoring model
- A Film project currently owns one versioned story.
- Each named story node points to a saved sequence in that same project. Build and mix that sequence with the normal timeline first.
- Choose a start node. Mark a node terminal, or give it one to eight labeled choices leading to other nodes.
- Choices appear only after the node's movie ends. A loop back is allowed. Rehearsal stops after 256 transitions to bound accidental cycling.
- Save persists the story separately from sequences. Stale revisions are rejected rather than overwriting a newer edit. Local draft undo does not claim durable command-level undo.

## Freeze and rehearse
Export each referenced linear sequence first, then freeze the saved story. Freezing never starts generation or automatically renders a missing sequence. Every node must be reachable from the start.

A frozen story pins each sequence revision and manifest, copies its verified mixed MP4 into immutable content-addressed storage, and retains source review/provenance. Later edits to a linear sequence cannot quietly change that frozen story. A revoked source approval or corrupt media blocks validation/playback; it is not silently ignored.

Rehearsal plays the frozen movie in the existing Canvas with its already-mixed audio. At the end, choose a branch, or restart/exit. Normal editing controls are inactive only during rehearsal; exiting returns to the original linear cut. Rehearsal is not a saved player-game state.

## Verified source relationship and limitations
This is sequence-level FMV authoring, not a replacement for Titanic's existing runtime. Titanic already has original dialogue IDs, learned/journal flags, original voice and reviewed performance mappings. No Titanic runtime files or original game saves are changed by this feature.

Not implemented here: automatic next edges, timed hotspots, inventory/conditions, actor placement, original-dialogue import, performance-direction/body-reference tools, portable standalone game packaging, or deployment. The frozen manifest and local Canvas rehearsal are the present deliverable; do not call this a shipped Titanic game exporter.

Evidence and technical verification live under `artifacts/film-fmv-20261113`.
