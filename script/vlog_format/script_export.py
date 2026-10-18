"""Google Docs-friendly styled exports for production-package scripts."""

from __future__ import annotations

from typing import Any

from .word_anchors import anchored_text, narrative_beat_views


BLACK = "#000000"
OVERLAY_COLORS = ("#1f4e79", "#006100", "#7030a0", "#9c005d")
SUBTITLE_BRACKETS = (("[", "]"), ("(", ")"), ("{", "}"))
EXPORT_LEGEND = (
    (
        "Base visual — ",
        "The narration switches between regular and bold whenever the base visual "
        "changes. BASE 1 is regular, BASE 2 is bold, and the pattern then repeats.",
    ),
    (
        "Overlay — ",
        "Text color marks the active overlay: dark blue, dark green, dark purple, "
        "then dark pink. The sequence repeats after pink; black means no overlay.",
    ),
    (
        "Top overlay — ",
        "Underlined narration means a top overlay is active. No underline means none "
        "is active. If two top overlays are adjacent, the space between them is "
        "intentionally left un-underlined to mark the change.",
    ),
    (
        "Special subtitle — ",
        "Brackets mark special subtitle directions. They cycle in this order: "
        "[ ], ( ), { }, then repeat.",
    ),
)


def _indexed_range(
    anchored: dict[str, Any], positions: dict[str, int]
) -> tuple[int, int]:
    return positions[anchored["start_word_id"]], positions[anchored["end_word_id"]]


def _intersects(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] <= second[1] and second[0] <= first[1]


def _timecode(seconds: float) -> str:
    minutes, remaining = divmod(int(seconds + 0.5), 60)
    return f"{minutes:02d}:{remaining:02d}"


def _word_style(
    content: dict[str, Any], index: int, positions: dict[str, int]
) -> tuple[bool, str, bool]:
    base_number = next(
        (
            number
            for number, block in enumerate(content["visual_tracks"]["base"], start=1)
            if _intersects((index, index), _indexed_range(block, positions))
        ),
        1,
    )
    overlay_number = next(
        (
            number
            for number, block in enumerate(
                content["visual_tracks"]["overlay_1"], start=1
            )
            if _intersects((index, index), _indexed_range(block, positions))
        ),
        None,
    )
    underlined = any(
        _intersects((index, index), _indexed_range(block, positions))
        for block in content["visual_tracks"]["overlay_2"]
    )
    color = (
        OVERLAY_COLORS[(overlay_number - 1) % len(OVERLAY_COLORS)]
        if overlay_number is not None
        else BLACK
    )
    return base_number % 2 == 0, color, underlined


def _styled_narration(
    content: dict[str, Any], beat: dict[str, Any], positions: dict[str, int]
) -> list[dict[str, Any]]:
    words = content["script"]["words"]
    narration = content["script"]["narration"]
    start_index, end_index = _indexed_range(beat, positions)

    directive_starts: dict[int, list[tuple[int, tuple[str, str]]]] = {}
    directive_ends: dict[int, list[tuple[int, tuple[str, str]]]] = {}
    for number, directive in enumerate(content["subtitle_directives"]):
        start, end = _indexed_range(directive, positions)
        bracket = SUBTITLE_BRACKETS[number % len(SUBTITLE_BRACKETS)]
        directive_starts.setdefault(start, []).append((number, bracket))
        directive_ends.setdefault(end, []).append((number, bracket))

    top_overlay_ranges = [
        _indexed_range(block, positions)
        for block in content["visual_tracks"]["overlay_2"]
    ]
    top_overlay_break_starts = {
        current[0]
        for previous, current in zip(top_overlay_ranges, top_overlay_ranges[1:])
        if current[0] == previous[1] + 1
    }

    chunks: list[tuple[str, bool, str, bool]] = []
    cursor = beat["start_char"]
    previous_style = _word_style(content, start_index, positions)
    for index in range(start_index, end_index + 1):
        word = words[index]
        style = _word_style(content, index, positions)
        if word["start_char"] > cursor:
            separator_style = previous_style
            if index in top_overlay_break_starts:
                separator_style = previous_style[0], previous_style[1], False
            chunks.append((narration[cursor : word["start_char"]], *separator_style))
        for _, bracket in directive_starts.get(index, []):
            chunks.append((bracket[0], *style))
        chunks.append((narration[word["start_char"] : word["end_char"]], *style))
        for _, bracket in reversed(directive_ends.get(index, [])):
            chunks.append((bracket[1], *style))
        cursor = word["end_char"]
        previous_style = style

    if cursor < beat["end_char"]:
        chunks.append((narration[cursor : beat["end_char"]].rstrip(), *previous_style))

    segments: list[dict[str, Any]] = []
    for text, bold, color, underline in chunks:
        if not text:
            continue
        if segments and (
            segments[-1]["bold"],
            segments[-1]["color"],
            segments[-1]["underline"],
        ) == (bold, color, underline):
            segments[-1]["text"] += text
        else:
            segments.append(
                {
                    "text": text,
                    "bold": bold,
                    "color": color,
                    "underline": underline,
                }
            )
    return segments


