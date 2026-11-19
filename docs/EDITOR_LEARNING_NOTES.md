# Editor learning notes

## Large preview and all tracks — 2026-10-31

- Creator requests the reviewed layout as an additional **View** option and small larger/smaller track buttons. This is direct authorization to install this scope. Implemented **View → Standard layout / All tracks overview**, with Standard initially selected and its previous panel size restored when returning. Timeline **− / +** controls step Reduced/Small/Medium/Large independently of Canvas height and time zoom; Original restores the previous mixed track heights. Row resizing remains available. Reselecting overview clears custom heights and restores Reduced rows. Installed frontend build and browser checks pass, including all 117 Reading segments and 17/17 overview rows; saved-library fingerprints remain unchanged. Evidence: `artifacts/layout-review-20261031/installed-view-menu.png`; production source/build backup: `installed-before-view-menu/` in that folder.
- Creator rejected the side-by-side timeline proposal and directed screenshot research of complicated Final Cut sequences. Retain the original monitor arrangement and full-width bottom timeline; do not solve density by moving the timeline into a narrow side panel.
- Apple FCP 7 help documents Reduced/Small/Medium/Large tracks, individually sized rows, independent horizontal zoom and separately scrolling video/audio regions. Inspected both the FCP 7 four-window screenshot and a densely layered modern Final Cut timeline. References and the rejected first proposal are preserved in `artifacts/layout-review-20261031/`.
- Revised separate preview displays 17/17 rows at 12px with an approximately 539 × 303px contained picture at 1440 × 804. Changing to Small rows preserves monitor size and scrolls; All tracks restores the overview. Individual row resizing and horizontal fit are independent. Nested Reading retains all 117 source segments. TypeScript/Vite and the nested regression pass. The application is still silent; independent video/audio scrolling remains unimplemented.
- The original review screenshot remains `artifacts/layout-review-20261031/fcp-stacked-1440.png`. The latest request authorizes installation of the optional layout and track controls above; broader editor work remains subject to the October 26 approval rule. Saved sequence settings and media remain unchanged.

## Approved nested beds and texture track — 2026-10-31

- Creator approves the nested-sequence solution and requests full texture-track control. These changes are authorized; broader deferred editor work remains separate.
- Automatic idle/hold regions now appear as nested beds. Reading opens to its 117 existing source segments; Episode sequence returns to the grouped view. Local nested playback respects its span and source audition is available. Grouping does not alter actual motion frequency, clip timing or placement gaps.
- A dedicated FX3 Video texture track exposes live on/off, strength 0–100% with exact entry, grain size 1–8px, seed/New pattern and Reset. Apply pins the settings to a new revision and CPU export. Undo and reopening restore the settings. The full-picture finish runs after motion/rain/steam; legacy plans without texture keep their original renderer/appearance.
- New cross-runtime tests prove identical grain bytes and frame offsets for preview/export; integration tests prove unchanged schedules, legacy-plan stability, persistence, moving static-hold texture and exact CPU-export timing. 209 tests ran (208 passed, one Windows symlink skip), TypeScript/Vite and 61-file Python checks passed.
- Isolated browser save/reload restored 65%/2px/seed 23. A real-scene 10s export with rain/steam passed all 240 timestamps/frames and six exit-frame hold checks. The actual `quickstart.bat --check` rebuilt and validated the updated interface. Original media, live rows and saved sequences remain preserved; no GPU requests or dependencies were added. Evidence/backups: `artifacts/nested-texture-editor-20261030/`.

## Applied rain fix and reading-track feedback — 2026-10-30

