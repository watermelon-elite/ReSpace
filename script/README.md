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

The timeline follows **words, not elapsed seconds**. Cards contain a short shot description and an expandable **Details** note. Exact layer timing remains in the data; full sound and production directions remain in `data/storyboard.md`. The middle's Details also retain the approved source directions verbatim, including their editorial timing references. All lanes receive a minimum readable card width, and lane names stay visible during horizontal scrolling. The current Working cut has 22 narration beats and 314 spoken words.

The treatment uses an **external narrator for the saved opening**, then the **ReSpace team** addressing the lens and continuing over demonstrations. Base contains 34 camera takes/full-screen sequences, Overlay contains 22 independent inserts and panels, and Top overlay contains 30 labels and attention cues. The existing Working opening and closing were preserved, including the user's narration and removed opening blocks; they were not reset to the earlier seed.

The middle, **00:24–02:42**, now follows all twelve passages in the approved [middle proposal](../.lavish/respace-middle.html). It replaces the previous demonstration, business passage, flower/imagined evening, community and pitch reservations. Its 25 Base blocks, 19 Overlay blocks and 27 Top overlay blocks cover capture, Keep/budget, generated questions, taste, research papers, six diagram returns, Product discovery and checking, solver placement, the room reveal, edit/Undo, shopping, the Mom draft and café/office sharing. The beauty view has no overlays from **01:57–02:01**. The original **02:42–03:00** closing remains intact. The film retains its completed-product creative brief; the directions distinguish proposed imagery from current implementation and automatic publication.

The existing workspace's Original version preserves the earlier treatment; its Working version contains this middle replacement. Fresh workspaces start both versions from the current seed. Working edits save to `data/workspace.json`; the 180-second planned runtime remains fixed when text changes. Shot timings are production directions and need editorial review if the narration changes substantially. This is the planning screen, without video playback, media uploads or automatic script generation.

## Files

- `app.py`: localhost server and atomic JSON persistence for the existing screen's endpoints.
- `templates/`, `static/`, `format_workflow/`, `vlog_format/`: copied DS_HQ screen, styles, editor, presentation, word anchors and export helpers. Adaptations retain landscape format and explicit shot times, remove Contributors, refresh export after edits, show delivery roles in export and collapse concise details for readable stacked tracks.
- `data/seed.json`: current complete layered treatment; `data/voiceover.txt` and `data/storyboard.md` are the recording copy and production directions. The earlier research storyboard outside this folder remains unchanged.
- `data/middle.json`: the twelve approved narration passages, complete source directions and independently timed Base/Overlay/Top overlay blocks.
- `seed.py`: refreshes only the seed's middle from `data/middle.json`, preserves surrounding seed records, and updates the recording copy and storyboard. It does not overwrite working edits. `replace_middle` can apply the same replacement to an explicitly chosen package while preserving its own opening and closing anchors.
- `data/workspace.json`: private local working state, excluded from Git. Back up this file to retain edits and comments.
- `static/fonts/licenses/inter-OFL.txt`: license for the copied Inter font.

## Check

```sh
.venv/bin/python -m unittest -v test_app
```

The checks cover the twelve passages against the approved HTML, removal of old middle content, independent layer timing/anchors, the unobstructed beauty hold, export, idempotent seed refresh, preservation of custom opening/closing records and the original/180-second runtime, persistence, comments and rejected writes. The server binds only to localhost and rejects cross-origin writes.
