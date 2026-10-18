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

The timeline follows **words, not elapsed seconds**. Cards contain a short shot description and an expandable **Details** note. Timestamps, delivery labels and production boilerplate are omitted from both fields. Exact layer timing remains in the data; full sound and production directions remain in `data/storyboard.md`. All lanes receive a minimum readable card width, and lane names stay visible during horizontal scrolling. The current cut has 47 editorial beats and 262 spoken words; several beats share continuous camera takes.

The current treatment uses an **external dramatic narrator for 00:00–00:24**, then the **ReSpace team** addressing the lens and continuing off camera over demonstrations and story cutaways. Base contains 26 camera takes/full-screen sequences; Overlay contains 18 independent story inserts, demo panels, commercial-space designs, comparison insets, furnishings-only composites and end-card artwork; Top overlay contains 17 foreground labels and attention cues. The opening adds room-key, notebook and photograph inserts plus three subtle graphic accents; app panels enter with the presenter. Presenter footage remains underneath staggered scan, budget and goal panels; unfamiliar questions and key results get full-screen holds. The acted imagined future keeps real people/contact surfaces in Base and proposed furnishings in Overlay.

At **01:20–01:39**, café and office designs demonstrate business-space use cases, labeled **Café · Connection** and **Office · Focus**. The script assumes the product is complete, as requested. At **01:39–01:44**, “A flower blooms in the right environment” accompanies a cinematic macro bloom that match-cuts into the student opening his notebook. Technical and affiliate/freemium explanations retain seven-second reservations each. The flower and commercial-space imagery are planned assets, not supplied media.

The existing workspace's Original version preserves the earlier treatment; its Working version contains this layer revision. Fresh workspaces start both versions from the current seed. Working edits save to `data/workspace.json`; the 180-second planned runtime remains fixed when text changes. Shot timings are production directions and need editorial review if the narration changes substantially. This is the planning screen, without video playback, media uploads or automatic script generation.

## Files

- `app.py`: localhost server and atomic JSON persistence for the existing screen's endpoints.
- `templates/`, `static/`, `format_workflow/`, `vlog_format/`: copied DS_HQ screen, styles, editor, presentation, word anchors and export helpers. Adaptations retain landscape format and explicit shot times, remove Contributors, refresh export after edits, show delivery roles in export and collapse concise details for readable stacked tracks.
- `data/seed.json`: current layered treatment; `data/voiceover.txt` retains the approved words and `data/storyboard.md` contains the revised production directions. The earlier research storyboard outside this folder remains unchanged.
- `seed.py`: rebuilds the seed from those local copies. It does not overwrite working edits.
- `data/workspace.json`: private local working state, excluded from Git. Back up this file to retain edits and comments.
- `static/fonts/licenses/inter-OFL.txt`: license for the copied Inter font.

## Check

```sh
.venv/bin/python -m unittest -v test_app
```

The checks cover rendering, all 47 shots in export, persistence, word-anchor remapping, preservation of the original and 180-second runtime, comments, and rejected writes. The server binds only to localhost and rejects cross-origin writes.
