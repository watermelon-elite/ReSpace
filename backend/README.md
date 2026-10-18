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
The CLI reads the process environment; it does not automatically load `.env`.
Export the credential for the credited Gemini project in that process.

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

## Post-scan verification (2026-10-17)

Both requested waves ran with three ticket subagents in parallel. Initial LiDAR
scanning and room reconstruction were excluded. The resulting fixes reject
catalog conversion without supplied dimensions, give Gemini the canonical typed
edit-plan schema, report malformed actions without losing valid independent
changes, reuse an explicitly requested saved snapshot, and keep unfinished
spatial/edit candidates out of public Operation and Room responses.

The credited repository Gemini credential produced a valid planning question
that survived SQLite reopen (1,825 tokens). A real edit response exposed the
malformed-action bug (33,326 tokens); its recorded replay now rejects safely.
Spatial attempts and the final small edit check returned HTTP 503. One real
Product extraction failed. These checks used synthetic repository room inputs;
they do not establish a successful live design or fixed-schema edit.

The new SerpAPI key completed three fresh US/USD shopping queries: 120 hits,
109 distinct Google Product IDs and 68 source labels. One merchant-resolution
request found seven offers. Tribesigns loaded in the production browser;
Macy's was inaccessible. Four free SerpAPI searches were used, leaving 246.
No eligible Product or selected purchase was asserted from incomplete evidence.

All 21 stand-ins passed immutable API delivery checks and native numeric loading
checks. SPAR3D still requires approved model access (HTTP 401), a suitable runtime
and license confirmation. Complete exact-variant catalog evidence, deployed
sessions, successful live edits and iPhone fidelity/performance remain open.

Final verification: 247 backend tests and 30 Swift tests passed. Full mypy checks
28 modules and reports two pre-existing multipart capture-upload type errors;
that excluded implementation was left unchanged. No native source changed, so
the iPhone build was not repeated. Detailed bounded probes, usage and coverage
are retained in [`assets/proof.json`](../assets/proof.json).
