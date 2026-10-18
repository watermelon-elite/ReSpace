from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol


def anchored_text(content: dict[str, Any], anchored: dict[str, Any]) -> str:
    words = content["script"]["words"]
    positions = {word["id"]: index for index, word in enumerate(words)}
    start = words[positions[anchored["start_word_id"]]]["start_char"]
    end = words[positions[anchored["end_word_id"]]]["end_char"]
    return content["script"]["narration"][start:end]


def narrative_beat_views(content: dict[str, Any]) -> list[dict[str, Any]]:
    script = content["script"]
    words = script["words"]
    positions = {word["id"]: index for index, word in enumerate(words)}
    beats = script["beats"]
    return [
        {
            **beat,
            "start_char": (
                0
                if index == 0
                else words[positions[beat["start_word_id"]]]["start_char"]
            ),
            "end_char": (
                words[positions[beats[index + 1]["start_word_id"]]]["start_char"]
                if index + 1 < len(beats)
                else len(script["narration"])
            ),
            "narration_text": script["narration"][
                0
                if index == 0
                else words[positions[beat["start_word_id"]]]["start_char"] : (
                    words[positions[beats[index + 1]["start_word_id"]]]["start_char"]
                    if index + 1 < len(beats)
                    else len(script["narration"])
                )
            ],
        }
        for index, beat in enumerate(beats)
    ]


class ScriptsPageRepository(Protocol):
    def read_production_packages(self, run_id: int) -> list[dict[str, Any]]: ...

    def read_feedback(self, package_id: str) -> list[dict[str, Any]]: ...


def _narration_span_fragments(
    content: dict[str, Any], comment: dict[str, Any]
) -> list[dict[str, Any]]:
    start = comment["range_start"]
    end = comment["range_end"]
    narration = content["script"]["narration"]
    if (
        start is None
        or end is None
        or not 0 <= start < end <= len(narration)
        or narration[start:end] != comment["anchored_text"]
    ):
        return []

    fragments = []
    for beat in narrative_beat_views(content):
        fragment_start = max(start, beat["start_char"])
        fragment_end = min(end, beat["end_char"])
        if fragment_start >= fragment_end:
            continue
        local_start = fragment_start - beat["start_char"]
        local_end = fragment_end - beat["start_char"]
        fragments.append(
            {
                **comment,
                "target_type": "narration",
                "target_id": f'{beat["id"]}:narration:text',
                "range_start": local_start,
                "range_end": local_end,
                "anchored_text": beat["narration_text"][local_start:local_end],
            }
        )
    return fragments


def _annotated_word_narration(
    text: str,
    comments: list[dict[str, Any]],
    words: list[dict[str, Any]],
    *,
    text_start_char: int,
) -> list[dict[str, Any]]:
    local_words = [
        {
            "index": word["index"],
            "start": word["start_char"] - text_start_char,
            "end": word["end_char"] - text_start_char,
        }
        for word in words
        if text_start_char <= word["start_char"] < text_start_char + len(text)
    ]
    valid_comments = [
        comment
        for comment in comments
        if comment["range_start"] is not None
        and comment["range_end"] is not None
        and 0 <= comment["range_start"] < comment["range_end"] <= len(text)
        and text[comment["range_start"] : comment["range_end"]]
        == comment["anchored_text"]
    ]
    boundaries = {
        0,
        len(text),
        *(bound for word in local_words for bound in (word["start"], word["end"])),
        *(
            bound
            for comment in valid_comments
            for bound in (comment["range_start"], comment["range_end"])
        ),
    }
    ordered = sorted(bound for bound in boundaries if 0 <= bound <= len(text))
    return [
        {
            "text": text[start:end],
            "word_index": next(
                (
                    word["index"]
                    for word in local_words
                    if word["start"] <= start and end <= word["end"]
                ),
                None,
            ),
            "comment_ids": [
                comment["id"]
                for comment in valid_comments
                if comment["range_start"] <= start and comment["range_end"] >= end
            ],
        }
        for start, end in zip(ordered, ordered[1:])
        if start < end
    ]