def _bullet(
    label: str,
    description: str | None,
    *,
    bold: bool = False,
    color: str = BLACK,
    underline: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "description": description,
        "bold": bold,
        "color": color,
        "underline": underline,
    }


def _plain_text(export: dict[str, Any]) -> str:
    parts = [export["title"], export["metadata"], "", "How to read the styling"]
    parts.extend(f"• {label}{explanation}" for label, explanation in export["legend"])
    for line in export["lines"]:
        parts.extend(
            [
                "",
                line["heading"],
                "".join(segment["text"] for segment in line["segments"]),
            ]
        )
        parts.extend(
            f"• {bullet['label']}"
            + (f" — {bullet['description']}" if bullet["description"] else "")
            for bullet in line["bullets"]
        )
    return "\n".join(parts)


def _visual_description(block: dict[str, Any]) -> str:
    description = block["visual_description"]
    action = (block.get("recording_requirement") or {}).get("exact_action")
    return f"{description} Following action: {action}" if action else description


def build_script_export(
    *, title: str, version_id: str, content: dict[str, Any]
) -> dict[str, Any]:
    """Project one selected package version into a copy-ready styled script."""
    words = content["script"]["words"]
    positions = {word["id"]: index for index, word in enumerate(words)}
    duration = float(content["script"]["estimated_duration_seconds"])
    total_words = len(words)
    beats = narrative_beat_views(content)
    lines = []
    seen_elements: set[str] = set()

    for line_number, beat in enumerate(beats, start=1):
        line_range = _indexed_range(beat, positions)
        has_explicit_time = (
            beat.get("start_seconds") is not None
            and beat.get("end_seconds") is not None
        )
        start_seconds = (
            beat["start_seconds"] if has_explicit_time
            else line_range[0] / total_words * duration
        )
        end_seconds = (
            beat["end_seconds"] if has_explicit_time
            else (line_range[1] + 1) / total_words * duration
        )
        bullets = []

        for number, block in enumerate(content["visual_tracks"]["base"], start=1):
            if not _intersects(line_range, _indexed_range(block, positions)):
                continue
            bullets.append(
                _bullet(
                    f"BASE {number}",
                    None
                    if block["id"] in seen_elements
                    else _visual_description(block),
                    bold=number % 2 == 0,
                )
            )
            seen_elements.add(block["id"])

        for number, block in enumerate(
            content["visual_tracks"]["overlay_1"], start=1
        ):
            if not _intersects(line_range, _indexed_range(block, positions)):
                continue
            bullets.append(
                _bullet(
                    f"OVERLAY {number}",
                    None
                    if block["id"] in seen_elements
                    else _visual_description(block),
                    color=OVERLAY_COLORS[(number - 1) % len(OVERLAY_COLORS)],
                )
            )
            seen_elements.add(block["id"])

        for number, block in enumerate(
            content["visual_tracks"]["overlay_2"], start=1
        ):
            if not _intersects(line_range, _indexed_range(block, positions)):
                continue
            bullets.append(
                _bullet(
                    f"TOP OVERLAY {number}",
                    None
                    if block["id"] in seen_elements
                    else _visual_description(block),
                    underline=True,
                )
            )
            seen_elements.add(block["id"])

        for number, directive in enumerate(content["subtitle_directives"], start=1):
            if not _intersects(line_range, _indexed_range(directive, positions)):
                continue
            bracket = SUBTITLE_BRACKETS[(number - 1) % len(SUBTITLE_BRACKETS)]
            excerpt = anchored_text(content, directive)
            if directive["mode"] == "hidden":
                description = f"Hide subtitles for {bracket[0]}{excerpt}{bracket[1]}"
            else:
                description = (
                    f"Emphasize {bracket[0]}{excerpt}{bracket[1]} — color: "
                    f"{directive.get('color') or 'default'}; animation: "
                    f"{directive.get('animation') or 'default'}; location: "
                    f"{directive.get('location') or 'default'}"
                )
            bullets.append(
                _bullet(
                    f"SPECIAL SUBTITLE {number}",
                    None if directive["id"] in seen_elements else description,
                )
            )
            seen_elements.add(directive["id"])

        lines.append(
            {
                "heading": (
                    f"(Line {line_number}) {'' if has_explicit_time else '~'}{_timecode(start_seconds)}–"
                    f"{_timecode(end_seconds)}"
                ),
                "segments": _styled_narration(content, beat, positions),
                "bullets": bullets,
            }
        )

    export = {
        "title": title,
        "metadata": (
            f"Styled script · {version_id} · approximately {duration:.1f} seconds"
        ),
        "legend": EXPORT_LEGEND,
        "lines": lines,
    }
    export["plain_text"] = _plain_text(export)
    return export
