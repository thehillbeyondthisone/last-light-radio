# CozyClay keyframe packages and local H3

The import-only adapter accepts a native CozyClay keyframe ZIP and creates a
saved Last Light Radio motion recipe. Generation remains a separate action
using the existing recovered ComfyUI bindings. It adds no application
dependency on CozyClay, its agent or a cloud model.

Inspect a package without creating a library or submitting work:

```powershell
python -m last_light_radio.cozyclay_adapter path/to/pack.zip --inspect-only
python -m last_light_radio.cozyclay_adapter --help
```

For import, supply a destination store, recipe/subject names, named entry and
exit states, explicit seed and VAE, a source-pixel motion polygon and
`--fixed-camera`. `--motion-direction` supplies explicit H3 action text when
the original exported prompt delegates motion to its reference video.
Use `--expected-sha256` to require the package inspected earlier. The complete
command for this project's isolated trial is recorded in its evidence folder.

The adapter validates one shot, both opaque endpoint PNGs, matching geometry,
timing, camera metadata and the input archive. It rejects unsafe paths,
duplicate/unknown members, excessive sizes and unsupported timing rather than
silently changing the shot. Current native recipe timing is 24fps with 39, 90
or 124 frames. A nominal five-second shot must be authored/exported at the
chosen exact duration; 124 frames are 5.166667 seconds.

Imported endpoint originals, the exact ZIP and source members are preserved
with hashes. Source provenance, original camera/prompt, producer identity and
the explicit H3 adaptation are part of the immutable recipe before its ID is
calculated. Reimporting identical inputs is idempotent. Import never approves
clips, changes world canon or submits a render.

The graph receives first/last conditioning and explicit text. A reference
video is retained for human comparison. Depth, normals and reference-video
motion are not graph inputs in the recovered workflow. Matching endpoints
therefore does not prove that H3 follows the interior 3D trajectory.

Camera endpoint metadata cannot prove that all interior camera keys are fixed.
The importer records the creator's acknowledgement. The isolated runtime trial
additionally samples every actual source camera frame. New camera motion would
need a separately tested workflow/scene contract.

CozyClay is run separately from pinned source for the experiment. Its upstream
license and third-party asset notices remain in that checkout; the trial uses
original primitive geometry and excludes the bundled raw FBX rigs.