def scripts_page_context(
    repository: ScriptsPageRepository,
    run_id: int,
    *,
    selected_package_id: str | None = None,
    selected_version_id: str | None = None,
) -> dict[str, Any]:
    """Build the shared production-package Scripts page for any Format."""
    packages = repository.read_production_packages(run_id)
    if not packages:
        return {"packages": [], "selected_package": None}

    for package in packages:
        active_content = package["active_version"]["content"]
        title = active_content["script"]["titles"][0]
        words = title.split()
        package["title"] = title
        package["selector_title"] = " ".join(words[:6]) + (
            "…" if len(words) > 6 else ""
        )

    selected_package = next(
        (
            package
            for package in packages
            if package["id"] == selected_package_id
        ),
        packages[0],
    )
    display_version = selected_package["active_version"]
    if selected_version_id:
        display_version = next(
            (
                version
                for version in selected_package["versions"]
                if version["id"] == selected_version_id
            ),
            display_version,
        )
    display_version = {**display_version, "content": deepcopy(display_version["content"])}
    selected_package["display_version"] = display_version
    display_titles = display_version["content"]["script"]["titles"]
    selected_package["title_options"] = display_titles
    selected_package["display_title"] = display_titles[0]
    selected_package["generated_base_version_id"] = (
        display_version["id"]
        if display_version["kind"] == "generated"
        else display_version["parent_version_id"]
    )

    commentary = [
        item
        for item in repository.read_feedback(selected_package["id"])
        if item["is_commentary"]
    ]
    element_comments: dict[str, list[dict[str, Any]]] = {}
    for item in commentary:
        if (
            item["target_type"]
            in {"visual-block", "subtitle-directive", "recording-requirement"}
            and item["target_state"] == "valid"
        ):
            element_comments.setdefault(item["target_id"], []).append(item)

    content = display_version["content"]
    beat_views = narrative_beat_views(content)
    narration_comments_by_beat: dict[str, list[dict[str, Any]]] = {}
    narration_comments_by_id: dict[str, dict[str, Any]] = {}
    for item in commentary:
        view_comments = []
        rail_comment = item
        if item["target_type"] == "narration" and item["range_start"] is not None:
            view_comments = [item]
        elif item["target_type"] == "narration-span":
            view_comments = _narration_span_fragments(content, item)
        elif item["target_type"] == "beat":
            beat = next(
                (beat for beat in beat_views if beat["id"] == item["target_id"]),
                None,
            )
            if beat:
                rail_comment = {
                    **item,
                    "target_type": "narration",
                    "target_id": f'{beat["id"]}:narration:text',
                    "range_start": 0,
                    "range_end": len(beat["narration_text"]),
                    "anchored_text": beat["narration_text"],
                }
                view_comments = [rail_comment]
        for comment in view_comments:
            beat_id = comment["target_id"].removesuffix(":narration:text")
            narration_comments_by_beat.setdefault(beat_id, []).append(comment)
        if view_comments:
            narration_comments_by_id[item["id"]] = rail_comment

    indexed_words = [
        {**word, "index": index}
        for index, word in enumerate(content["script"]["words"])
    ]
    word_positions = {word["id"]: word["index"] for word in indexed_words}
    for beat in beat_views:
        narration_text = beat["narration_text"]
        beat["narration_comments"] = [
            comment
            for comment in narration_comments_by_beat.get(beat["id"], [])
            if comment["range_start"] is not None
            and comment["range_end"] is not None
            and 0 <= comment["range_start"] < comment["range_end"] <= len(narration_text)
            and narration_text[comment["range_start"] : comment["range_end"]]
            == comment["anchored_text"]
        ]
        beat["annotated_narration"] = _annotated_word_narration(
            narration_text,
            beat["narration_comments"],
            indexed_words,
            text_start_char=beat["start_char"],
        )
    content["display_beats"] = beat_views

    timeline_tracks = []
    for track_name, blocks in content["visual_tracks"].items():
        for block in blocks:
            block["start_index"] = word_positions[block["start_word_id"]]
            block["end_index"] = word_positions[block["end_word_id"]]
            block["word_span"] = block["end_index"] - block["start_index"] + 1
            block["script_text"] = anchored_text(content, block)
            block["element_comments"] = element_comments.get(block["id"], [])
            recording = block.get("recording_requirement")
            block["recording_comments"] = (
                element_comments.get(recording["id"], []) if recording else []
            )
            block["target_type"] = "visual-block"
        timeline_tracks.append(
            {
                "key": track_name,
                "label": {
                    "base": "Base",
                    "overlay_1": "Overlay",
                    "overlay_2": "Top overlay",
                }[track_name],
                "elements": blocks,
            }
        )

    for directive in content["subtitle_directives"]:
        directive["start_index"] = word_positions[directive["start_word_id"]]
        directive["end_index"] = word_positions[directive["end_word_id"]]
        directive["word_span"] = directive["end_index"] - directive["start_index"] + 1
        directive["script_text"] = anchored_text(content, directive)
        directive["visual_type"] = f"subtitle-{directive['mode']}"
        directive["visual_description"] = (
            f"Hide subtitles over “{directive['script_text']}”"
            if directive["mode"] == "hidden"
            else f"Emphasize “{directive['script_text']}”"
        )
        directive["element_comments"] = element_comments.get(directive["id"], [])
        directive["target_type"] = "subtitle-directive"
    timeline_tracks.append(
        {
            "key": "subtitles",
            "label": "Subtitles",
            "elements": content["subtitle_directives"],
        }
    )
    content["timeline_tracks"] = timeline_tracks
    content["timeline_script_sections"] = [
        {
            "id": block["id"],
            "start_index": block["start_index"],
            "word_span": block["word_span"],
            "words": indexed_words[block["start_index"] : block["end_index"] + 1],
        }
        for block in content["visual_tracks"]["base"]
    ]
    content["word_count"] = len(indexed_words)
    from vlog_format.script_export import build_script_export

    content["copy_export"] = build_script_export(
        title=selected_package["display_title"],
        version_id=display_version["id"],
        content=content,
    )

    valid_comment_ids = {
        comment["id"]
        for beat in beat_views
        for comment in beat["narration_comments"]
    }
    selected_package["narration_comments"] = sorted(
        (
            comment
            for comment_id, comment in narration_comments_by_id.items()
            if comment_id in valid_comment_ids
        ),
        key=lambda comment: comment["created_at"],
    )
    selected_package["commentary_events"] = sorted(
        [
            {
                "kind": "comment",
                "created_at": item["created_at"],
                "comment": item,
            }
            for item in commentary
            if item["target_type"] == "package"
        ]
        + [
            {
                "kind": "regeneration",
                "created_at": version["created_at"],
                "version": version,
            }
            for version in selected_package["versions"]
            if version["source"] == "regenerate"
        ],
        key=lambda event: (
            event["created_at"],
            1 if event["kind"] == "regeneration" else 0,
        ),
    )
    return {"packages": packages, "selected_package": selected_package}
