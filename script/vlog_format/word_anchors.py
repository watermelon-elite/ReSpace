"""Shared projections from schema-v2 word anchors into authoritative narration."""

from __future__ import annotations

from typing import Any


def anchored_character_range(
    content: dict[str, Any], anchored: dict[str, Any]
) -> tuple[int, int]:
    words = content["script"]["words"]
    positions = {word["id"]: index for index, word in enumerate(words)}
    start = words[positions[anchored["start_word_id"]]]["start_char"]
    end = words[positions[anchored["end_word_id"]]]["end_char"]
    return start, end


def anchored_text(content: dict[str, Any], anchored: dict[str, Any]) -> str:
    start, end = anchored_character_range(content, anchored)
    return content["script"]["narration"][start:end]


def narrative_beat_views(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Partition every narration character using the ordered beat word anchors."""
    script = content["script"]
    words = script["words"]
    positions = {word["id"]: index for index, word in enumerate(words)}
    beats = script["beats"]
    views = []
    for index, beat in enumerate(beats):
        start_char = (
            0
            if index == 0
            else words[positions[beat["start_word_id"]]]["start_char"]
        )
        end_char = (
            words[positions[beats[index + 1]["start_word_id"]]]["start_char"]
            if index + 1 < len(beats)
            else len(script["narration"])
        )
        views.append(
            {
                **beat,
                "start_char": start_char,
                "end_char": end_char,
                "narration_text": script["narration"][start_char:end_char],
            }
        )
    return views
