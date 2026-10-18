# Perceptron API facts (researched 2026-10-17)

Legend: **[C]** = confirmed from primary source (docs.perceptron.inc, the official SDK source, or PyPI). **[I]** = inferred, or from a third-party listing.

## 1. Docs, base URL, auth, SDK
- [C] Docs: https://docs.perceptron.inc (index: https://docs.perceptron.inc/llms.txt). There are separate doc trees for Mk1.5 (`/perceptron-mk1.5/...`) and Mk1 (`/perceptron-mk1/...`).
- [C] Base URL: `https://api.perceptron.inc/v1`. The API is OpenAI-compatible: `POST /v1/chat/completions`. There is also a native `POST /v1/detect`, plus `/v1/models`, `/v1/files` and Multilook.
- [C] Auth header: `Authorization: Bearer $PERCEPTRON_API_KEY`. Get keys at https://platform.perceptron.inc/. Source: https://docs.perceptron.inc/perceptron-mk1.5/guides/python/auth.md
- [C] Python SDK: `perceptron` on PyPI, **v0.4.0** (released 2026-09-24), Python >=3.10. Repo: https://github.com/perceptron-ai-inc/perceptron (commit 5607603, 2026-09-25). `AsyncClient` exists, which suits FastAPI.
  - Main call: `Client(api_key=..., provider="perceptron", timeout=60.0).chat.completions.create(model="perceptron-mk1.5", messages=[{"role":"user","content":[image(url_or_path_or_bytes), {"type":"text","text":...}]}], vision_config={"annotation_format":"box"}, reasoning_effort="high", max_completion_tokens=2048)`
  - High-level helpers: `detect(media, *, classes=None, examples=None, strict=None, max_outputs=None, stream=False, response_format=None, **kw)`, plus `question`, `caption`, `ocr`, and `perceive`. `detect()` runs over chat completions with `expects="box"`, so it returns 0–1000 coordinates (source: `src/perceptron/highlevel.py`).
  - The SDK does **not** retry automatically. Its `retries` setting is accepted but does nothing (auth doc).

## 2. Model IDs
- [C] `perceptron-mk1.5`: **current**, the SDK default, and recommended for new integrations. Released 2026-09-25. Context window 36,864 tokens, max output 8,192 tokens. Accepts text, image, video and audio input. Supports tool calling and `reasoning_effort`. https://docs.perceptron.inc/perceptron-mk1.5/models/perceptron-mk1.5.md
- [C] `perceptron-mk1`: still listed. Accepts text, image and video, with no function calling. OpenRouter [I] gives it a 32,768-token context.
- [C] `perceptron-mk1.5-preview` was renamed to `perceptron-mk1.5`; the old ID returns 400 `model_renamed`.
- [C] `isaac-0.1`, `isaac-0.2-1b` and `isaac-0.2-2b-preview` were **retired** from the Perceptron API on 2026-09-25 and return 404 `model_not_found`. `isaac-0.1` is still served on fal (`https://fal.run/perceptron/isaac-01/openai/v1/chat/completions`, header `Authorization: Key $FAL_KEY`) per the SDK's `_providers.py`. https://docs.perceptron.inc/perceptron-mk1.5/changelog.md
- [C] Isaac-0.1 open weights: https://huggingface.co/PerceptronAI/Isaac-0.1 (CC-BY-NC-4.0, roughly 2B parameters).

## 3. Grounded outputs (boxes/points/polygons)
- [C] Request parameter: `vision_config.annotation_format`, set to **one of** `"point" | "box" | "polygon" | "clip"`. This is a single enum value, not a list (OpenAPI `AnnotationFormat`). Describe the targets in the prompt text.
- [C] Output is **markup inside `choices[0].message.content`** mixed with prose. It is not a JSON detections array:
  ```
  <point mention="button center" asset_idx="0"> (120,200) </point>
  <point_box mention="package" asset_idx="0"> (100,150) (300,350) </point_box>   # top-left, bottom-right
  <polygon mention="surface" asset_idx="0"> (20,40) (60,40) (60,80) (20,80) </polygon>
  <collection mention="packages" asset_idx="0"> <point_box>...</point_box> ... </collection>
  ```
  `mention` holds the label. `asset_idx` is optional and refers to the zero-based media index; if it is missing, the annotation applies to the last asset. https://docs.perceptron.inc/perceptron-mk1.5/concepts/annotations.md
- [C] **Coordinates: integers on a normalized 0–1000 grid for each image, origin at the top-left, x increasing to the right and y increasing downward.** `(500,500)` is the center for any aspect ratio. To convert to pixels: `px = x*W/1000`, `py = y*H/1000`, using the dimensions of the image *as you supplied it*, after EXIF orientation is applied. https://docs.perceptron.inc/perceptron-mk1.5/concepts/coordinates.md
- [C] **Exception:** the native `POST /v1/detect` endpoint returns **pixel coordinates in the target image** as JSON: `{"detections":[{"mention":..., "point_box":{"top_left":{"x","y"},"bottom_right":{...}}}], "finish_reason":"complete"|"max_tokens"}`. It supports only `config.output` = `"box" | "point"` (no polygons), takes `categories` (max 256, no commas) and pixel-space `exemplars` / `negative_exemplars`, and returns no confidence scores. It is image-only and uses "its own supported model". https://docs.perceptron.inc/capabilities/detect.md
- [C] Legacy `<hint>BOX</hint>` / `<hint>THINK</hint>` system-message tokens are still injected by the SDK's `expects=` path (`client.py::_build_hint_content`). The docs, however, steer new code to `vision_config` and `reasoning_effort`.
- [C] Mk1 uses the same 0–1000 grid with a top-left origin. https://docs.perceptron.inc/perceptron-mk1/concepts/coordinates.md

