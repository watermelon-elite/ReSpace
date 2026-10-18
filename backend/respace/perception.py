"""Stored-frame detection; an empty observation is never a provider failure."""

import asyncio
import base64
from contextlib import nullcontext
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import os
import time

import httpx
from perceptron.errors import ParseError

from .categories import DETECTION_LABELS


class DetectionFailure(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def _box(label, coords, width, height):
    if label not in DETECTION_LABELS:
        raise ValueError("detector returned an unsupported category")
    if len(coords) != 4 or not all(math.isfinite(float(v)) for v in coords):
        raise ValueError("box must have four finite coordinates")
    x1, y1, x2, y2 = map(float, coords)
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("box falls outside uploaded image bounds")
    return {"category": label, "box_px": [x1, y1, x2, y2]}


def parse_detections(response, width, height, mode="chat"):
    """Dedicated detect uses pixels; chat grounding uses the 0–1000 grid."""
    try:
        if mode == "detect":
            if response["finish_reason"] != "complete":
                raise ValueError("incomplete detector output")
            boxes = []
            for detection in response["detections"]:
                box = detection["point_box"]
                boxes.append(_box(detection["mention"],
                    [box["top_left"]["x"], box["top_left"]["y"],
                     box["bottom_right"]["x"], box["bottom_right"]["y"]], width, height))
            return boxes
        from perceptron import collect_annotations

        choice = response["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("incomplete chat grounding output")
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("grounding content must be text")
        annotations = collect_annotations(content, expects="box", strict=True)
        if annotations.points or annotations.polygons or annotations.clips or annotations.tracks:
            raise ValueError("expected boxes-only detector output")
        boxes = []
        for ann in annotations.boxes:
            if getattr(ann, "asset_idx", None) not in (None, 0):
                raise ValueError("box references an unknown image")
            grid = _box(ann.mention, [ann.top_left.x, ann.top_left.y,
                                    ann.bottom_right.x, ann.bottom_right.y], 1000, 1000)
            x1, y1, x2, y2 = grid["box_px"]
            boxes.append(_box(ann.mention, [x1*width/1000, y1*height/1000,
                                           x2*width/1000, y2*height/1000], width, height))
        return boxes
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, ParseError) as exc:
        raise DetectionFailure("parse_error", "Detector output could not be validated.") from exc


class PerceptronAdapter:
    def __init__(self, api_key=None, *, client=None, model=None, mode=None, sleep=asyncio.sleep):
        self.api_key = api_key or os.getenv("PERCEPTRON_API_KEY")
        self.client = client
        self.model = model or os.getenv("PERCEPTRON_MODEL", "perceptron-mk1.5")
        self.mode = mode or os.getenv("PERCEPTRON_MODE", "chat")
        if self.mode not in ("chat", "detect"):
            raise ValueError("PERCEPTRON_MODE must be chat or detect")
        if self.model not in ("perceptron-mk1.5", "perceptron-mk1"):
            raise ValueError("Unsupported configured Perceptron model")
        self.sleep = sleep

    async def detect(self, jpeg, width, height, frame_id):
        if not isinstance(width, int) or not isinstance(height, int) or min(width, height) <= 0:
            raise ValueError("positive uploaded JPEG dimensions are required")
        outcome = {"schema_version": 1, "frame_id": frame_id, "state": "failed", "attempts": [],
                   "usage": {}, "detections": None, "failure": None,
                   "provider": "perceptron", "model": self.model if self.mode == "chat" else None,
                   "mode": self.mode}
        if not self.api_key:
            outcome["failure"] = {"code": "credentials_missing", "message": "Detection provider is not configured.", "retryable": True}
            return outcome
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        if self.mode == "chat":
            path, body = "chat/completions", {
                "model": self.model, "vision_config": {"annotation_format": "box"},
                "max_completion_tokens": 2048,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "Locate only these categories using exact labels: " +
                     ", ".join(DETECTION_LABELS) + ". Return boxes only; if none are visible return no annotations."}]}]}
        else:
            path, body = "detect", {"media": {"type": "image", "image_url": data_url},
                                   "categories": list(DETECTION_LABELS), "config": {"output": "box"}}
        async with httpx.AsyncClient() if self.client is None else nullcontext(self.client) as client:
            for attempt in range(2):
                started = time.monotonic()
                record = {"attempt": attempt + 1, "outcome": "failed"}
                retry_after = None
                try:
                    response = await asyncio.wait_for(client.post(
                        f"https://api.perceptron.inc/v1/{path}", json=body,
                        headers={"Authorization": f"Bearer {self.api_key}"}, timeout=20), timeout=20)
                    record["http_status"] = response.status_code
                    if response.status_code == 429:
                        if attempt == 0:
                            retry_after = _retry_after(response.headers.get("Retry-After"))
                        raise DetectionFailure("rate_limit", "Detection provider is rate limited.", True)
                    if response.is_error:
                        raise DetectionFailure("provider_error", "Detection provider rejected or failed the request.", response.status_code >= 500)
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise DetectionFailure("parse_error", "Detection provider did not return JSON.") from exc
                    outcome["usage"] = payload.get("usage", {})
                    detections = parse_detections(payload, width, height, self.mode)
                    outcome.update(state="succeeded", detections=detections, failure=None)
                    record["outcome"] = "succeeded"
                except (asyncio.TimeoutError, httpx.TimeoutException):
                    outcome["failure"] = {"code": "timeout", "message": "Detection attempt timed out.", "retryable": True}
                except httpx.RequestError:
                    outcome["failure"] = {"code": "provider_error", "message": "Detection provider could not be reached.", "retryable": True}
                except DetectionFailure as exc:
                    outcome["failure"] = {"code": exc.code, "message": str(exc), "retryable": exc.retryable}
                finally:
                    record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                    record["usage"] = outcome["usage"]
                    if outcome["failure"]:
                        record["failure_kind"] = outcome["failure"]["code"]
                    outcome["attempts"].append(record)
                if retry_after is None:
                    break
                record["retry_after_seconds"] = retry_after
                await self.sleep(retry_after)
        return outcome


def _retry_after(value):
    if value is None:
        return 1.0
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else 1.0
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return 1.0


async def detect_frames(adapter, frames, *, selection_finalized):
    if not selection_finalized:
        raise ValueError("Detection requires finalized choices.")
    if len(frames) > 40:
        raise ValueError("At most 40 stored frames may be processed.")
    outcomes = []
    for frame in sorted(frames, key=lambda f: (f["idx"], f["frame_id"])):
        outcomes.append(await adapter.detect(frame["jpeg"], frame["w"], frame["h"], frame["frame_id"]))
    succeeded = sum(o["state"] == "succeeded" for o in outcomes)
    return {"outcomes": outcomes, "processing": {"expected_frames": len(frames), "not_started": 0,
            "pending": 0, "succeeded": succeeded, "failed": len(frames) - succeeded}}


def detection_overlay_svg(outcome, width, height):
    from html import escape

    boxes = []
    for detection in outcome.get("detections") or []:
        x1, y1, x2, y2 = detection["box_px"]
        boxes.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="#0c8"/><text x="{x1}" y="{y1}">{escape(detection["category"])}</text>')
    if outcome["state"] == "failed":
        boxes.append(f'<text x="10" y="20">{escape(outcome["failure"]["code"])}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">' + "".join(boxes) + "</svg>"
