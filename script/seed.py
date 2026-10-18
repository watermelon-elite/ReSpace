"""Replace only the approved middle of the contained ReSpace film package."""

from copy import deepcopy
import json
from pathlib import Path

from vlog_format.production_validation import tokenize_narration

DATA = Path(__file__).parent / "data"


def timecode(seconds):
    whole = int(seconds)
    fraction = f"{seconds % 1:.1f}"[1:] if seconds % 1 else ""
    return f"{whole // 60:02d}:{whole % 60:02d}{fraction}"


def replace_middle(content, definition):
    """Keep the current opening/closing records, changing only their word offsets."""
    result = deepcopy(content)
    script = result["script"]
    old_words = script["words"]
    positions = {word["id"]: index for index, word in enumerate(old_words)}
    start, end = definition["start_seconds"], definition["end_seconds"]
    first = next(beat for beat in script["beats"] if beat["start_seconds"] == start)
    closing = next(beat for beat in script["beats"] if beat["start_seconds"] == end)
    first_index, closing_index = positions[first["start_word_id"]], positions[closing["start_word_id"]]
    left, right = old_words[first_index]["start_char"], old_words[closing_index]["start_char"]
    prefix, suffix = script["narration"][:left], script["narration"][right:]
    middle = "\n\n".join(beat["narration"] for beat in definition["beats"]) + "\n\n"
    script["narration"] = prefix + middle + suffix
    words = tokenize_narration(script["narration"], version_id=result["version_id"])
    middle_count = len(tokenize_narration(middle, version_id=result["version_id"]))
    delta = middle_count - (closing_index - first_index)

    def protected(record):
        kept = deepcopy(record)
        for key in ("start_word_id", "end_word_id"):
            index = positions[kept[key]]
            assert index < first_index or index >= closing_index, record["id"]
            kept[key] = words[index + (delta if index >= closing_index else 0)]["id"]
        return kept

    def outside(record):
        return record["end_seconds"] <= start or record["start_seconds"] >= end

    beats = [protected(beat) for beat in script["beats"] if outside(beat)]
    tracks = {lane: [protected(block) for block in blocks if outside(block)]
              for lane, blocks in result["visual_tracks"].items()}
    directives = [protected(item) for item in result["subtitle_directives"]
                  if positions[item["end_word_id"]] < first_index
                  or positions[item["start_word_id"]] >= closing_index]
    shots = [shot for shot in result["storyboard_shots"] if outside(shot)]
    cursor = first_index
    for number, source in enumerate(definition["beats"], 1):
        tokens = tokenize_narration(source["narration"], version_id=result["version_id"])
        count = len(tokens)
        assert [w["text"] for w in words[cursor:cursor + count]] == [w["text"] for w in tokens]
        first_second, last_second = source["start_seconds"], source["end_seconds"]
        shot_id = f"shot-middle-{number:02d}"
        beats.append({
            "id": f"beat-middle-{number:02d}",
            "start_word_id": words[cursor]["id"], "end_word_id": words[cursor + count - 1]["id"],
            "start_seconds": first_second, "end_seconds": last_second,
            "speaker": "ReSpace team", "delivery": "To camera, continuing over demos and cutaways.",
            "story_purpose": source["title"], "evidence_ids": [],
            "audio": "Typing, a small pause and the presenter's look to camera; leave the remainder unvoiced."
                     if number == 11 else "Connected team narration; allow the demonstrated action and result to register.",
        })
        shots.append({
            "id": shot_id, "number": 10 + number,
            "start_seconds": first_second, "end_seconds": last_second,
            "section": source["title"], "voiceover": source["narration"],
            "picture": " ".join(source["directions"]), "sound": beats[-1]["audio"],
        })
        for lane in tracks:
            for entry in source.get(lane, []):
                a, b = entry["word_range"]
                assert 0 <= a <= b < count, entry["id"]
                block = {key: deepcopy(value) for key, value in entry.items() if key not in ("exact_action", "word_range")}
                block.update({
                    "start_word_id": words[cursor + a]["id"], "end_word_id": words[cursor + b]["id"],
                    "contributors": [], "framing": "16:9 landscape.",
                    "recording_requirement": {
                        "id": f"asset-{entry['id']}",
                        "timing_trigger": f"{timecode(entry['start_seconds'])}–{timecode(entry['end_seconds'])}",
                        "exact_action": entry["exact_action"],
                    },
                })
                if lane == "base":
                    block["shot_ids"] = [shot_id]
                    block["recording_requirement"]["natural_audio"] = beats[-1]["audio"]
                tracks[lane].append(block)
        if source.get("emphasis"):
            phrase = source["emphasis"]
            offset = source["narration"].index(phrase)
            selected = [i for i, token in enumerate(tokens)
                        if offset <= token["start_char"] and token["end_char"] <= offset + len(phrase)]
            assert 1 <= len(selected) <= 3
            directives.append({
                "id": f"subtitle-middle-{number:02d}",
                "start_word_id": words[cursor + selected[0]]["id"],
                "end_word_id": words[cursor + selected[-1]]["id"], "mode": "emphasis",
                "color": "warm off-white with a subtle warm accent",
                "animation": "small emphasis only; no bouncing text",
                "location": "lower safe area, clear of app controls and people",
            })
        cursor += count
    assert cursor == closing_index + delta
    script["words"] = words
    script["boundaries"]["end"]["character_offset"] = len(script["narration"])
    script["beats"] = sorted(beats, key=lambda beat: beat["start_seconds"])
    result["visual_tracks"] = {lane: sorted(blocks, key=lambda b: b["start_seconds"]) for lane, blocks in tracks.items()}
    result["storyboard_shots"] = sorted(shots, key=lambda shot: shot["start_seconds"])
    new_positions = {word["id"]: index for index, word in enumerate(words)}
    result["subtitle_directives"] = sorted(directives, key=lambda item: new_positions[item["start_word_id"]])
    for blocks in result["visual_tracks"].values():
        previous_time, previous_word = -1, -1
        for block in blocks:
            a, b = new_positions[block["start_word_id"]], new_positions[block["end_word_id"]]
            assert previous_time <= block["start_seconds"] < block["end_seconds"] <= 180, block["id"]
            assert previous_word < a <= b, block["id"]
            previous_time, previous_word = block["end_seconds"], b
    return result


