import asyncio
import json

import httpx

from respace.perception import PerceptronAdapter


def test_chat_grid_becomes_uploaded_pixels_and_empty_success_stays_distinct():
    bodies = []
    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '<point_box mention="plant" asset_idx="0">(100,200) (300,600)</point_box>'}}],
            "usage": {"prompt_tokens": 30}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await PerceptronAdapter("key", client=client).detect(b"jpeg", 1000, 500, "f1")
    result = asyncio.run(run())
    assert result["state"] == "succeeded"
    assert result["detections"] == [{"category": "plant", "box_px": [100,100,300,300]}]
    assert bodies[0]["vision_config"] == {"annotation_format": "box"}
    assert "material" not in bodies[0]["messages"][0]["content"][1]["text"]


def test_empty_parse_timeout_and_provider_failure_have_distinct_terminal_outcomes():
    async def run(response):
        def respond(request):
            if isinstance(response, Exception):
                raise response
            return response
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await PerceptronAdapter("key", client=client).detect(b"jpeg", 100, 100, "f")
    empty = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "No objects visible."}}]})
    assert asyncio.run(run(empty))["detections"] == []
    malformed = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '<point_box mention="plant">broken</point_box>'}}]})
    assert asyncio.run(run(malformed))["failure"]["code"] == "parse_error"
    timeout = asyncio.run(run(httpx.ReadTimeout("timeout")))
    assert timeout["failure"]["code"] == "timeout"
    failed = asyncio.run(run(httpx.Response(503)))
    assert failed["failure"]["code"] == "provider_error"
    assert len(failed["attempts"]) == 1


def test_only_rate_limit_retries_once_and_honors_retry_after():
    calls, sleeps = [], []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0.01"})
    async def sleep(seconds):
        sleeps.append(seconds)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await PerceptronAdapter("key", client=client, sleep=sleep).detect(b"jpeg", 100, 100, "f")
    outcome = asyncio.run(run())
    assert len(calls) == 2
    assert sleeps == [.01]
    assert outcome["failure"]["code"] == "rate_limit"


def test_pixel_detect_is_not_rescaled_as_chat_grid():
    from respace.perception import parse_detections
    response = {"finish_reason": "complete", "detections": [{"mention": "rug", "point_box": {
        "top_left": {"x": 100, "y": 20}, "bottom_right": {"x": 300, "y": 100}}}]}
    assert parse_detections(response, 640, 480, "detect")[0]["box_px"] == [100,20,300,100]


def test_dedicated_detect_uses_documented_media_request_and_keeps_model_identity_unknown():
    bodies = []
    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"detections": [], "finish_reason": "complete"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await PerceptronAdapter("key", client=client, mode="detect").detect(b"jpeg", 100, 100, "f")
    outcome = asyncio.run(run())
    assert bodies[0]["media"]["type"] == "image"
    assert bodies[0]["media"]["image_url"].startswith("data:image/jpeg;base64,")
    assert "model" not in bodies[0]
    assert outcome["model"] is None