- Creator approves applying the rain fix, requests stronger texture, and finds back-to-back reading clips confusing and insufficiently FCP7-like. Only the reviewed rain code is applied; the track proposal still needs review.
- Installed `EditorCanvas`/`AmbienceCanvas` patch and rebuilt production assets. Installed playback reached frame 1241 (51.708s) through ten reading boundaries, with rain at frame 1241, no error and successful pause. Twelve ambience tests, TypeScript and Vite passed. Source/build backups and preservation audit are retained.
- Reader's saved `continuous` mode generates 116 idle events in 600 seconds, with no manual placements. Proposed presentation: one nested **Reading** bed, separately placed occasional actions, and inspectable source cuts when opened. The comparison uses the actual first two minutes of saved revision 3. Grouping preserves timing; changing repetition/quiet holds is a separate pacing decision. No track or schedule change is applied.
- New 2x/3x grain-setting auditions use the same clean rain/action/hold source, with full-size and three-way full/detail comparisons. All 576 frames/timestamps pass. Strength selection and integration remain pending review; no finishing setting is saved.
- All 46 original master/output media, 60 other application/workflow files and all studio rows match the before audit. No GPU requests, take approvals, placements or canon changes. Evidence: `artifacts/rain-applied-texture-v2-20261030/`.

## Unfinished rain and overall video treatment — 2026-10-30

- Creator reports that rain does not work and requests an overlay to make the complete scene feel like video rather than still graphics. Treat this as unfinished episode appearance; technical motion/containment tests are not visual approval.
- The completed ten-minute pilot has no rain/steam recipe or audio. The latest saved subject sequence includes v3 rain at 22% and steam at 14%, but remains a draft. Diagnose the reported failure in the relevant preview/export rather than assuming that enabling the layer solves it.
- [ ] Establish whether the rain is absent/frozen, visually unsuitable, or both; inspect full-scene and detail playback through holds and actions.
- [ ] Agree on an overall video treatment and preview its strength over the same scene with rain and a complete action/hold boundary. Exact overlay style remains undecided.
- [ ] Prove the combined look in a short review export before a new ten-minute final assembly. Review the final full-length visual/audio result before marking the episode complete.
- Proposed editor follow-up: expose the accepted rain and finishing treatment with clear controls and consistent preview/export behavior. Existing creator review of editor changes still applies; no application code, settings, placements or review statuses change with this note.

### Clarification and isolated proof

- Creator specifies frozen rain and chooses a subtle moving texture. A texture-strength audition is still needed for visual approval.
- Reproduced fatal handling of a canceled video `play()` promise. The displayed `AbortError` pauses the shared episode clock. A review-only patch ignores obsolete/canceled play promises while retaining visible handling of real playback failures.
- Found a second gate: the rain preview demands a newly prepared character composite for the current frame and deletes readiness while a video seeks/loads. The isolated patch retains the last valid effect source and keeps weather on episode time. Rain still excludes pinned subject support; fixed-plume steam keeps its action pauses. CPU canvas contexts address repeated pixel-readback cost; export rendering and original recipes remain unchanged.
- Final isolated browser playback reached timeline/rain frame 1295 (53.958s) through ten five-second idle changes, without an error; pause worked. Twelve focused ambience tests and isolated TypeScript/Vite checks passed. Preserve earlier diagnostic builds as evidence rather than applying their intermediate changes.
- A 24-second luma-grain audition on the existing rain/action/hold preview has full/detail paired comparisons, all completely decoded with verified timestamps. Source media, original application files and all studio table contents match the before audit. See `artifacts/rain-texture-20261030/README.md` for the exact proposed fix and reproduction.
- Applying the tested playback patch, approving the texture strength and integrating the finishing overlay are pending creator review. No live editor source, saved sequence, candidate approval or canon changed.

## Creator approval gate and linked radio cue — 2026-10-26

- Creator requests a passing car with restrained headlights reflected across
  the wet road as an additional animation trial. Keep it separate from saved
  sequences; a new candidate is not production approval or a new world fact.
- Creator specifies that the radio should flicker **when she adjusts it**.
  Treat this as an editorial synchronization requirement, not unrelated
  continuous radio ambience or a reason to regenerate the reader action.
- **Run every editor change past the creator for approval before applying it.**
  This includes code/UI, saved timing/effect settings and sequence placements.
  The older unchecked items below remain proposals, not permission to implement.
- Creator approved **this radio cue scope only** after the synchronized
  comparison: cue boundaries at frames 34–68 (1.417–2.833 seconds after action
  start), with restrained light dips/recoveries. Other editor proposals remain
  deferred; this approval does not approve the take for production.