def build_seed():
    content = json.loads((DATA / "seed.json").read_text())
    definition = json.loads((DATA / "middle.json").read_text())
    return replace_middle(content, definition)


def write_sources(content):
    (DATA / "seed.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    (DATA / "voiceover.txt").write_text(content["script"]["narration"])
    lines = ["# ReSpace launch-film production directions", "",
             "The current Working opening and closing are preserved. The middle replaces the entire passage from Meet ReSpace through the final sharing/diagram beat. Its twelve narration passages and source directions come from the approved `.lavish/respace-middle.html`; editable production layers are in `middle.json`.", "",
             "The master remains 180 seconds in 16:9. Opening: before 00:24. Middle: 00:24–02:42. Closing: 02:42–03:00. The viewer is a script and production-planning screen, without video playback. Timeline widths follow words; exact layer times remain in the data. Overlay-free beauty hold: 01:57–02:01.", "",
             "## Recording copy", "", content["script"]["narration"],
             "## Shot directions", ""]
    for shot in content["storyboard_shots"]:
        lines += [f"### {shot['id']} · {timecode(shot['start_seconds'])}–{timecode(shot['end_seconds'])}", "",
                  shot["voiceover"] or "No additional narration.", "", shot["picture"], "", shot["sound"], ""]
    lines += ["## Independent production layers", ""]
    for lane, blocks in content["visual_tracks"].items():
        lines += [f"### {lane}", ""]
        for block in blocks:
            lines += [f"- **{block['id']} · {timecode(block['start_seconds'])}–{timecode(block['end_seconds'])}:** {block['visual_description']}",
                      "", block["recording_requirement"]["exact_action"], ""]
    (DATA / "storyboard.md").write_text("\n".join(lines))


if __name__ == "__main__":
    content = build_seed()
    write_sources(content)
    print(f"Seeded {len(content['script']['words'])} words, 12 replacement middle beats; preserved opening and closing.")
