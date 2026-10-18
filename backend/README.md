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
continues to make no provider calls.

### Combined interview and Product test in Simulator

Use the authored JSON room measurements from the agent-loop fixtures below:

```sh
set -a
source .env
set +a
unset GOOGLE_API_KEY # Ensure the repository GEMINI_API_KEY wins over an inherited Google key.
export GEMINI_PLANNING_MODEL=gemini-3.1-pro-preview
export GEMINI_EXTRACTION_MODEL=gemini-3.8-flash
PYTHONPATH=backend .local/venv/bin/python -u -m respace.local \
  --port 8081 --live-providers \
  --test-shopping backend/tests/fixtures/agent_loop/01_small_living_room.json \
  --data-dir .local/shopping-loop/live-data \
  --trace-file .local/shopping-loop/agent.jsonl \
  > .local/shopping-loop/backend.log 2>&1
```

Create `.local/shopping-loop` first if necessary. These model IDs completed live
calls with the repository's funded credential on 2026-10-18; availability and
quota still depend on the configured project. This mode needs only the planning
and extraction models. It imports `agent_context.measured_context` and planning
instructions, remaps capture IDs, and labels the Room as synthetic. It never
imports fictional listings, expected answers or replay actions. No camera,
LiDAR, RoomPlan export, photos or processed room snapshot is fabricated.

In Xcode, run **ReSpace / Debug** on an iPhone Simulator. Set its Debug backend
URL to `http://127.0.0.1:8081`, open **TEST SHOPPING · Small living room**, and tap
**Design this room**. Enter a budget and natural-language priorities, then answer
the interview. The existing controller runs real Gemini actions, SerpAPI,
Playwright verification, ranking and final selection checks. It stops at Product
selection, where Debug shows selected Products and their evidence/scores. Spatial
fit, placement, design publication and image-to-3D are outside this test boundary.
To try a different request, start another design from the same test Room. You can
copy a fixture and change its authored measurements/Objects; a changed file hash
imports a new test Room. Keep the `synthetic` / `synthetic_json` provenance labels.

For a fast live smoke test, the copied scenario may explicitly contain:

```json
"shopping_scope": {
  "merchant_names": ["songmics"],
  "merchant_domains": ["www.songmics.com"],
  "candidates_per_query": 1
}
```

This test-only scope still calls the real provider for every query and resolves
real merchant URLs; it filters returned hits to the named merchant and then checks
only its domains. Prompts, extraction, ranking and final selection remain real.
The Room warning and trace label this restricted coverage. Original provider
responses remain in the trace. It proves the agent/tool wiring on a small case,
not full search breadth or market-wide recommendation accuracy. Omit the scope
for the normal three-query/full-candidate pass, which can be slow because it
checks each retained candidate's merchant offers.

The Xcode debug console shows client/network diagnostics. Backend HTTP/startup
output is in `backend.log`; `agent.jsonl` contains operation/search/span IDs,
Gemini prompts and structured responses, token usage, timings, questions/answers,
tool calls, merchant extraction, scores, rejected evidence and original provider
errors. Merchant image URLs are retained in each selected variant's
`image_references`; they must occur in the scraped page and address public HTTPS
hosts. Exhaustive gallery coverage is not established by this smoke test.
Follow either log with `tail -f`. Tracing is opt-in and credentials are
redacted; the trace file is private (0600) because interview/page content remains
in it. Normal runtime does not enable these prompt logs unless `--trace-file` is
supplied. SQLite records persist in the data directory. Do not mix this live data
directory with offline replay data.

The server binds loopback by default. For an
iPhone on a trusted LAN, use `--host 0.0.0.0` and configure its Debug backend URL
to the Mac's private address. The current API groups data by installation ID and
has no user authentication; expose it only on a trusted development network.
Release builds require HTTPS and supported capture hardware.

Run backend checks with `PYTHONPATH=backend .local/venv/bin/pytest backend/tests`.
Run shared native checks with `swift test`.

## Test shopping independently

The standalone shopping tests start at the exact request that planning sends to
`ProductService`. They need no iPhone, room model, running API, cloud database,
Perceptron, planning model or spatial model. Synthetic user preferences and
planner actions live in `tests/fixtures/shopping-scenarios.json`; the existing
planning request builder adds the real schema, budget and Room/operation context.
No measurements or merchant facts are invented for live runs.

First preview one request and its three actual search queries, without credentials
or network calls:

```sh
PYTHONPATH=backend .local/venv/bin/pytest -q -s \
  backend/tests/test_shopping_live.py -k 'preview and desk'
```

