"""Offline authoring handoff prototype. No model, network, renderer, or NLE writes."""
import argparse, hashlib, json, pathlib, sys, uuid

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def validate(book):
    errors = []
    if not isinstance(book, dict):
        return ["Book must be an object"]
    if book.get("schema") != "director.draft.v0":
        errors.append("Unsupported schema")
    fps = book.get("fps", {})
    if not isinstance(fps, dict) or any(type(fps.get(k)) is not int or fps[k] <= 0 for k in ("num", "den")):
        errors.append("FPS must be positive integer numerator/denominator")
    if type(book.get("duration_frames")) is not int or book["duration_frames"] <= 0:
        errors.append("Duration must be positive integer frames")
    for key in ("title", "brief"):
        if not isinstance(book.get(key), str) or not book[key].strip():
            errors.append("Missing " + key)
    locations = book.get("locations", [])
    if not isinstance(locations, list) or any(not isinstance(x, dict) for x in locations):
        errors.append("Locations must be objects")
        locations = []
    location_ids = {x.get("id") for x in locations}
    shots = book.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= 128:
        return errors + ["Use 1..128 shots"]
    cursor, ids, previous = 0, set(), None
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append(f"Shot {index} must be an object")
            continue
        sid = shot.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            errors.append(f"Shot {index}: invalid/duplicate ID")
        else:
            ids.add(sid)
        if shot.get("scene_id") not in location_ids:
            errors.append(f"{sid}: unknown scene")
        start, end = shot.get("start"), shot.get("end")
        if type(start) is not int or type(end) is not int or start != cursor or end <= start:
            errors.append(f"{sid}: invalid contiguous interval")
        else:
            cursor = end
        for key in ("beat", "purpose", "framing", "action", "sound", "risk"):
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                errors.append(f"{sid}: missing {key}")
        before, after = shot.get("state_in"), shot.get("state_out")
        if not isinstance(before, dict) or not isinstance(after, dict) or not before or before.keys() != after.keys():
            errors.append(f"{sid}: state contracts must use the same nonempty keys")
        else:
            if previous is not None and previous != before:
                errors.append(f"{sid}: continuity mismatch")
            previous = after
    if cursor != book.get("duration_frames"):
        errors.append("Shot coverage does not equal duration")
    return errors

def compile_book(book, max_frames=124):
    errors = validate(book)
    if errors:
        raise ValueError("; ".join(errors))
    if type(max_frames) is not int or max_frames <= 0:
        raise ValueError("max_frames must be positive")
    sha = hashlib.sha256(canonical(book)).hexdigest()
    slots, blockers, jobs = [], [], []
    for shot in book["shots"]:
        sid = shot["id"]
        slot_id = "plannedshot." + uuid.uuid5(uuid.NAMESPACE_URL, book["title"] + ":" + sid).hex
        duration = shot["end"] - shot["start"]
        refs = shot.get("references", {})
        refs = refs if isinstance(refs, dict) else {}
        issues = []
        if duration > max_frames:
            issues.append("Interval exceeds inspected adapter capability; do not silently split")
        if not refs.get("first_frame"):
            issues.append("First-frame reference unresolved")
        if shot.get("review") != "approved":
            issues.append("Shot plan remains unapproved")
        if issues:
            blockers.append({"shot_id": sid, "reasons": issues})
        brief = shot["framing"] + ". " + shot["action"] + " Sound: " + shot["sound"] + "."
        slots.append({"id": slot_id, "label": sid + " " + shot["beat"], "brief": brief,
                      "start_frame": shot["start"], "end_frame": shot["end"],
                      "first_frame_id": None, "last_frame_id": None})
        jobs.append({"shot_id": sid, "content_sha256": hashlib.sha256(canonical(shot)).hexdigest(),
                     "requested_frames": duration, "prompt_candidate": brief,
                     "status": "dry_run_only", "submitted": False})
    if book.get("audio", {}).get("master") is None:
        blockers.append({"scope": "film", "reasons": ["Final audio master unresolved"]})
    return {"schema": "director.compilation.v0", "book_sha256": sha,
            "mode": "dry_run_only", "can_submit": False,
            "warning": "Projection is not a save request: real sequence revisions, references and approvals must be resolved.",
            "slots": slots, "jobs": jobs, "blockers": blockers}

def writer_packet(idea):
    if not idea.strip():
        raise ValueError("Idea must not be blank")
    return {"schema": "director.writer-packet.v0", "idea_verbatim": idea,
            "mode": "authoring_only",
            "instructions": [
                "Develop two distinct short treatments. Preserve the supplied idea; mark invented details provisional.",
                "For the selected draft, write causal beats and an ending before choosing shots.",
                "Write action and any dialogue. Each shot must reveal, cause or pay off a story beat.",
                "Track cast, wardrobe, geography and prop state. Do not silently rewrite approved canon.",
                "Return a director.draft.v0 book matching the supplied example contract.",
                "Timing is provisional until the audio and references are reviewed. Do not claim footage exists."],
            "backend": "No LLM configured. A person or authorized assistant supplies the authored book."}

def review_text(book, result):
    lines = ["# " + book["title"], "", "PROVISIONAL DESIGN REVIEW. No footage generated.", "", book["brief"], ""]
    for s in book["shots"]:
        lines.extend([f"## {s['id']} | frames {s['start']}..{s['end']} (exclusive out)",
                      s["purpose"], "", s["framing"], s["action"],
                      "Sound: " + s["sound"], "Risk: " + s["risk"], ""])
    lines += ["## Readiness blockers", json.dumps(result["blockers"], indent=2), "",
              "Structural validation is not an artistic, continuity-in-pixels or lip-sync approval."]
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    packet = sub.add_parser("brief")
    packet.add_argument("idea")
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("book")
    compile_parser.add_argument("--out", required=True)
    compile_parser.add_argument("--max-frames", type=int, default=124)
    args = parser.parse_args()
    if args.command == "brief":
        print(json.dumps(writer_packet(args.idea), indent=2))
        return
    book = json.loads(pathlib.Path(args.book).read_text(encoding="utf-8-sig"))
    result = compile_book(book, args.max_frames)
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    (output / "compilation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "review.md").write_text(review_text(book, result), encoding="utf-8")
    print(json.dumps({"output": str(output), "shots": len(result["slots"]), "submitted": False,
                      "blocker_groups": len(result["blockers"])}))
if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

