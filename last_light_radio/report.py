"""A self-contained schedule report for the first headless milestone."""

from html import escape


def schedule_report(manifest: dict) -> str:
    fps = manifest["fps"]
    rows = []
    for event in manifest["events"]:
        label = event.get("variant_id", "Quiet hold")
        reasons = ", ".join(sorted({item["code"] for item in event["skipped"]})) or "—"
        rows.append(
            f'<tr class="{escape(event["kind"])}">'
            f'<td>{event["start_frame"] / fps:.3f}s</td>'
            f'<td>{event["end_frame"] / fps:.3f}s</td>'
            f'<td>{escape(label)}</td><td>{escape(event["entry_anchor"])}</td>'
            f'<td>{escape(event["reason"])}</td><td>{escape(reasons)}</td></tr>'
        )
    title = "Last Light Radio · Schedule proof"
    fixture = "Mock fixture · no production media or approved canon" if manifest["fixture"] else "Draft schedule"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#101b20;color:#e4e7df}}
body{{max-width:1200px;margin:40px auto;padding:0 24px}}h1{{font-weight:500;letter-spacing:-.04em}}
.eyebrow{{color:#e4b978;text-transform:uppercase;letter-spacing:.15em;font-size:12px}}
.cards{{display:flex;gap:16px;flex-wrap:wrap;margin:28px 0}}.card{{background:#1c2b30;padding:18px 24px;border-radius:10px}}
.card strong{{font-size:24px;display:block;color:#f5dfb0}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{padding:14px 10px;border-bottom:1px solid #304046;text-align:left;vertical-align:top}}
th{{color:#99b2b5}}.clip td:first-child{{border-left:3px solid #e4b978}}.hold{{color:#9fb2b4}}
code{{overflow-wrap:anywhere}}.table{{overflow-x:auto}}a{{color:#e4b978}}
</style></head><body><p class="eyebrow">Music for places that are still awake</p>
<h1>Last Light Radio</h1><p>{fixture}</p>
<div class="cards"><div class="card"><strong>{manifest["duration_frames"] / fps:g}s</strong>Exact requested duration</div>
<div class="card"><strong>{manifest["seed"]}</strong>Reproducible seed</div>
<div class="card"><strong>{len(manifest["events"])}</strong>Timeline segments</div>
<div class="card"><strong>{manifest["fps"]} fps</strong>Frame timebase</div></div>
<p>World <code>{escape(manifest["world_id"])}</code>, revision {manifest["world_revision"]}.
All picture events use one exclusive full-frame lane. Holds retain the current approved anchor.</p>
<p>Input fingerprint: <code>{manifest["input_hash"]}</code></p>
<p><a href="episode_manifest.json">Manifest JSON</a> · <a href="event_log.md">Detailed event log</a></p>
<div class="table"><table><thead><tr><th>Start</th><th>End</th><th>Picture</th><th>Entry anchor</th>
<th>Selected because</th><th>Other eligibility reasons</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
</body></html>\n'''