For live testing, export `SERPAPI_API_KEY`, `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
and `GEMINI_EXTRACTION_MODEL` in the shell. The CLI does not load `.env`
automatically. Install Chromium once, then run one scenario:

```sh
.local/venv/bin/python -m playwright install chromium
RESPACE_LIVE_SHOPPING=1 PYTHONPATH=backend .local/venv/bin/pytest -q -s \
  backend/tests/test_shopping_live.py -k 'live_shopping and desk'
```

To exercise real Chromium without using any provider credits, run the isolated
browser replay instead:

```sh
RESPACE_BROWSER_REPLAY=1 PYTHONPATH=backend .local/venv/bin/pytest -q -s \
  backend/tests/test_shopping_live.py -k browser_shopping_replay
```

This uses independently authored shopping requests and storefront pages, with
mock HTTP responses at the SerpAPI and Gemini boundaries. It exercises the real
adapters, merchant resolution, Chromium navigation/text capture, SDK schemas,
evidence validation and ranking. Real provider keys are removed from that test
process and live Python socket connections are blocked. The cases include
package-only desk dimensions, out-of-stock chair packs and missing rug footprint dimensions.
Each scenario also ranks two eligible synthetic alternatives in the expected
60/30/10 order. The desk case includes published specifications in a hidden HTML
tab with adjacent text nodes, checking that counts and item names remain separate.
`synthetic-listings.json` saves the authored storefront data beside the report.
It uses no synthetic room fixtures from the separate agent-loop tests.

In live mode, only the inputs are synthetic. Runs use the production SerpAPI adapter for
three fresh US/USD queries and merchant resolution, Playwright for merchant
pages, Gemini for extraction/ranking, and the usual evidence/eligibility checks.
Each scenario starts with an empty isolated SQLite store. This checks the fresh
discovery path; existing controlled tests cover cached candidates and stale checks.
Search can visit every discovered candidate, including alternative merchant
offers and browser retries. It is **not limited to three API
calls or three pages**; SerpAPI and Gemini usage can incur charges.

Replace `desk` with `chair_pair` to exercise two physical units, whole-pack
budgeting and a hard material requirement, or `rug` to verify its footprint while
allowing unpublished thickness. Remove the scenario filter to run all three. Change the fixture's
payload/preferences to test your own realistic request. `budget` is the approved
whole-room ceiling, not a per-Product allocation. Room dimensions/photos do not
enter this search request; final spatial fit is checked later.

The printed evidence directory contains `request.json`, `trace.jsonl`,
`report.json` (searches, retained candidates/rejections, dimensions, offers and
comparisons) and `records.sqlite3`. Pytest retains temporary directories for recent
runs. A passing live test requires successful fresh discovery and at least one
eligible choice with usable fit-critical dimensions, a supported USD shopping
offer, acceptable supplied contents and satisfied request constraints. A no-match fails
this smoke test but can be correct rejection behavior: inspect the report to
distinguish missing dimensions, inaccessible pages, unavailable stock and provider
failures. Local success does not establish deployed merchant coverage or room fit.
### Batched Product verification

Production searches retain the full discovered pool, with up to 50 relevant stored
candidates and three distinct fresh queries. Merchant URL resolution and browser
capture precede specification-based screening; a model batch is not a shortlist.
The existing planning controller receives completed rankings, checked facts,
rejected evidence, coverage and failure diagnostics before deciding whether to ask
one useful question, refine a search or finalize a verified purchase set.

Playwright preserves Product headings, selected controls, published hidden tabs,
text boundaries and raw JSON-LD, including metadata outside the main container.
Only confidently unrelated navigation/banner/footer content is removed; ambiguous
containers are retained. Each evidence field retains at most 500,000 characters.
Truncated captures are explicitly incomplete and cannot
yield selectable Products. No Python specification parser or normalized fact
packet runs before Gemini.

The DOM copy collapses ordinary formatting whitespace (not preformatted text or
JSON metadata) and removes SVG path geometry while retaining SVG text/labels.
These non-fact bytes otherwise crowd out real merchant pages; original visible
and specification text remain separate evidence channels. Input and capture
limits stay explicit, with oversized inputs rejected rather than silently cut.

Gemini receives both structured metadata and Product DOM in each bounded batch.
Its prompt requires exact-variant JSON-LD first, with DOM fallback only for
unresolved fit-critical facts. It maps a rug's published size to its footprint,
allows an ordinary single-item assumption, and retains usable conflicted facts
with caveats instead of blanket rejection. Python checks correlated
identities, source URLs, channel-specific quotations and the existing evidence
and eligibility rules. Clearer offers are preferred over conflicting or
availability-uncertain fallbacks, then the cheapest offer within that tier receives
batch fit scores. Python computes the global 60/30/10 ranking and comparison
snapshot across stored/live sources and all batches, not a batch-local benchmark.

Verification is practical rather than all-or-nothing: an ordinary single-item
listing can assume one supplied item, and rugs need their published footprint
but not thickness. Missing rug height uses the category's representative geometry
and is recorded in `dimension_evidence.assumed_axes`, never added as a published
measurement or used to satisfy an explicit height limit. Conflicting merchant
metadata and unknown stock remain eligible fallback options with visible
`verification_warnings`; clearer eligible alternatives rank first. Known
out-of-stock offers, unknown prices, missing fit-critical dimensions, unsupported
hard requirements and ambiguous mixed bundles still fail eligibility. The same
rules apply to discovery, ranking, selection rechecks, Swap and whole-pack totals.

`GeminiProductModels` defaults to conservative internal input/output budgets of
512,000/8,192 tokens. Prompt plus schema UTF-8 bytes bound input conservatively;
output reservation allows up to four listings and input size can split them sooner.
Constructor limits must fit the configured model. An oversized listing is isolated
and explicitly rejected without an unbounded request. These bounds are not a
production candidate limit or a claim of reduced input tokens or latency.

Each bounded step makes at most one external attempt. Room-scoped
`product_captures`, `product_batches` and progress cursors retain completed work
for replay and deletion. Transient whole-batch failures retry once; invalid,
missing, duplicate and mismatched listing results are isolated without discarding
valid peers. Searches report coverage, candidate dispositions, batch failures,
actual provider/merchant-resolution request counts and reported model tokens.
Evidence freshness uses capture time, not delayed extraction time; expired
captures are refreshed on resume. Planner retries also use persisted bounded steps.
Private opt-in traces add batch membership, timings and source-backed decisions,
not private model reasoning.

Run the controller integration regressions without provider credits:

```sh
PYTHONPATH=backend .local/venv/bin/pytest -q \
  backend/tests/test_product_batches.py backend/tests/test_discovery_replay.py