- Approved first scope: one restrained, display-only light cue
  tied to the existing corrected radio-adjustment take's hand-contact interval.
  Preview onset/offset and strength together at full-scene and contact scale.
  Keep its timing relative to the action so moving the action preserves sync.
- Current editor moves complete approved takes but does not trim or retime
  them. The separate display-flicker mask overlaps the corrected reader mask,
  so placing the two as independent tracks is currently blocked. A synchronized
  light cue or a separately reviewed combined derivative needs explicit scope
  approval; do not bypass the general overlap validation.
- Minimal implementation choice: a separate combined CPU take carries the
  approved light timing inside the existing adjustment's frames and mask.
  Moving that whole take preserves sync without a new overlapping FX track or
  changes to editor code. Preserve the old action and require take review.
  The earlier 08:00 cue-sheet position remains an unapproved saved placement.
- Car trial observation: coherent headlight reflections can still be far too
  bright, and broad foreground protection can remove the late car silhouette.
  Review raw/composite playback over the whole route, retain real bars/leaves
  in front and inspect open gaps beside them. A future light-strength control
  must not dim the car body by reducing the whole clip's opacity. These remain
  findings for later approval, not newly authorized editor features.
- Approved radio cue delivered as pending CPU take
  `709d4298e10a5a72ff5f827de9806230`, retaining the corrected action's mask,
  profile and native timing. No editor implementation or sequence changed.
  Generic mask correction is unavailable on this derivative to prevent losing
  the cue; rebuild from the retained source plus explicit light transform.
  Evidence: `artifacts/radio-sync-proposal-20261026/`. Car auditions and their
  known light-balance/exit limitations: `artifacts/passing-car-20261026/`.

## 2026-10-23 — Add motion to more things in Apartment Pilot

Creator direction: create more scene animations first and learn from them.
Record editor changes here; defer implementing them until we have more evidence.
These are proposals, not completed features or approved canon.

### Observed before this batch

- The main toolbar says **New action**, the Browser says **Create action**,
  and idle creation lives inside **Subject setup**. There is no obvious
  scene-level **Animate something** entry for a plant, flame or light.
- The Effects panel exposes saved rain/steam regions. It cannot create an
  arbitrary new effect region. A new object can use the existing motion-recipe
  API, but that path is difficult to discover from the editor.
- Existing recipes include reader/cat actions and idles. The saved Apartment
  sequence has reader and cat tracks. This batch explores three additional
  subjects: hanging plant, right-hand candle and radio display.
- Opening **New action** offers My own action, Sip from a mug, Turn a page and
  A brief glance. Its default subject is the reader and its example is a sip.
  This reinforces a person/action interpretation even though object names work.
- The three new setups are idle recipes because they represent ongoing ambient
  motion. Their eventual candidates must be found/reviewed through Subject
  setup or Library, rather than the action-only Browser filter.
- Model context and visible motion area are separate: the plant needs fixed-pot
  protection, while the radio's tiny display needs a much closer detail view.
  A context crop alone does not show which pixels will actually be allowed to move.
- Reopening the editor exposes all three new subjects with empty approved pools
  without changing the saved episode. **Review idle takes** is in Subject setup;
  keep that capability but make its existence clearer from the main Browser.
- With the radio candidate completed, its subject still says **0 idle takes**
  and the pool says **No dedicated idle takes yet**, although **Review idle
  takes** contains **Take 1 · Needs review**. Distinguish total, pending review,
  approved and selected-in-pool counts in labels and empty states.
- Radio sample review: the generated middle frame brightens more strongly than
  requested; its geometry remains localized. A repeatable strength adjustment
  would be useful for reducing an otherwise promising take without a GPU rerun.
  This is a visual observation, not creator approval or a quantitative quality score.

### Proposed changes to revisit after review

- [ ] One discoverable **Animate something** command: pick/paint a region,
  name it, describe motion, then choose occasional action or ongoing ambience.
- [ ] Create a subject/region directly from the scene monitor; do not require
  an existing take or an understanding of the distinction between action and idle.
- [ ] Offer starting points for objects/environment (leaf sway, flame flicker,
  light variation). Keep text editable; do not imply automatic segmentation.
