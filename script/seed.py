"""Build the contained ReSpace film package for the copied DS_HQ Script screen."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vlog_format.production_validation import tokenize_narration


DATA = Path(__file__).parent / "data"
VERSION = "respace-original"


def timecode(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def build_seed() -> dict:
    narration = (DATA / "voiceover.txt").read_text()
    storyboard = (DATA / "storyboard.md").read_text()
    words = tokenize_narration(narration, version_id=VERSION)
    assert len(words) == 224, "The approved recording copy must remain intact."
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
    assert [shot["number"] for shot in shots] == list(range(1, 44))
    assert shots[0]["start_seconds"] == 0 and shots[-1]["end_seconds"] == 180
    assert all(a["end_seconds"] == b["start_seconds"] for a, b in zip(shots, shots[1:]))
    assert sum(s["end_seconds"] - s["start_seconds"] for s in shots[36:39]) == 24

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

    labels = {
        1: "The anonymous dorm — locked doorway wide",
        2: "Standard bed — precise one-second detail",
        3: "Standard desk — repeat the framing line",
        4: "Blank wall — complete the three-cut rhythm",
        5: "A particular person enters — open notebook",
        6: "An unfinished assignment — pencil detail",
        7: "The friends and the game — photograph and cards",
        8: "Try the photograph against the wall",
        9: "Tuck the photograph into the notebook",
        10: "Room to phone — the question that introduces ReSpace",
        11: "Meet ReSpace — actual app over his shoulder",
        12: "Scan the room and Keep the bed and desk",
        13: "Set a comfortable budget — hold the actual amount",
        14: "Tell ReSpace how he wants to live here",
        15: "Hold the goal: study space and two friends",
        16: "A generated question clarifies a useful detail",
        17: "Choose a visual preference that appears in the result",
        18: "Answers become a taste profile — honest processing edit",
        19: "First complete proposal — lamp and selected materials",
        20: "A real product joins the furniture he is keeping",
        21: "Explore the photorealistic proposed room",
        22: "Read the lamp card: size, price and merchant",
        23: "Enter the explicitly imagined future",
        24: "Study at the existing desk; finish the opening assignment",
        26: "Page becomes cards; reveal the two friends on the real bed",
        28: "The friend picks up a backpack — another hand is dealt",
        29: "The friend sits again; let the room and laughter breathe",
        31: "Back in the real dorm — the notebook needs more room",
        32: "Ask for a smaller lamp in warm wood",
        33: "Inspect the smaller lamp and clearer desktop",
        34: "Explore other people's proposed rooms",
        35: "Share the proposal; then three reserved eight-second pitch ideas",
        40: "Return to the exact original room with a saved proposal",
        41: "Finally display the photograph beside the proposed room",
        42: "Photograph and proposal together — transition to wordmark",
        43: "ReSpace / Make room for you. / Join the waitlist.",
    }
    reserved = {
        37: (
            "BRAINSTORM ONLY: Make the same room briefly explain itself: Measure / Plan / Check. "
            "Measured structure becomes a proposed arrangement and a visible fit check. Optional small "
            "technical labels: RoomPlan/LiDAR and Perceptron for measurement/perception, Gemini for "
            "relationships, placement solver for geometry checks. Keep the recognizable dorm underneath. "
            "An alternative follows the same lamp's available space, real dimensions and placement. "
            "Use a research-informed caption only when tied to an actual planning rule. No finished VO."
        ),
        38: (
            "BRAINSTORM ONLY: Follow the familiar lamp's purchase link: Generous free tier → Relevant "
            "product links → Affiliate revenue. This is the intended business model, not earned revenue "
            "or signed partnerships. No fictional sales, commission rates or conversions. Purchasing "
            "furniture is not required to explore a design. No finished VO."
        ),
        39: (
            "BRAINSTORM ONLY: Expand the dorm outline into a multi-room home, then a small café. "
            "Label Future direction; give each place one beat and return through a doorway shape to "
            "the actual dorm. No delivery date. No finished VO."
        ),
    }
    base = []
    beats = []
    for group in groups:
        first, last = group["shots"][0], group["shots"][-1]
        number = first["number"]
        start, end = first["start_seconds"], last["end_seconds"]
        shot_label = f"{number:02d}" if first is last else f"{number:02d}–{last['number']:02d}"
        description = f"{timecode(start)}–{timecode(end)} · Shot {shot_label} · {labels[number]}"
        assert len(description) <= 160
        notes = []
        for shot in group["shots"]:
            silence = " VO: silent; leave room for the performance and sound." if not shot["voiceover"] else ""
            notes.append(
                f"SHOT {shot['number']:02d} · {timecode(shot['start_seconds'])}–{timecode(shot['end_seconds'])}. "
                f"PICTURE / ACTION: {shot['picture']} SOUND / EDIT: {shot['sound']}{silence} "
                f"{reserved.get(shot['number'], '')}".strip()
            )
        if number == 1:
            notes.append("CAPTIONS: subtitle all spoken narration by default; the Subtitles lane only marks selective emphasis. Times are proposed edit timings, not scan-speed claims.")
        if number == 23:
            notes.append("COMPOSITING: Keep the physical bed, desk, chair and room architecture. Record locked clean plates with matched focus, exposure and white balance. Actors and all contact surfaces/shadows remain real. Added furnishings must come from the actual design; never buy or physically dress the room for this film. Keep digital rugs away from actors' feet, or omit them.")
        if number == 26:
            notes.append("CAPTURE PLAN: Film shots 27–30 as one continuous locked-wide performance, crop for the first beat, and use a second fixed angle only if needed. Mark an unobstructed standing area for the departing friend. Preserve spontaneous reactions. The friends appear only in this editorial imagined future, never as generated people in the app.")
        if number == 35:
            notes.append("EDIT OPTION: Shots 37–39 reserve 24 seconds; there is no spoken placeholder. Remove them together for the 02:36 story cut. Traction is omitted. The three directions remain brainstorms, not completed technical/business narration.")
        if number == 43:
            notes.append("DELIVERY: Hold the CTA to the end. Waitlist destination and final brand assets are still to be supplied; do not invent a URL. Master is 1920×1080 landscape.")
        timing = {"start_seconds": start, "end_seconds": end}
        base.append({
            "id": f"base-{number:02d}", **group["range"], **timing,
            "shot_ids": [s["id"] for s in group["shots"]],
            "visual_description": description,
            "visual_type": "recording",
            "contributors": [],
            "framing": "16:9 landscape; follow the specific shot directions.",
            "recording_requirement": {
                "id": f"capture-{number:02d}",
                "timing_trigger": f"{timecode(start)}–{timecode(end)}; the written shot times govern silent holds.",
                "capture_surface": "Actual room, actual app capture or finished composite, as specified per shot.",
                "device_orientation": "Landscape 16:9 master, 1920×1080.",
                "framing": "Preserve the established doorway, window, bed and desk geography.",
                "exact_action": "\n\n".join(notes),
                "lead_in_tail": "Record handles before and after the action; edit to the listed shot times.",
                "natural_audio": " ".join(s["sound"] for s in group["shots"]),
                "on_screen_state": "Use one coherent room/design session, consistent products, budget and prices; show processing edits visibly.",
                "privacy_redaction": "Use permitted or staged community content with no fabricated engagement; omit personal account details.",
                "acceptance_criteria": "Retain each shot direction and exact proposed time; imagined people remain separate from the app's room-only proposal.",
            },
        })
        beats.append({
            "id": f"beat-{number:02d}", **group["range"], **timing,
            "speaker": "Narrator",
            "delivery": "Warm, observant and conversational. Let connected phrases flow over cuts; leave the documented silent holds intact.",
            "story_purpose": first["section"],
            "evidence_ids": [],
            "audio": " ".join(s["sound"] for s in group["shots"]),
        })

    def overlay(number: int, start_shot: int, end_shot: int, description: str, *, lane: int = 1) -> dict:
        a, b = shots[start_shot - 1], shots[end_shot - 1]
        return {
            "id": f"overlay-{lane}-{number:02d}",
            "start_word_id": shot_ranges[start_shot]["start_word_id"],
            "end_word_id": shot_ranges[end_shot]["end_word_id"],
            "start_seconds": a["start_seconds"], "end_seconds": b["end_seconds"],
            "visual_description": f"{timecode(a['start_seconds'])}–{timecode(b['end_seconds'])} · {description}",
            "visual_type": "general-asset", "contributors": [],
            "framing": "Keep the room and interface readable; use restrained emphasis within 16:9 safe margins.",
            "recording_requirement": None,
        }

    overlay_1 = [
        overlay(1, 12, 12, "Subtle emphasis on the actual Keep controls for the bed and desk."),
        overlay(2, 16, 17, "Emphasize the actual generated question and chosen answer; do not invent branching or a profile dashboard."),
        overlay(3, 19, 21, "Small ‘Proposed design’ identifier; keep the lamp, materials and room readable."),
        overlay(4, 22, 22, "Emphasize size → actual price → merchant link in spoken order; hold the same real Product card."),
        overlay(5, 23, 30, "Retain ‘Imagined future’ throughout the acted sequence. These people are editorial imagination."),
        overlay(6, 33, 33, "Restrained emphasis on the smaller lamp and newly clear desktop; no unrelated changes."),
        overlay(7, 35, 35, "Post preview: ‘First plan for my dorm.’ Clearly identify it as a proposed design; do not publish."),
        overlay(8, 43, 43, "End-card text: ReSpace / Make room for you. / Join the waitlist. Add a URL only when supplied."),
    ]
    overlay_2 = [
        overlay(1, 10, 11, "Match doorframe to phone edge; retain the same musical theme into the actual app.", lane=2),
        overlay(2, 18, 19, "Visible editorial transition across processing; carry the selected color into the proposal.", lane=2),
        overlay(3, 20, 20, "Precise product-image → placed-lamp match; keep the real desk and bed in the same design.", lane=2),
        overlay(4, 22, 23, "Match the Product-card lamp to the future-room composite; pencil sound arrives before its source.", lane=2),
        overlay(5, 26, 26, "Page-turn → card-deal match cut. Use real page and card sounds to join study and friends.", lane=2),
        overlay(6, 31, 31, "Match the host's glance back to the barren room and the room-only proposal on the phone.", lane=2),
        overlay(7, 36, 39, "SILENT 02:14–02:42: tile → room diagram; Measure / Plan / Check → affiliate branch → Future direction: home, café.", lane=2),
        overlay(8, 42, 43, "A restrained doorway line resolves into the wordmark and final CTA; hold to the end.", lane=2),
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
        "timeline_note": "The DS_HQ timeline is anchored to narration words, not elapsed time. Exact shot times and silent holds are in each Base block's Following action. Full spoken captions are on by default; the Subtitles lane contains selective emphasis only.",
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
