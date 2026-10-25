# Model costs and routing research

Checked 2026-10-25. **Confirmed** means source or official documentation establishes the claim. **Inferred** means an engineering recommendation or arithmetic scenario; no alternative was benchmarked or configured by this research. Prices are USD, excluding taxes, infrastructure and third-party search. This is a repository audit, not an account invoice or deployment inventory.

## Calls present in this checkout

- **Confirmed — fresh walkthroughs:** At the initial audit, [`threejs_agent.py`](../services/reconstruction/respace_reconstruction/threejs_agent.py) used `gpt-6-astra` with high reasoning. The user's subsequent 25 October instructions switch both authoring and independent native-asset photo reviews to `gpt-6.1-sol`, initially with medium reasoning; the later modeling-only request sets authoring to high while independent review remains medium. The author can request 32,768 output tokens per turn; each review can request 6,000. The continuing conversation, images and tool results are input to later turns. [`astra_spending.py`](../services/reconstruction/respace_reconstruction/astra_spending.py) retains the shared $10 generation cap, unknown-outcome reservations and paid checkpoints, and adds Sol 6.1 rates without changing historical rates. Other model selections remain unchanged.
- **Confirmed — planning and Products:** [`backend/README.md`](../backend/README.md) records successful 2026-10-18 local test calls using `gemini-3.1-pro-preview` for planning and `gemini-3.8-flash` for Product extraction/scoring. These are documented test settings; current production values were not established. [`planning.py`](../backend/respace/planning.py), [`discovery.py`](../backend/respace/discovery.py), [`spatial_planning.py`](../backend/respace/spatial_planning.py) and [`edits.py`](../backend/respace/edits.py) read environment-configured model IDs. Spatial/edit IDs have no verified default in the deployment template.
- **Confirmed — perception path:** [`perception.py`](../backend/respace/perception.py) defaults chat detection to `perceptron-mk1.5`, also accepts `perceptron-mk1`, and has a separate `/v1/detect` mode. Mk1.5 prices below apply to its chat model, not an independently verified detect-endpoint rate. Presence in this path does not establish a call during every fresh walkthrough.
- **Confirmed — retained reconstruction and photographs:** [`astra.py`](../services/reconstruction/respace_reconstruction/astra.py) and [`renditions.py`](../services/reconstruction/respace_reconstruction/renditions.py) use `gpt-6-sol`. Renditions call `gpt-image-2` at high quality, 1536×1024, with scan references. These optional/retained paths are separate from the fresh Three.js authoring loop.

## Official token prices

**Confirmed — OpenAI Standard, per million tokens:**

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| GPT-6 Astra | $10.00 | $1.00 | $50.00 |
| GPT-6 Sol | $2.00 | $0.20 | $10.00 |
| GPT-6.1 Sol | $2.00 | $0.10 | $10.00 |
| GPT-6 Luna | $0.10 | $0.01 | $0.50 |

