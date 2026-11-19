# Which client to use (added 2026-11-16)
Read this together with START_HERE.md, which is unchanged.

- Use `comfyui_client_safe.py`. Do NOT use `comfyui_client.py`: it is a broken draft, kept only as a record. Its submit sends the POST and then crashes, losing the prompt_id; its preflight lists node classes, not model files.
- The safe client follows the START_HERE protocol. Run `python comfyui_client_safe.py --help` for commands:
  1. `preflight A02.workflow.json --out preflight.json`: read-only. Checks node classes, model and image choices, and the queue, and hashes the reference image.
  2. `prepare A02.workflow.json <NEW experiment dir> --variable "..." --planned-start "..." --planned-end "..."`: local only. Sets a unique output prefix and writes experiment.json.
  3. `submit <dir> --confirm`: ONLY after the GPU owner agrees. It sends one POST per directory and never resends.
  4. If submit exits with code 3 (outcome unknown), run `reconcile <dir>`. Never resubmit.
  5. `poll <dir> --wait`, then `download <dir>`. Then do the START_HERE QA gates (full decode, probe, review) and fill in the observed state in experiment.json.
- What has been verified (2026-11-16): preflight and prepare against the real server (A01..A05: 0 problems). Submit, reconcile, poll and download have run ONLY against the offline mock in `comfyui_client_safe_test.py` (`python -B comfyui_client_safe_test.py`, 20/20). The first real job is the first real test of those steps. Inspect its history.json rather than assuming the output format.
- Reference SHA256 at that check (compare with your own preflight):
  - van-mara-reference-20261115.png 87961c482be50b1a079cf0b5f6cad011d7e3de6a18fecf084f5e2933cf9cf177
  - mara-mug-down.png 36c7d7afb61788c4e63950d42367d0181dd989fd183fcb028eac82944c019aa9
  - mara-at-rear-doors.png bd1a1a687cb140b15d1ebf94e34e2fce3e84a8a9545db2188c03ce3dd1900186
  - mara-outside-rear.png ec0eb2a71660ff8eadcab6bb9b48c36fa4ae856aac8dd9042b1d230ea4b0bd5b
- Another worker uses this GPU (recent jobs under `fable-animals-20261116/`). An empty queue is not permission to submit.
