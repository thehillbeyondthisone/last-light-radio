# Make a motion

For an existing scene, open **Make a motion → New motion**. Importing a new
scene opens this guide directly.

1. **Describe.** Choose a starting point—your own action, quiet idle, sip,
   page turn or glance. Name the subject and describe one complete action.
   You can edit the suggested wording. Rendering instructions automatically
   preserve the camera, identity, props and style and request a return to the
   starting pose. The description and compiled instructions are both saved.
2. **Mark area.** A known subject starts with its latest saved area. Choose
   another saved area or an empty one if useful. Draw a box to begin, use
   **Include** along the movement path and **Protect** around nearby subjects.
   Include the whole action: for a sip, the face, arm, mug and space between
   them. **Undo** reverses a stroke. Keyboard area controls are also available.
3. **Make a take.** Check the protected-scene preview. **Make first take**
   saves the motion and explicitly requests generation. **Save for later**
   saves the setup alone. Watch the result in the motion workspace, compare
   it with the still and choose **Review this take** before approving it.

Take length, seed, model and motion name live under **More options**. The
guide uses the already configured model variant; missing models still block
submission visibly. A complete returning action defaults to the proven
5.17-second H3 setting. This is guidance, not a guarantee that the model will
perform the action or match its endpoints exactly.

**Make another take** uses a fresh variation seed by default. To repeat a
particular seed, select **Repeat this seed** under **Take settings**. Every
actual prompt, seed, workflow and source image remains pinned to its take.

## Fix a clipped hand or prop

Choose **Adjust motion area** below a supported take. Switch among **Start**,
**Mid-action** and **End** to see the saved generated pixels before masking.
Paint with **Include / Protect**, then choose **Apply area & preview**.
The new version returns to the workspace for review. It uses the existing
motion frames and makes no additional GPU request. Its original is retained,
and an old approval never transfers automatically to the corrected version.

The dashed boundary is the frame the model originally generated. Adjustments
stay inside it. Motion that needs more room requires a new take with a wider
area. Mask changes cannot recover an action the model never performed.
The source-frame preview is an editing aid; it is not an approved composite.

## Scope

These starting points are ordinary text templates. No live AI agent directs
the scene or makes approval/episode decisions. Painting is manual; the app
does not detect subjects or invent canon. Masters stay immutable.

For a different ending pose, use **More options → Set up a different ending
pose** to open the established pose editor. Historical recipes remain
editable through that editor. Timeline, behavior-frequency, audio and shared
world authoring are separate work. The fixed tabletop steam still needs an
episode-level check before a moving-mug clip is used in an ambience export.

## Local verification

```powershell
.\scripts\run.ps1 test
.\scripts\run.ps1 check
npm run build --prefix frontend
```

Tests use fake clients and temporary libraries. The area API validates PNG
dimensions/alpha, rejects empty/out-of-crop masks and appends immutable recipe
and candidate records. Recomposition retries verify cached media and can
recover an encoded candidate after interrupted registry publication.
See `artifacts/guided-motion-20261021/README.md` for browser evidence.