Sources: [official OpenAI pricing](https://developers.openai.com/api/docs/pricing), [GPT-6 Sol model card](https://developers.openai.com/api/docs/models/gpt-6-sol). Sol's $0.20 cache rate remains correct for Sol; the $0.10 rate belongs to 6.1 Sol. Cache writes and long-context uplifts require separate accounting. The [6.1 Sol card](https://developers.openai.com/api/docs/models/gpt-6.1-sol) lists image input, Responses function calling and structured outputs; prompts above 272k tokens cost twice the input/cache rates and 1.5 times output. **Confirmed:** hidden reasoning is billed as output; `max_output_tokens` includes it. [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).

**Confirmed — Gemini Standard, text/image/video input and output including thinking, per million tokens:**

| Model | Input | Output | Qualification |
| --- | ---: | ---: | --- |
| Gemini 3.1 Pro Preview | $2.00 | $12.00 | Prompts ≤200k; above that $4/$18 |
| Gemini 3.8 Flash | $0.75 | $3.75 | Through Dec 31, 2026; then $1.50/$7.50 |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 | Current Standard rate |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 | Current Standard rate |
| Gemini 2.5 Flash-Lite | $0.10 | $0.40 | Older option, quality requires evaluation |

Google lists search grounding separately: 5,000 monthly free requests shared across Gemini 3+ models, then $14/1,000 search requests. This does not price the app's separate SerpAPI searches. [Official Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). [3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite) supports structured output and function calling. [3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) supports low/medium/high thinking; `minimal` is invalid.

**Confirmed — Perceptron Mk1.5:** input $0.15, cached input $0.0375, output $1.50 per million tokens. [Official model card](https://docs.perceptron.inc/perceptron-mk1.5/models/perceptron-mk1.5.md), successfully fetched directly after the web reader could not access it. Its [tokenization guide](https://docs.perceptron.inc/perceptron-mk1.5/guides/tokenization.md) says image processing determines visual tokens; compressed JPEG size is not a token count. Measure reported prompt/completion usage for representative frames. No current Mk1 price was independently established.

**Confirmed — GPT Image 2:** OpenAI's example output estimates for 1536×1024 are $0.165 high, $0.041 medium and $0.005 low. Input/reference images and the mainline orchestration model add charges. These are output estimates, not a complete room-image price. [Official image cost guide](https://developers.openai.com/api/docs/guides/image-generation#cost-and-latency).

## Recommendations

**Confirmed — one retained local run inspected in this audit:** 85 settled Astra calls recorded $9.635314 in its spending ledger: 83 authoring calls ($9.019554) and two review calls ($0.615760). Its author state had no successful submission. This is a local ledger estimate for one run, not a provider invoice or successful-room average. Responses reported 5,313,883 input tokens, including 5,131,453 cached and 182,175 cache-write tokens, plus 44,482 output tokens. **Inferred cost-only counterfactual:** pricing those same quantities at 6.1 Sol's ordinary/cache/write/output rates of $2/$0.10/$2.50/$10 yields about $1.414, around 85.3% less. A different model can use different tokens and iterations; this does not predict completion, quality or actual future cost.

These are **inferences**, subject to comparison on saved captures and Product evidence cases:

1. Use **GPT-6.1 Sol** for fresh walkthrough authoring and independent photo review. It fits the existing Responses/image/tool shape and costs 80% less for ordinary input/output and 90% less for cache hits than Astra at the stated rates. The initial recommendation was medium reasoning with a bounded Astra escalation after failed visual review; the later authorized implementation uses high authoring and medium review, without automatic escalation. Preserve the asset validation and independent photo comparison.
2. Use **Gemini 3.8 Flash** for routine interviews, plan actions and language edits, escalating difficult or repeatedly invalid plans to Pro. Preserve Python's authoritative geometry, budget and Product-evidence checks. At the current promotional rate, Flash's input/output prices are 62.5%/68.75% below Pro's ≤200k tier. Revisit economics before the announced January increase.
3. Evaluate **Gemini 3.1 Flash-Lite** first for Product fact extraction and simple scoring; compare 3.5 Flash-Lite if quality is insufficient. Relative to current 3.8 Flash, 3.1 Lite is 66.7% cheaper on input and 60% on output. Evaluate correlated variant identity, dimensions and evidence quotations, not merely JSON validity. GPT-6 Luna is a cheap alternative where a provider adapter change is acceptable; it is not established as a reconstruction replacement.
4. Keep **Perceptron Mk1.5** unless measurements show perception dominates cost. Prefer fewer useful detection frames and deduplication while preserving coverage. Its low rates make the Astra authoring loop the more immediate target in the inspected run.
5. For optional photographs, try **GPT Image 2 medium**, retaining high as an explicit final-quality choice. The documented output estimate drops about 75%; evaluate preservation of the Room and selected Products. The fresh Three.js walkthrough does not require purchasing an image on every authoring turn.

Add end-to-end accounting by Room/operation/model/stage before promising a cost per successful design. Bound iteration/review/retry counts and repeated history, retain paid checkpoints and cache-friendly prompt prefixes, and measure quality plus completed-room cost. A cheaper failed model can consume more total money through repair loops. No changes or paid comparison calls were made by this research.

## Authorized walkthrough change and prediction (2026-10-25)

**Confirmed — implementation:** The user initially authorized GPT-6.1 Sol with
medium reasoning for walkthrough modeling and independent review. A later
modeling-only instruction raises authoring to high; independent review remains
medium. Both requests use Sol 6.1. Native generation metadata identifies Sol 6.1; the iOS result
reader recognizes it. Type checking, source-photo texture requirements, native
asset export/integrity checks, independent visual review, rejection handling and
the shared $10 cap are preserved. Existing Astra/Sol rates and billed entries
remain intact. Other pipelines keep their previous models; no automatic Astra
escalation was added.

**Inferred — prediction using the previous run:** Reprice every recorded response
with the new model's rates, preserving its input/cache/write/output quantities,
long-context rules and per-call rounding. The existing ledger is read only.

| Stage | Calls | Previous recorded USD | Predicted Sol 6.1 USD |
| --- | ---: | ---: | ---: |
| Modeling | 83 | 9.019554 | 1.290799 |
| Independent review | 2 | 0.615760 | 0.123152 |
| Total | 85 | 9.635314 | 1.413951 |

This predicts **$8.221363 less, or 85.33% savings**, for the same usage.
High and medium use the same token prices. The original Astra run used high
reasoning, so the same-usage $1.413951 estimate remains the comparison baseline.
No Sol medium or high comparison run has been measured. Each additional 10,000
billed output tokens costs $0.10 at the stated short-context rate, plus any
additional input/context charges; changed reasoning and repair counts can change
the final cost.
The retained run had no successful submission, so this is a prediction for the
same amount of work, not a measured cost per completed Room. No paid comparison
generation was started to make this estimate.


## Full-pipeline planning scenario (2026-10-25)

**Inferred — illustrative workload, not a measured successful-room average:**
The following adds planning, shopping, placement and three edits to the
same-work walkthrough estimate above. It assumes all calls complete without
retries or model escalation. Output quantities include thinking. No Gemini
cache discount is assumed; each modeled request stays within its stated
short-context price tier.

| Stage | Assumed total tokens (input / output) | Proposed routing USD | Other models unchanged USD |
| --- | --- | ---: | ---: |
| Walkthrough | Same usage as the retained 85-call run | 1.413951 | 1.413951 |
| Extract 150 merchant pages | 3,750,000 / 120,000 | 1.117500 | 3.262500 |
| Score 150 choices | 150,000 / 30,000 | 0.082500 | 0.225000 |
| Interview/planning loop | 200,000 / 20,000 | 0.225000 | 0.640000 |
| Spatial plan/repair | 40,000 / 8,000 | 0.060000 | 0.176000 |
| Three language edits, combined | 30,000 / 6,000 | 0.045000 | 0.132000 |
| Perceptron, 30 frames | 60,000 / 15,000 | 0.031500 | 0.031500 |
| Model total | | **2.975451** | **5.881451** |

The proposed profile uses Flash-Lite 3.1 for extraction/scoring and Flash 3.8
for interview, spatial planning and edits; Perceptron remains unchanged. The
comparison uses documented Pro 3.1 interview/Flash 3.8 Product test settings,
and **assumes Pro for spatial/edits because their actual deployment IDs are
unknown**. Both columns retain the authorized Sol 6.1 walkthrough. Token prices
come from the official model pricing sources above. Spatial constraints and
Python placement remain subject to their existing validation.

Page extraction assumes 25,000 input tokens and 800 output tokens per merchant
page, including its text, structured evidence and prompt share. Each score
assumes 1,000 input/200 output tokens. These represent 150 pages/choices across
the discovered pool, not a three-Product shortlist. The code supplies several
potentially large page fields and can visit several merchant URLs for one
candidate; actual input can exceed these assumptions substantially.

**Confirmed — search pricing:** [SerpApi's current plans](https://serpapi.com/pricing)
include $25/1,000, $75/5,000 and $150/15,000 successful searches per month.
At full utilization these imply $0.025/$0.015/$0.01 per successful credit.
They are subscriptions, not purely metered per-call charges; underutilization
increases effective cost. **Inferred:** 100 successful shopping and merchant
resolution requests add $1.00–$2.50, putting this scenario at **$3.98–$5.48**
with proposed routing, or **$6.88–$8.38** with other models unchanged.

A fresh redesign of an already processed Room can omit the modeled walkthrough
and perception, giving **$2.53–$4.03** for the same new search/planning workload
plus three edits under the proposed routing. Reusing valid Product evidence can
reduce that amount; renewed broad discovery can restore it. A geometry-only
language edit with no new discovery, using 10,000 input/2,000 output Flash tokens,
is about **$0.015** in model charges, before any repair or follow-up calls.

These are planning figures, **not a production cost ceiling**. Discovery has no
production candidate-count cap. Six hundred merchant pages at 50,000 input and
1,500 output tokens alone cost $8.85 on Flash-Lite, before scoring, searches,
walkthrough, planning or repairs. Failed authoring can spend the retained $10
walkthrough budget without publishing a Room. Excluded: optional generated
photographs, browser/compute hosting, storage, egress and taxes. No runtime or
model configuration was changed to produce this scenario.