## 4. Multiple labels, mixed types, attributes
- [C] Multiple labels per call: **yes**. The docs show "Locate helmets, vests, and goggles. Use those labels...", with each annotation's `mention` set to its label. `/v1/detect` accepts up to 256 categories.
- [C] Collections "can contain different geometry types" in the output grammar. **However**, `annotation_format` takes a single value per request.
- [I] Getting boxes for some labels and points for others in **one** request is not documented as a supported pattern. You would have to ask for it in the prompt and hope the model complies. The safe options are separate requests per geometry type, or boxes for everything with centers computed client-side (this is what `/v1/detect` point mode does internally).
- [C] Free text: prose can sit alongside the annotation markup in `content`, and `mention` is free text, so attributes like "brass floor lamp" could go there.
- [C] `response_format` JSON Schema (structured attributes such as color or material) is a **separate output contract**. The docs show grounding and JSON counts as two separate requests and never document combining a JSON schema with `annotation_format`.
- [I] Practical approach: request boxes with descriptive mentions, or run a second JSON-schema call for attributes.

## 5. Image input
- [C] Ways to send an image: `image_url` (an HTTP(S) URL **or** a base64 data URL), `image_file_id` (from the Files API, 128 MiB per file, 100 GiB per organization), or a `/v1/files/{id}/content` URL. The SDK's `image()` takes a path, bytes, URL, or `file_id`, and encodes local files inline as base64.
- [C] Formats: **PNG, JPEG, WebP only**. Anything else returns `invalid_image_format`; convert GIF, BMP, TIFF or HEIC first (SDK README troubleshooting).
- [C] JSON request body limit: **20 MiB**, and base64 counts against it. Max 256 media units per request. https://docs.perceptron.inc/perceptron-mk1.5/guides/scaling.md
- [C] Server-side preprocessing: "Large images may be resized, and small images may be upscaled." No max resolution or token-per-image table is published. **Coordinates are unaffected** because they are normalized to the image you supplied. https://docs.perceptron.inc/perceptron-mk1.5/guides/tokenization.md
- [C] The SDK does not resize client-side. `Settings.resize_max_side` exists but is unused in the v0.4.0 source.

## 6. Pricing, limits, latency
- [C] Mk1.5 pricing per 1M tokens: input $0.15, output $1.50, cached input $0.0375 (model card).
- [C] No per-image token cost is documented. The docs say to measure `usage.prompt_tokens` on representative images.
- [I] OpenRouter (`perceptron/perceptron-mk1.5`, served only by Perceptron) lists the same prices. Mk1 has the same prices too.
- [C] Rate limits (default, per organization): **300 req/min** for chat completions and 150 req/min for Multilook. Honor `Retry-After` on 429.
- [C] Request time budget: **120 s** for chat completions and 300 s for Multilook.
- [I] Latency: the OpenRouter page (via search snippet) showed P50 of about 0.99 s and about 37 tok/s. There is no official latency figure. Reasoning adds both latency and output tokens. OpenRouter lists the default `reasoning_effort` for Mk1.5 as `high`; the direct-API default is not stated.
- [I] OpenRouter's `supported_parameters` for Mk1.5 does not include `vision_config`, so grounding format control may not pass through OpenRouter. Call the Perceptron API directly.

## 7. SDK parsing helpers
- [C] On the response: `response.annotations(strict=True)` returns an `AnnotationCollection` with `.boxes`, `.points`, `.polygons`, `.clips` and `.tracks`, and `response.resolve_asset_idx(ann)`. Box objects expose `.top_left.x/.y`, `.bottom_right.x/.y` and `.mention`.
- [C] Module-level: `collect_annotations(text, *, expects=None, strict=False)`, `parse_annotations` (lenient, with `.errors`), `parse_text` (strict), `extract_points(text, expected=...)`, `resolve_asset_idx(ann, n_assets)`, `scale_points_to_pixels(anns, *, width, height, clamp=True)`, `scale_annotations_by_asset(anns, sizes, *, n_assets=None, clamp=True)`, and `PerceiveResult.boxes_to_pixels(width, height, clamp=True)`.
- [C] The docs warn against parsing the markup with an HTML parser (`track` is a void element in HTML). Validate that coordinates fall within 0–1000, that `x1<x2` and `y1<y2`, and that `finish_reason == "stop"`.
- Full worked renderer: https://docs.perceptron.inc/perceptron-mk1.5/guides/rendering-annotations.md