```

These tests cover independently authored desk, two-chair and rug requests, later
batch candidates, reordered/invalid results, global comparisons, question pause
and resume, refined searches, verified finalization, bounded retries and late
cancellation/deletion. The separate real-Chromium replay above tests capture.
Controlled acceptance is not deployed merchant coverage. Any live run still
requires a separate authorization covering searches, merchant lookups, captures,
model batches, planner calls and retries; these changes impose no new spend limit.

## Synthetic JSON inputs for planning and listings

Five self-contained fixtures in `tests/fixtures/agent_loop/` supply authored room
measurements directly to the planning boundary. They contain no room model files,
photos, LiDAR, native exports or detector observations. Their dimensions are
internally consistent test values, not measurements of real rooms.

| Fixture | Floor area / height | USD ceiling | Main coverage |
|---|---|---|---|
| [Small living room](tests/fixtures/agent_loop/01_small_living_room.json) | 15.12 m² / 2.60 m | 250.00 | Kept sofa, rug thickness, inch conversion, same variant at two merchants. |
| [Narrow office](tests/fixtures/agent_loop/02_narrow_office.json) | 11.52 m² / 2.45 m | 220.00 | Narrow door, fixed radiator, package-only rejection, millimeter conversion, lamp supported by a new desk. |
| [L-shaped studio](tests/fixtures/agent_loop/03_l_shaped_studio.json) | 22.72 m² / 2.70 m | 350.00 | Concave boundary, protected bed, removed original Object, wall mirror, ambiguous variant. |
| [Family room with two doors](tests/fixtures/agent_loop/04_family_room_two_doors.json) | 48.00 m² / 2.80 m | 300.00 | Two door widths, doorless opening, three chairs supplied by two packs, paid surplus, stock rejection. |
| [Tight bedroom](tests/fixtures/agent_loop/05_tight_bedroom.json) | 9.60 m² / 2.40 m | 300.00 | Required dresser cannot fit, over-budget alternative, supported lamp, unresolved must-have. |

Each file contains:

- `agent_context`: the context dictionary accepted by `GeminiPlanningModel.act`.
  Its `measured_context` uses explicit normalized measurements with source
  `synthetic_json`. The floor polygon defines usable space; extents describe only
  its bounding rectangle. `request` uses the existing Generation contract.
- `room_snapshot`: a synthetic processed RoomModel for `validate_plan` and `solve`.
  All observation/processing counts are zero. Objects have no fabricated sensor
  confidence or sampled colors. This snapshot bypasses capture and perception.
- `listings`: fictional candidates, extracted facts and supporting page text for
  the existing `checked_facts` verifier. Rejected evidence remains present.
- `replay`: recorded model actions, a numeric answer and listing selections for
  deterministic offline controller tests. A live model can choose different valid
  questions/actions. `spatial_case` supplies a separate Anchor plan and constraints.
- `expected`: test assertions, including selected purchase total, placed candidate
  total and fit conflicts. Keep this and the recorded replay out of model input.

Geometry uses meters, `[x,z]` floor coordinates, `[width,depth,height]` sizes and
yaw in radians. Objects specify `base_y` separately from their footprint center;
wall and tabletop Objects retain explicit wall/support references.

For an agent experiment, load JSON and pass only `fixture['agent_context']` to the
configured planning model. No model invocation is needed to run the offline replay:

```sh
PYTHONPATH=backend .local/venv/bin/pytest backend/tests/test_agent_loop_fixtures.py -q
```

The test's `FixtureCatalog` feeds recorded listings through the real ProductService
search, verification, ranking and purchase calculations without network calls.
Verification times are assigned at replay time so the fixtures do not expire;
their authored provenance time stays fixed. Fictional URLs and prices are offline
test evidence and must stay out of production Product catalogs. The supplied
`initial_products` is empty until this discovery step runs.

The controller replay stops at the finalized selection boundary; separate checks
run the actual plan validator and solver. In the bedroom, the selected set costs
USD 274.98, but the surviving candidate contains only the USD 24.99 lamp and an
unresolved `must_have_unplaced` conflict. That candidate cannot be published or
treated as permission to omit the dresser. The offline replay does not establish
live model, merchant, capture or device acceptance. The opt-in `--test-shopping`
mode above imports only their authored Room inputs for live interview/shopping
testing.

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

### Natural-language room requests

`POST /v1/rooms/{room_id}/designs` accepts `intent: "auto"`, `text`, the existing capture/planning/active revision fields and optional `selected_object_id`. The iOS client no longer submits a mode, style form or invented budget. Gemini resolves scope/style before discovery and asks a text clarification for missing budget. Resolved inputs persist on the operation; original request and answers remain available to spatial planning. Explicit zero allows an empty purchase set, with the same collision, Keep, budget and publication checks. Legacy explicit-mode requests are retained.

`POST /v1/rooms/imported` attaches reconstructed Object bounds as private planning context, with `source_capture_id`, `source_scene_sha256` and typed `entities`. It uses creation receipts for retries. This is not a native RoomPlan capture: generated results are verified Product selections, not applied layouts. The UI states this limit; original capture/support evidence is still required for validated placement.

Verification: `PYTHONPATH=backend .local/venv/bin/python -m pytest backend/tests/test_natural_request.py -q`. Offline providers simulate the interpretation for UI testing; live Gemini interpretation requires the configured planning model.

## Room previews from a reconstruction

Places Products into a fully modelled room (a reconstruction USDZ plus its JSON
record) and writes one preview USDZ. The record format is version 2 of
[`specs/room-reconstruction-json.md`](../specs/room-reconstruction-json.md).

1. `reconstruction.room_from_reconstruction(record, room_id)` reads the record
   into the same RoomModel that native captures produce, with wall
   `protrusions`, support `surfaces` (with `holes`) and unclassified `obstacles`
   (`SPEC.md` §12.5). It returns `validity.usable: false` with reasons instead
   of guessing. It snaps floor, ceiling and tabletop contact within 2 cm.
2. `solver.solve(...)` places the Additions as for any room.
3. `composition.compose(room_usdz, room, scene, out)` references each new Item's
   asset at its placement, moves the nodes of moved Objects and deactivates
   removed or replaced ones. It refuses the room when a node is missing, or is more
   than 1 cm or 1° from its record horizontally, or more than 3 cm vertically.

The model must be in room coordinates, like the JSON. A model left in scan
coordinates is off by the `room_from_world` translation on every node, and is
refused. Placements stay in room coordinates even if the model's root carries a
transform. Records may name a node as written (`chair-6`) or as USD stores it
(`chair_6`).

The room model can be a `.usdz` or a plain USD layer. Product assets come from
`assets.asset_path` unless a `resolve` function is passed; a missing asset is
drawn as a box of the placement's size.

Composition needs usd-core, which the API image does not install by default:

```sh
.local/venv/bin/pip install -e 'backend[test,usd]'
```

Without it, `tests/test_composition.py` skips. Not yet wired to an endpoint:
`POST /v1/rooms/imported` still accepts the version 1 record as planning-only
context.
