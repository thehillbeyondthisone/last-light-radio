# Compare motion takes

In the default editor, choose a motion and source take in Browser, then click
**Compare takes** in Viewer. Choose take B from the menu. Takes from the same
motion family, recipe revisions and recovered reference links are available
when their scene, subject and state contracts match.

Both takes show their seed, recipe revision, review version and status.
Pending and rejected takes may be inspected; this does not approve them or
allow their placement in a production sequence. Review controls below the
comparison continue to apply to source A.

- **Shared playback** uses the original MP4 cadence and a shared clock. The
  shorter take stops and holds its own final decoded frame. Neither take loops
  independently. Pause, step or scrub to request exact zero-based decoded PNG
  frames. Different frame rates are sampled against the displayed common clock.
- **Last → first** shows each take's loop boundary.
- **Last → held frame** shows the identical decoded exit frame on both sides.
- **Last → pose plate** shows the potential reset to the pinned conditioning
  plate. It does not replace any video frame.
- **Measure seams** reads verified media and reports actual decoded endpoints,
  conditioning comparisons and A's exit to B's entry. Saved lossless assembly
  samples are reported separately when available. Missing evidence and changed
  files produce visible messages.

RGB differences are advisory measurements, not quality scores or automatic
approval thresholds. The default measurement region is the original scene;
full-scene means can dilute small local changes. The Python comparison helper
also accepts an explicit diagnostic rectangle.

Comparison performs no generation, review, timeline or canon writes. Exact
frame inspection checks source checksums and bounds before decoding. Existing
start/middle/end media URLs retain their earlier behavior.

Verification and real-media contact sheet:
`artifacts/digest-trials-20261023/review-real/`. The isolated browser fixture
includes approved, pending and rejected takes, and deliberately different
durations. Usage and reproduction are recorded with the trial artifacts.