- [ ] Explain continuous ambience versus occasional actions before generation,
  and show where the result will appear in the Browser and timeline.
- [ ] Show pending idle/ambient takes in a clearly discoverable review list;
  approval, loop inspection and mask correction should be reachable together.
- [ ] Preview motion extent, feathered mask support and other subject overlaps
  before spending a GPU render. Include fixed-object protection and context crop.
- [ ] Offer a zoomed detail audition alongside the full scene, with start/end
  joins and actual-exit holds. Tiny flickers are hard to judge at scene fit size.
- [ ] Once useful takes are approved, allow choosing a safe continuous pool,
  quiet gaps, phase/seed and strength. Show exact loop limits and visible seams.
- [ ] Evaluate deterministic local effects for small flame/glow changes as an
  alternative to generating/changing the whole object. Decide after comparison.

### Experiment evidence

Batch setup, source hashes, requests, jobs and audits belong in
`artifacts/scene-animations-20261023/`. Results and additional observations are
recorded below. Approval remains a creator decision.

### Results from this batch

- Three H3 candidates completed: plant, candle/light and radio display, each
  90 frames at 24fps / 3.75 seconds. All 270 lossless composites preserved
  every protected pixel, and original/detail/combined media passed complete
  frame and timestamp checks. They remain unapproved.
- The plant has a localized leaf/vine-motion trial with a protected pot area.
  Judge motion amount, leaf texture and joins in the full-size/detail audition.
- The candle trial introduces a graphic teardrop flame in its middle instead
  of simply flickering the painted light. Record as needing revision; do not
  infer approval from successful rendering or source containment.
- A separate deterministic CPU comparison varies only the original candle and
  radio pixels' brightness. All 144 frames / six seconds passed protected-pixel
  checks, with exactly identical canonical first/last lossless frames. No new
  GPU request, library approval or editor integration was made for this trial.
  It provides a comparison for choosing a tool, not an implemented Effects feature.
- Consider an explicit **What should change? Shape/motion or light only** choice
  and an editable preview strength. A prompt alone did not constrain the candle
  to the original artwork. Preview mode should identify source-preserving effects.
- Existing four masters, 25 candidate/review records, eight approvals and two
  saved sequence summaries were preserved. There are exactly three new H3 jobs
  and pending candidates. Evidence: batch `validation.json`,
  `procedural-validation.json` and `preservation.json`.

## Creator feedback and street-activity follow-up — 2026-10-23

- Creator feedback: the other trials are promising, but the plant does not work
  because the original basket remains in front during the swing, and the swing
  has no convincing cause. Do not treat the plant trial as accepted.
- Prefer meaningful background activity: distant window lights switching and
  people entering/leaving the shop. New trials remain pending review; no named
  character or additional world lore is established.
- [ ] Add an optional plain-language motivation/context field or review prompt: why does
  this move here? Avoid unsolicited periodic movement merely to animate a region.
- [ ] Separate fixed foreground occluders from moving subject support, and
  preview the complete path behind/in front of them. A fixed exclusion mask
  cannot support a basket that should move with the plant. Moving the basket
  requires including it and its full path, plus reconstructing revealed background.
- [ ] Support persistent light states with sparse switch events and settled
  holds. A five-second return-to-start clip should not force lights to blink
  back immediately. Keep these distinct from continuous ambience.
- [ ] Background events need appearance/disappearance through doorways or
  occlusion, perspective scale, foot contact and reflection checks. Include
  stable shop signs/geometry and foreground rail protection in review.
- [ ] Preview a scale guide against a doorway or another known-sized feature.
  The initial step-out take made the person far too small despite the text
  direction. Retain the failed-scale take and compare an explicit adult-scale
  retry; do not silently replace it or call it approved.
- [ ] Let creators describe arrival, exit and dwell intervals, with sparse
  deterministic occurrence rules. A preview repetition is not a production cadence.
- [ ] Give regions an explicit depth relationship: exterior people belong
  behind window glass/rain and balcony structures, while room subjects may be
  in front. Revisit the current rain-versus-subject exclusion rule before
  production integration; masking rain out of a whole exterior motion area
  would remove the through-glass effect there.

