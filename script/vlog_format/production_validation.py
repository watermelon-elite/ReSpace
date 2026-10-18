"""DS_HQ word tokenization and edit remapping for the local Script prototype."""

from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SPOKEN_WORD = re.compile(
    r"[^\W_]+(?:['’][^\W_]+)*(?:[-‑][^\W_]+(?:['’][^\W_]+)*)*",
    re.UNICODE,
)


def tokenize_narration(narration: str, *, version_id: str) -> list[dict[str, Any]]:
    """Return the version-local spoken-word stream with exact character offsets."""
    if not isinstance(narration, str):
        raise ValueError("script.narration must be a string.")
    if not isinstance(version_id, str) or not _STABLE_ID.fullmatch(version_id):
        raise ValueError("version_id requires a stable identifier.")
    return [
        {
            "id": f"{version_id}-word-{index}",
            "text": match.group(),
            "start_char": match.start(),
            "end_char": match.end(),
        }
        for index, match in enumerate(_SPOKEN_WORD.finditer(narration), start=1)
    ]


def remap_version_word_anchors(package: dict[str, Any]) -> dict[str, Any]:
    """Retokenize edited narration and keep every surviving word-anchored range valid."""
    remapped = deepcopy(package)
    script = remapped.get("script")
    version_id = remapped.get("version_id")
    if not isinstance(script, dict) or not isinstance(version_id, str):
        return remapped
    current_words = script.get("words")
    expected_words = tokenize_narration(script.get("narration"), version_id=version_id)
    if current_words == expected_words:
        return remapped
    if not isinstance(current_words, list) or not current_words or not expected_words:
        return remapped
    if any(
        not isinstance(word, dict)
        or not isinstance(word.get("id"), str)
        or not isinstance(word.get("text"), str)
        for word in current_words
    ):
        return remapped

    old_positions = {word["id"]: index for index, word in enumerate(current_words)}
    owners: list[int | None] = [None] * len(expected_words)
    matcher = SequenceMatcher(
        None,
        [word["text"] for word in current_words],
        [word["text"] for word in expected_words],
        autojunk=False,
    )
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(new_end - new_start):
                owners[new_start + offset] = old_start + offset
            continue
        if tag == "replace" and old_start < old_end:
            old_span = old_end - old_start
            new_span = new_end - new_start
            for offset in range(new_span):
                owners[new_start + offset] = old_start + min(
                    old_span - 1,
                    offset * old_span // max(1, new_span),
                )
            continue
        if tag == "insert":
            owner = old_start - 1 if old_start else 0
            owner = min(owner, len(current_words) - 1)
            for index in range(new_start, new_end):
                owners[index] = owner

    # SequenceMatcher can leave only pathological replacement positions unmapped.
    # Giving them to the preceding word preserves the editor's simple ownership rule.
    for index, owner in enumerate(owners):
        if owner is None:
            owners[index] = owners[index - 1] if index else 0

    script["words"] = expected_words
    boundaries = script.get("boundaries")
    if isinstance(boundaries, dict) and isinstance(boundaries.get("end"), dict):
        boundaries["end"]["character_offset"] = len(script["narration"])

    def remap(items: Any) -> list[Any]:
        if not isinstance(items, list):
            return items
        retained = []
        for item in items:
            if not isinstance(item, dict):
                retained.append(item)
                continue
            old_start = old_positions.get(item.get("start_word_id"))
            old_end = old_positions.get(item.get("end_word_id"))
            if old_start is None or old_end is None:
                retained.append(item)
                continue
            indexes = [
                index
                for index, owner in enumerate(owners)
                if owner is not None and old_start <= owner <= old_end
            ]
            if not indexes:
                continue
            start = indexes[0]
            end = indexes[-1]
            item["start_word_id"] = expected_words[start]["id"]
            item["end_word_id"] = expected_words[end]["id"]
            retained.append(item)
        return retained

    script["beats"] = remap(script.get("beats"))
    tracks = remapped.get("visual_tracks")
    if isinstance(tracks, dict):
        for track_name, blocks in tracks.items():
            tracks[track_name] = remap(blocks)
    directives = remap(remapped.get("subtitle_directives"))
    new_positions = {word["id"]: index for index, word in enumerate(expected_words)}
    for directive in directives:
        if isinstance(directive, dict) and directive.get("mode") == "emphasis":
            position = new_positions[directive["start_word_id"]]
            end_position = min(position + 2, len(expected_words) - 1)
            if new_positions[directive["end_word_id"]] > end_position:
                directive["end_word_id"] = expected_words[end_position]["id"]
    remapped["subtitle_directives"] = directives
    return remapped

