"""Build the contained ReSpace film package for the copied DS_HQ Script screen."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vlog_format.production_validation import tokenize_narration


DATA = Path(__file__).parent / "data"
VERSION = "respace-original"


def timecode(seconds: float) -> str:
    whole = int(seconds)
    fraction = f"{seconds % 1:.1f}"[1:] if seconds % 1 else ""
    return f"{whole // 60:02d}:{whole % 60:02d}{fraction}"


def build_seed() -> dict:
    narration = (DATA / "voiceover.txt").read_text()
    storyboard = (DATA / "storyboard.md").read_text()
    words = tokenize_narration(narration, version_id=VERSION)
    assert len(words) == 262, "Keep the recording copy and storyboard in sync."
    shots = []
    section = ""
    for line in storyboard.splitlines():
        if line.startswith("### "):
            section = line.removeprefix("### ")
        match = re.match(
            r"\| \*\*(\d+) · (\d+):(\d+)–(\d+):(\d+)\*\* \| (.*?) \| (.*?) \| (.*?) \|$",
            line,
        )
        if not match:
            continue
        number, sm, ss, em, es, picture, voiceover, sound = match.groups()
        shots.append({
            "id": f"shot-{number}",
            "number": int(number),
            "start_seconds": int(sm) * 60 + int(ss),
            "end_seconds": int(em) * 60 + int(es),
            "section": section,
            "picture": picture,
            "voiceover": "" if voiceover == "—" else voiceover.strip("“”"),
            "sound": sound,
        })
    assert [shot["number"] for shot in shots] == list(range(1, 48))
    assert shots[0]["start_seconds"] == 0 and shots[-1]["end_seconds"] == 180
    assert all(a["end_seconds"] == b["start_seconds"] for a, b in zip(shots, shots[1:]))
    assert sum(s["end_seconds"] - s["start_seconds"] for s in shots[41:43]) == 14

    # DS_HQ lays out the visual tracks against spoken words. Silent performance
    # and pitch shots remain timed instructions in the preceding spoken block.
    groups = []
    cursor = 0
    shot_ranges = {}
    for shot in shots:
        if not shot["voiceover"]:
            groups[-1]["shots"].append(shot)
            shot_ranges[shot["number"]] = groups[-1]["range"]
            continue
        tokens = tokenize_narration(shot["voiceover"], version_id=VERSION)
        end = cursor + len(tokens)
        assert [w["text"] for w in words[cursor:end]] == [w["text"] for w in tokens], shot
        anchors = {"start_word_id": words[cursor]["id"], "end_word_id": words[end - 1]["id"]}
        groups.append({"shots": [shot], "range": anchors})
        shot_ranges[shot["number"]] = anchors
        cursor = end
    assert cursor == len(words)

    beats = []
    for group in groups:
        first, last = group["shots"][0], group["shots"][-1]
        opening = first["number"] <= 10
        beats.append({
            "id": f"beat-{first['number']:02d}", **group["range"],
            "start_seconds": first["start_seconds"], "end_seconds": last["end_seconds"],
            "speaker": "External narrator" if opening else "ReSpace team",
            "delivery": "Dramatic external voiceover." if opening else "To camera, continuing over demos and cutaways.",
            "story_purpose": first["section"], "evidence_ids": [],
            "audio": " ".join(s["sound"] for s in group["shots"]),
        })

    base_takes = [
        (1, 1, "Wide shot of the bare dorm from the doorway.", "The student stands at the threshold with a bag. The bed, desk and window fill the frame."),
        (2, 2, "Close-up of the standard bed.", "Plain bedding fills a static, level frame."),
        (3, 3, "Close-up of the standard desk.", "Match the bed shot's horizontal framing."),
        (4, 4, "Close-up of the blank wall.", "Hold on the empty wall before the student enters."),
        (5, 5, "The student puts an open notebook on the desk.", "An unfinished assignment and a small doodle are visible."),
        (6, 6, "Close-up of his pencil correcting an unfinished line.", "His hand pauses beside the unfinished assignment."),
        (7, 7, "A photograph of two friends and a deck of cards come out of his bag.", "Place both beside the notebook."),
        (8, 8, "The student tries the photograph against the wall.", "He studies its position, then lowers it."),
        (9, 9, "He tucks the photograph into his notebook.", "The desk and wall remain mostly bare."),
        (10, 10, "The student looks around the room, then down at his phone.", "Match the doorway edge to the phone, then cut to the presenter."),
        (11, 15, "Presenter speaks to camera from the left side of the dorm.", "Scan, budget and goal panels appear on the right during one continuous take."),
        (16, 17, "Full-screen app demo shows a generated question and selected answer.", "The user answers a practical question, then chooses a material or color."),
        (18, 18, "Presenter speaks beside a crop of the chosen answer.", "The answer expands into the room reveal."),
        (19, 20, "Full-screen room proposal reveals the lamp and chosen materials.", "Move toward the lamp, keeping the existing desk and bed visible."),
        (21, 21, "The room proposal shrinks to the right, revealing the presenter.", "The lamp is selected; its product card expands to fill the screen."),
        (22, 22, "Full-screen product card shows the lamp's size, price and store link.", "Hold the card so all three details can be read."),
        (23, 26, "Presenter introduces café and office design from the same dorm.", "Café and office designs appear beside them, then clear before the final thought."),
        (27, 27, "Full-screen macro of a flower blooming in warm window light.", "Petals unfold against a dark, blurred background, then match-cut to the notebook opening."),
        (28, 30, "The student opens his notebook and finishes the assignment.", "Widen from the opening notebook to the desk, then return to the pencil finishing the line and the page turning."),
        (31, 35, "The student and two friends play cards on the bed.", "A friend starts to leave. The student deals another hand; the friend sits back down. Hold their laughter, then the room wide."),
        (36, 37, "Presenter gestures to the notebook taking up desk space.", "An edit panel appears beside them as they request a smaller lamp."),
        (38, 38, "Full-screen updated design shows a smaller lamp and more desk space.", "Keep the previous viewpoint so the extra notebook space is obvious."),
        (39, 43, "Presenter introduces community designs, followed by the photograph and room diagram.", "Community and post previews appear beside the presenter. Cut to the notebook photo, then a plain room diagram beneath the reserved pitch graphics."),
        (44, 45, "The student props the photo beside his phone in the bare room.", "Begin with the opening doorway view, then move closer to the photo and saved room proposal."),
        (46, 46, "Presenter looks into the camera and says ‘ReSpace.’", "A line from the doorway begins forming the end card."),
        (47, 47, "Warm, plain background behind the ReSpace end card.", "The wordmark, tagline and waitlist invitation sit in the center."),
    ]
    base = []
    for first, last, description, action in base_takes:
        a, b = shots[first - 1], shots[last - 1]
        base.append({
            "id": f"base-{first:02d}",
            "start_word_id": shot_ranges[first]["start_word_id"],
            "end_word_id": shot_ranges[last]["end_word_id"],
            "start_seconds": a["start_seconds"], "end_seconds": b["end_seconds"],
            "shot_ids": [s["id"] for s in shots[first - 1:last]],
            "visual_description": description,
            "visual_type": "general-asset" if first == 47 else "recording",
            "contributors": [], "framing": "16:9 landscape.",
            "recording_requirement": {
                "id": f"capture-{first:02d}",
                "timing_trigger": f"{timecode(a['start_seconds'])}–{timecode(b['end_seconds'])}",
                "exact_action": action,
                "natural_audio": " ".join(s["sound"] for s in shots[first - 1:last]),
            },
        })

    positions = {word["id"]: i for i, word in enumerate(words)}

    def layer(identifier, start, end, first, last, description, action, *, start_word=0, end_word=None, visual_type="recording"):
        left = positions[shot_ranges[first]["start_word_id"]] + start_word
        right = (positions[shot_ranges[last]["end_word_id"]] if end_word is None
                 else positions[shot_ranges[last]["start_word_id"]] + end_word)
        return {
            "id": identifier, "start_word_id": words[left]["id"], "end_word_id": words[right]["id"],
            "start_seconds": start, "end_seconds": end,
            "visual_description": description,
            "visual_type": visual_type, "contributors": [], "framing": "16:9 landscape.",
            "recording_requirement": {
                "id": f"asset-{identifier}",
                "timing_trigger": f"{timecode(start)}–{timecode(end)}",
                "exact_action": action,
            },
        }

    overlay_1 = [
        layer("opening-key", 1, 3.5, 1, 1, "Close-up of the room key appears over the doorway wide.",
              "A small inset on the right shows the plain key and room tag, then dissolves back into the bare room.", start_word=2, visual_type="personal-asset"),
        layer("opening-notebook", 8, 12, 5, 6, "An enlarged notebook fragment reveals the unfinished assignment.",
              "The handwriting appears beside the student, then blends into the pencil close-up.", start_word=2, end_word=1, visual_type="personal-asset"),
        layer("opening-friends", 14, 18, 7, 8, "The friends' photograph enlarges beside the student.",
              "Carry the photo across the cut as he tries it against the wall, then fade it away.", start_word=2, end_word=2, visual_type="personal-asset"),
        layer("demo-scan", 26.5, 32.5, 11, 12, "Room scan and Keep selections appear beside the presenter.",
              "The panel opens on the right, shows the scan and measured room, then changes to the budget screen.", start_word=1),
        layer("demo-budget", 32.5, 37.5, 13, 13, "Budget input appears in the same right-side panel.",
              "Hold the selected amount, then fade the panel away."),
        layer("demo-goal", 38, 45, 14, 15, "A goal about studying and hosting friends is typed beside the presenter.",
              "Hold the completed goal, then expand the panel into the full-screen question.", start_word=2),
        layer("demo-answer", 55, 58, 18, 18, "The selected color or material appears beside the presenter.",
              "Expand the answer crop into the matching material in the room proposal.", start_word=1),
        layer("demo-before-room", 64.5, 67.5, 20, 20, "A small ‘Before’ view of the bare room appears over the proposal.",
              "Place it in the upper left, clear of the proposed lamp, then dissolve it away.", start_word=1, end_word=7),
        layer("demo-proposal", 69, 73, 21, 21, "The full-screen room shrinks beside the presenter.",
              "Keep the room facing the same way. Selecting the lamp expands its product card to full screen."),
        layer("vision-cafe", 83.5, 89.5, 24, 24, "A warm café design appears beside the presenter.",
              "Small tables, warm light and soft seating create places to sit together.", visual_type="recording"),
        layer("vision-office", 89.5, 96, 25, 26, "An office design replaces the café panel.",
              "Show clear work surfaces and a quiet place to focus, then let the panel recede and disappear.", end_word=3, visual_type="recording"),
        layer("future-study", 104, 112, 28, 29, "Proposed furnishings appear around the student at his desk.",
              "Match the lamp, art and storage to the room design. The student, notebook, desk and chair remain real.", start_word=2, visual_type="generative"),
        layer("future-friends", 112, 126, 31, 34, "Proposed furnishings surround the friends playing cards.",
              "The additions follow the wide shot and cropped reactions while the people, bed, chair and cards remain real.", visual_type="generative"),
        layer("demo-edit", 128, 133, 36, 37, "A request for a smaller wooden lamp is typed beside the presenter.",
              "Hold the request, show processing, then expand into the updated room.", start_word=3),
        layer("demo-before-lamp", 134, 136.5, 38, 38, "A small ‘Before’ inset shows the previous lamp.",
              "Match the updated desk's viewpoint and keep the newly clear notebook space visible.", start_word=1),
        layer("demo-community", 138, 144, 39, 40, "Community room designs scroll beside the presenter.",
              "Select one proposed room, then change the panel to the student's own post preview.", start_word=1, end_word=2),
        layer("demo-share-and-reservations", 144, 162, 40, 40, "The post preview expands into the reserved pitch graphics.",
              "The room tile becomes Measure / Plan / Check, then a lamp-to-retailer affiliate diagram labeled ‘Intended model.’", start_word=3, visual_type="general-asset"),
        layer("endcard-type", 174.5, 180, 47, 47, "ReSpace, ‘Make room for you’ and ‘Join the waitlist’ appear centrally.",
              "The doorway line becomes the wordmark. The tagline and invitation settle beneath it.", visual_type="general-asset"),
    ]
    overlay_2 = [
        layer("opening-edges", 4, 7, 2, 4, "A thin line follows the bed, desk and blank-wall cuts.",
              "Match the line's position across all three shots, then let it disappear.", visual_type="general-asset"),
        layer("opening-pencil", 10.5, 12.5, 6, 6, "A pencil-like underline picks out the unfinished assignment.",
              "Trace one short line under the handwriting, then fade it before the photograph appears.", visual_type="general-asset"),
        layer("opening-doorway", 21.5, 24, 10, 10, "A fine doorway outline narrows toward the phone's edge.",
              "The line guides the cut from the student's room to the presenter in the same dorm.", start_word=1, visual_type="general-asset"),
        layer("focus-brand", 24.5, 26.5, 11, 11, "A small ReSpace wordmark appears beside the presenter.",
              "Fade it away as the scan panel enters.", start_word=1, visual_type="general-asset"),
        layer("focus-keep", 29.5, 31.5, 12, 12, "An outline highlights the selected Keep controls.",
              "Follow each selection inside the demo panel, then clear the outline.", start_word=3, visual_type="general-asset"),
        layer("focus-budget", 34.5, 36.5, 13, 13, "A short underline highlights the selected budget.",
              "Appear after the amount settles and fade before the panel closes.", start_word=3, visual_type="general-asset"),
        layer("focus-goal", 41.5, 44.5, 15, 15, "The study and friends phrases are highlighted in the goal.",
              "Clear the emphasis as the panel expands.", start_word=1, visual_type="general-asset"),
        layer("focus-question", 47.5, 49.5, 16, 16, "A soft outline highlights the question and chosen answer.",
              "Leave all text readable and clear the outline before the next question.", start_word=3, visual_type="general-asset"),
        layer("focus-material", 51, 53, 17, 17, "A small ring highlights the chosen color or material.",
              "The ring fades while the selected answer remains visible.", start_word=1, visual_type="general-asset"),
        layer("label-proposal", 58, 73, 19, 21, "A small ‘Proposed design’ label sits inside the room view.",
              "Keep it attached to the capture as the room shrinks beside the presenter.", visual_type="general-asset"),
        layer("focus-product", 74, 78.5, 22, 22, "Size, price and store link are highlighted one at a time.",
              "Finish on the complete, unobstructed product card.", start_word=2, visual_type="general-asset"),
        layer("label-commercial-vision", 83.5, 96, 24, 26, "‘Café · Connection’ changes to ‘Office · Focus’ above the designs.",
              "Change the label with the panel, then remove it as the office recedes.", end_word=3, visual_type="general-asset"),
        layer("label-imagined", 104, 126, 28, 34, "‘Imagined future’ stays in the upper corner of the acted scenes.",
              "Keep it clear of faces and remove it when the real room returns.", visual_type="general-asset"),
        layer("focus-request", 130, 132, 37, 37, "The smaller-lamp phrase is highlighted in the typed request.",
              "Clear the highlight before the updated room appears.", start_word=2, visual_type="general-asset"),
        layer("focus-desktop", 133.5, 136.5, 38, 38, "A faint outline shows the newly available desk space.",
              "Keep the comparison inset visible; fade both to leave the result unobstructed.", start_word=1, visual_type="general-asset"),
        layer("focus-community", 139, 145, 39, 40, "A border follows the selected community tile into the post preview.",
              "Carry it across the panel change, then fade it away.", start_word=4, end_word=4, visual_type="general-asset"),
        layer("endcard-line", 170.5, 175, 46, 47, "A doorway line leads from the presenter into the ReSpace wordmark.",
              "Carry the line onto the plain background, resolve it into the wordmark, then disappear.", end_word=1, visual_type="general-asset"),
    ]

    # Caption directives are exceptions to ordinary full captions, never extra VO.
    subtitle_phrases = ["anyone", "yours", "taste profile", "real products", "One more page", "One more game", "smaller lamp", "Join the waitlist"]
    directives = []
    search_start = 0
    for number, phrase in enumerate(subtitle_phrases, 1):
        start = narration.index(phrase, search_start)
        end = start + len(phrase)
        selected = [w for w in words if start <= w["start_char"] and w["end_char"] <= end]
        assert 1 <= len(selected) <= 3
        directives.append({
            "id": f"subtitle-{number:02d}",
            "start_word_id": selected[0]["id"], "end_word_id": selected[-1]["id"],
            "mode": "emphasis", "color": "warm off-white with a subtle warm accent",
            "animation": "small emphasis only; no bouncing text",
            "location": "lower safe area, clear of app controls and people",
        })
        search_start = end

    content = {
        "schema_version": 2, "package_id": "respace-launch", "version_id": VERSION,
        "run_id": 1, "thesis_id": "respace-approved-story",
        "format_style_profile_version_id": "respace-landscape",
        "title_style_profile_version_id": "respace-approved-title",
        "target": {"resolution": {"width": 1920, "height": 1080}, "aspect_ratio": "16:9"},
        "script": {
            "titles": ["ReSpace — Make room for you"], "narration": narration,
            "estimated_duration_seconds": 180,
            "boundaries": {"start": {"id": "script-start", "character_offset": 0}, "end": {"id": "script-end", "character_offset": len(narration)}},
            "words": words, "beats": beats,
        },
        "visual_tracks": {"base": base, "overlay_1": overlay_1, "overlay_2": overlay_2},
        "subtitle_directives": directives,
        "storyboard_shots": shots,
        "timeline_note": "Base: footage and full-screen demos. Overlay: story inserts, app panels and room additions. Top overlay: labels and emphasis. Expand Details for the shot action.",
    }
    retained = [shot_id for block in base for shot_id in block["shot_ids"]]
    assert retained == [shot["id"] for shot in shots]
    positions = {word["id"]: i for i, word in enumerate(words)}
    for lane in content["visual_tracks"].values():
        previous = -1
        for block in lane:
            start, end = positions[block["start_word_id"]], positions[block["end_word_id"]]
            assert previous < start <= end
            previous = end
    return content


if __name__ == "__main__":
    content = build_seed()
    (DATA / "seed.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    print(f"Seeded {len(content['script']['words'])} words, {len(content['storyboard_shots'])} shots, 180 seconds; {len(content['visual_tracks']['base'])} Base blocks.")
