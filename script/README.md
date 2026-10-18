# ReSpace script screen

A temporary, local copy of the DS_HQ Format Scripts screen populated with the approved three-minute ReSpace launch film. All runtime code, dependencies, source content and saved edits live in this folder. The iPhone app and DS_HQ are independent of this prototype.

Open **http://127.0.0.1:5190** while the server is running.

## Run

From this folder, using the prepared environment:

```sh
.venv/bin/python app.py --port 5190
```

For a fresh checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --port 5190
```

## Editing

The screen retains DS_HQ's inline narration and visual-direction editing, automatic saving, anchored comments, original/working version selector, page-width controls, linked word highlighting, Timeline/Grid views, subtitle exceptions and styled Copy Export. Contributors and the rest of the pipeline are omitted.

The timeline follows **words, not elapsed seconds**. Base blocks include exact shot timecodes and full picture/action/sound notes. Silent shots attach to the preceding spoken block, including the 02:18–02:42 technical/business/future reservations. All 43 shots and all 224 spoken words are present. The subtitle lane contains emphasis exceptions; ordinary narration receives captions by default.

The Original version preserves the approved script. Working edits save to `data/workspace.json`; the 180-second planned runtime remains fixed when text changes. Shot timings are production directions and need editorial review if the narration changes substantially. This is the planning screen, without video playback, media uploads or automatic script generation.

## Files

- `app.py`: localhost server and atomic JSON persistence for the existing screen's endpoints.
- `templates/`, `static/`, `format_workflow/`, `vlog_format/`: copied DS_HQ screen, styles, editor, presentation, word anchors and export helpers. Adaptations retain landscape format and explicit shot times, remove Contributors, and refresh export after edits.
- `data/seed.json`: initial content; `data/voiceover.txt` and `data/storyboard.md` are contained copies of the approved source material.
- `seed.py`: rebuilds the seed from those local copies. It does not overwrite working edits.
- `data/workspace.json`: private local working state, excluded from Git. Back up this file to retain edits and comments.
- `static/fonts/licenses/inter-OFL.txt`: license for the copied Inter font.

## Check

```sh
.venv/bin/python -m unittest -v test_app
```

The checks cover rendering, all 43 shots in export, persistence, word-anchor remapping, preservation of the original and 180-second runtime, comments, and rejected writes. The server binds only to localhost and rejects cross-origin writes.