Street-trial evidence is saved separately in `artifacts/street-activity-20261023/`.
Editor implementation remains deferred as requested.

### Street-trial results — completed 2026-10-24

- The two apartment lights use settled on/off states in a 30-second compressed
  demonstration, with switches at 4.5, 11, 17 and 24 seconds. The revised full
  window-interior masks avoid the first trial's bright leftover strips. All
  720 lossless frames preserved 2,072,457 protected pixels per frame; original
  and detail videos passed every frame/timestamp check. This remains an
  isolated review effect, not persistent-state integration into the editor.
- Three 124-frame / 24fps H3 takes were produced: arrival, an undersized
  step-out, and one adult-scale retry. All 372 lossless composites preserved
  protected pixels, with full original/detail decoding and timestamps verified.
  Twelve-sample passage sheets show arrival through the entrance and the
  adult-scale retry stepping out, pausing, turning and returning inside. Scale,
  style, foot contact, door motion and endpoint joins still need creator review.
- Prompt size guidance alone proved unreliable. Explicit adult/doorway size
  instructions improved this retry; this is evidence for a scale guide, not a
  promise that text can enforce exact geometry or trajectory.
- Baseline preservation passed: 32 original master/output files, 28 previous
  review records, four masters, eight approvals and two saved sequences remain
  intact. Exactly three new GPU jobs/candidates were added; none was approved.

## Departure, dark-window lighting and pilot pacing — 2026-10-24

- Creator wants a customer to leave and continue down the street, not turn back
  into the shop. A returning picture state can be achieved by leaving the visible
  area through a real occluder; it must not force the action itself to reverse.
- Creator rejects the look of the darkened-window preview. The supplied
  screenshot shows cut-out black patches. Set that visual approach aside and
  try lighting genuinely dark glass areas while preserving frames/balcony bars.
- Current creative target: an interesting **10-minute video**, with meaningful
  events approximately **45–120 seconds apart**. This is a target for the pilot;
  continuous rain/subtle idles are background ambience, not extra scheduled events.
- [ ] Separate action intent from endpoint picture state: **leave the shot**,
  **stay in a new place**, **return to the original pose**. Do not automatically
  append a return-to-start behavior that contradicts the creator's action.
- [ ] Preview the complete route, its end occluder and the time needed to walk
  it. Five seconds may constrain a natural distant departure; expose this limit.
- [ ] State-lighting masks must follow panes and structural occlusion with
  continuous tones. Avoid per-color threshold cut-outs; offer before/on/after
  comparisons at scene scale and at detail scale before a full export.
- [ ] Expose a seed-based meaningful-event spacing range (pilot target 45–120s)
  with a ten-minute preview, exact event times and quiet-tail diagnostics.
- [ ] Track semantic offscreen state independently of the empty picture:
  a customer entering the shop is still inside, while a departure leaves the
  location. Pair visitor arrival/departure and review identity continuity before
  treating separate generated takes as the same person.

New evidence belongs in `artifacts/departure-lighting-20261024/`. Editor changes
remain deferred, and new trials do not enter the approved production timeline.

### Results of the departure/light-on follow-up

- One H3 departure take completed (124 frames / 24fps). Passage samples show
  departure, rightward travel past the crates and toward the receding street,
  without reentry. Shrink/disappearance near the bicycles/tree remains a
  qualitative review point. All 124 lossless containment and full original/detail
  frame/timestamp checks passed; it stays unapproved.
- Two dark windows now receive continuous warm light instead of darkening
  already-lit neighbors. The first preparation exposed an opaque facade below
  one opening; the revised mask excludes it. All 576 lossless containment checks
  and three video frame/timestamp checks passed. The lit end states are held on.
- A separate seed-based ten-minute proposal contains eight meaningful events,
  from 00:45 through 09:15, with 45–120-second lead, event gaps and tail. Replaying
  the seed is identical and a different seed varies timing. It includes pending
  source ideas, is explicitly ineligible for release and does not save an editor plan.
