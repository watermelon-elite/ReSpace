# Local development

The current priority is a local end-to-end testing loop. Cloud deployment and live
acceptance with physical scans remain deferred. By default local mode disables
providers, even if credentials exist in the environment. Live providers require
the explicit `--live-providers` flag; their usage can incur charges.

From the repository root, with Python 3.12 or newer:

```sh
python3.12 -m venv .local/venv
.local/venv/bin/pip install -e 'backend[test]'
PYTHONPATH=backend .local/venv/bin/python -m respace.local \
  --data-dir .local/respace \
  --test-model /Users/humaid/Downloads/room.glb
```

Open `ReSpace.xcodeproj`, select ReSpace / Debug and an iPhone Simulator, and run.
Debug defaults to `http://127.0.0.1:8000`. Open **TEST MODEL · room.glb**, continue
to design intent, enter a budget of **USD 200**, and answer the three questions.
The saved design supports Product details, Find more, Swap, Remove and Undo.
Offline conversation commands support one Move, Remove or Restore of a named
or selected Item at a time.

Some Simulator reopens still render a blank 3D surface, and accessibility
automation can time out after edits. Saved Scene/API checks pass; full native
visual verification remains open in [#42](https://github.com/watermelon-elite/ReSpace/issues/42).

The opt-in test mode imports actual floor triangles from the supplied `room.glb`.
Its **10 metres per source unit is an uncalibrated test assumption**; walls are
synthesized from its simplified floor contour. It imports no Objects, doors,
windows, photos, LiDAR or detector evidence. Source attribution, scale assumptions
and exact floor contour are retained in the capture's `test_source` metadata.
The apartment model is skipped because its room partitions have not been mapped.
The original GLBs stay outside the repository.

Planning answers and Product listings/evidence are explicitly simulated. Product
evidence validation, ranking, budgets, geometry, placement, purchase calculations,
immutable publication and history use the existing implementations. This mode
does not establish live discovery, calibrated capture or physical-device acceptance.

SQLite records and private capture files persist under `.local/respace`, which is
gitignored. Stop with Ctrl-C and rerun the same command to reopen saved Rooms and
resume runnable Operations. Questions remain pending until answered. A deleted
test Room is not reimported into the same installation and data directory.

Omit `--test-model` to run the durable local API without simulated providers;
planning reports unavailable unless live providers are explicitly enabled.

## Real providers with a local backend

Configure `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `SERPAPI_API_KEY`,
`GEMINI_PLANNING_MODEL`, `GEMINI_EXTRACTION_MODEL` and `GEMINI_SPATIAL_MODEL`.
Set `GEMINI_EDIT_MODEL` if edits should use a different model; otherwise they use
the spatial model. Use model IDs available to the configured account. Install the
merchant browser once with `.local/venv/bin/python -m playwright install chromium`.
Startup reports missing configuration before creating data or calling a provider.

```sh
PYTHONPATH=backend .local/venv/bin/python -m respace.local \
  --live-providers --test-model /Users/humaid/Downloads/room.glb
```

This uses the existing real Gemini/search/browser/evidence/solver/edit adapters
with SQLite and private local files. It requires no cloud services. The default
data directory is `.local/respace-live`; simulated test Rooms and live-provider
test Rooms cannot share a directory. Omitting `--test-model` uses ordinary
completed room inputs and retains the normal requirement for planning photos.

With a test model, only the room input is synthetic: geometry-only layout
planning explicitly tells the model that no room photos exist. Real Product
dimensions, offers, packs and budgets still require their usual evidence checks.
The room remains labeled as uncalibrated test input, so this mode does not prove
native scan accuracy or full live acceptance. The default offline command above
continues to make no provider calls. The current $0 run has not enabled live mode.

The server binds loopback by default. For an
iPhone on a trusted LAN, use `--host 0.0.0.0` and configure its Debug backend URL
to the Mac's private address. The current API groups data by installation ID and
has no user authentication; expose it only on a trusted development network.
Release builds require HTTPS and supported capture hardware.

Run backend checks with `PYTHONPATH=backend .local/venv/bin/pytest backend/tests`.
Run shared native checks with `swift test`.