- Preservation retained 35 earlier media/master files, 31 review records, four
  masters, eight approvals and two saved sequence summaries. One pending GPU
  job/candidate was added; no editor source or dependencies changed.

## Radio contact, travel-area clipping and window softness — 2026-10-24

- Creator requested a radio adjustment and identified clipping in the departure.
  Saved unmasked frames 56/62/67 confirm the full customer is present; the old
  diagonal mask cuts through the coat/legs. Widening that support and following
  the real sloping rail is a mask-only correction, not a new generated action.
  Evidence: `artifacts/radio-compositing-20261024/customer-mask-diagnosis.png`.
- [ ] Preview the route against actual unmasked source frames, and show the mask
  boundary during playback. An entire-passage/contact-sheet check is needed;
  checking three samples and protected pixels alone missed the visible clipping.
- [ ] Foreground protection should follow the observed shape, not an approximate
  horizontal cutoff. Keep soft support edges separate from true occluder geometry.
- [ ] Radio/prop actions need a contact view covering the hand, knob, torso reach,
  book and mug, plus original/end-pose review. Do not infer contact from a prompt.
- [ ] Broad reaches can overlap other subjects' saved regions. Review the full
  interaction and mask conflicts before independent-track production integration.
- Creator wants softer, more plausible window light. Keep structural edges
  sharp while feathering illumination inward, introducing off-centre light falloff
  and preserving cool reflections, shadows and texture. Provide previous/soft/
  gentler comparisons; simply filling the pane evenly produces a flat orange panel.

New experiment evidence is in `artifacts/radio-compositing-20261024/`. Editor
implementation and production approval remain deferred.

### Results

- One radio-adjustment candidate completed 124 frames / 24fps. Samples show
  reach/contact at the front controls and return to reading; detailed hand/prop
  and join review remains required. All 124 lossless protected-pixel checks and
  full/detail frame/timestamp checks passed.
- Corrected customer candidate reuses the exact 124 source PNG references,
  widens the walking area and follows the visible sloping rail. All 124 lossless
  containment checks and full/detail/paired frame/timestamp checks passed. The
  diagonal clipping was compositing, not a missing body in model output.
- Soft/gentler stills and a 384-frame soft-light preview show inward feathering,
  off-centre falloff and retained source tones. All lossless containment and
  three output-video frame/timestamp checks passed. Realism remains a creator
  judgment; the gentler option is a still, not a second video render.
- Preserved 36 earlier master/output files, 32 review records, four masters,
  eight approvals and two saved sequence summaries. Added one GPU radio job,
  its candidate and one separate CPU customer correction; no editor code changed.

## Head travel and adding subjects — 2026-10-25

- Creator says the radio action otherwise looks good but the head clips during
  the lean. Saved unmasked frames show complete hair/headphones; the diagonal
  top edge of the original mask removes them. This is another support-mask
  error, not missing generated anatomy. Do not replace the successful action.
- A separate CPU correction expands only the head's travel area inside the
  existing generated crop and reuses all 124 source PNGs. Whole-passage samples
  show the restored shape. All 124 lossless comparisons preserve pixels outside
  the added area, and the protected-pixel audit passes. Approval remains pending.
- Creator asks whether the editor can add a subject. It currently can, implicitly:
  **Create action / New action → Who moves?** accepts a new name, then description,
  area and **Save for later** create the subject without rendering. It appears in
  Subjects and timeline lanes. Subject setup itself only configures existing names.
  The existing isolated new-subject regression passes; this is a discoverability
  problem, not an absent backend capability. Usage is clarified in `docs/EDITOR.md`.
- [ ] Put **Add subject / Animate something** in Subjects and on the scene Canvas.
  Let the creator name and paint the subject before requiring a first action;
  explicitly offer occasional action, idle and lighting/environment behavior.
- [ ] Motion-area guidance must include the whole body arc, hair, headphones,
  clothing and handled props, not only the starting silhouette. Show raw and
  composite playback with the mask boundary and inspect the complete passage.
- Keep editor implementation deferred while these animation trials continue.
  Evidence: `artifacts/radio-headroom-20261025/`.
