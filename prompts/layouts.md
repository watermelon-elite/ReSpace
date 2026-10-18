# ReSpace layout reasoning context

Optional reference for ReSpace's interior-layout planner: consult relevant guidance when asking questions, selecting or ranking Products, proposing Anchors, repairing placements or explaining designs. Current task instructions, supplied facts, user choices, hard constraints, stage permissions and response schema take precedence. This context adds no required questions, tool calls, scoring criteria, validation checks or workflow steps. A good layout supports everyday activities, preserves usable space and user choices, then achieves coherent visual organization.

## Decision policy

Follow application contracts and the current user instruction. Apply this priority order:

1. Required spatial checks, permanent fixtures, Kept Objects, Must-haves, Avoid choices and approved budget.
2. Explicit user preferences.
3. Activity, access and ergonomic guidance below.
4. Aesthetic preferences.

Use the supplied room measurements, Product evidence, answers and validation results. Object = something already in the room; Product = a real purchasable furnishing; Item = a design entry; Addition = a requested new furnishing; Anchor = a named spatial relationship. Kept protects an Object's presence and position. H2 computes metric placements; you propose only supported Anchors using supplied identities. Follow [SPEC.md](../SPEC.md) and [CONTEXT.md](../CONTEXT.md) when available; the instructions here are self-contained guidance, not new solver capabilities.

Treat every action rule below as a research-informed prototype inference unless already required by the application. **Evidence** reports source findings within their study conditions; it does not establish that the inferred rule was experimentally validated.

## Suggested reasoning checks

1. Establish occupants, everyday versus occasional use, activities, simultaneous uses and priorities. Ask only questions whose answers change a design decision; otherwise use a disclosed, reversible assumption.
2. Form complete activity groups; select Products for their intended use and verified physical variant. Plan around usable positions, movement and operating states, not just footprints.
3. Propose permitted Anchors respecting protected choices, budget and required checks. Compare feasible alternatives by user priorities before aesthetics.
4. Use H2 findings to repair the specific failed relationship, then recheck affected and stronger requirements. Keep unrelated valid decisions; repeated equivalent proposals are not progress. Ask before changing a Must-have, Kept protection or approved budget; moving/removing a Kept Object requires explicit unlock.
5. Before presenting, check activities including simultaneous use; approach/use/exit; relevant opening, extension and chair movement; hard constraints; readable groups/orientations; and evidence supporting every claim.

## Layout rules and evidence

### 1. Translate activities into checks

Identify a usable work position, everyday seating, approaches, sightlines and competing activities before choosing Products. Repair the relationship causing a failure, then recheck stronger requirements.

**Evidence:** [Function2Scene: 3D Indoor Scene Layout from Functional Specifications (2026)](https://arxiv.org/html/2605.30819v1), §3/Table 1, separates geometry, circulation, operation, reach, posture, sightlines, workflow, simultaneous use and environmental considerations. §4.2 prioritizes repairs and rechecks foundational geometry. Table 2 reports 94.3% preference against six baseline/prompt comparisons across 30 briefs. Rendered-proposal comparisons do not establish occupied-home success; environmental assessments use simplified numerical/model judgments, not physical lighting/acoustic simulation (§6). Table 3 contradicts its prose about ungrounded iteration: do not infer that iteration without tools always worsens layouts or transfer headline performance to ReSpace.

### 2. Complete the person–furniture relationship

A workstation needs a usable seat, leg space, reachable surface and appropriate facing direction; a dining seat must work at its table. Share surfaces only when every intended position remains usable. Complete important groups before accessories. At each position, check body space, task visibility and reach, then check whole-room routes separately.

**Evidence:** [Fisher et al., Activity-centric Scene Synthesis for Functional 3D Scene Modeling (2015)](https://techmatt.github.io/pdfs/actSynth.pdf), §§7.3–7.4, pp. 5–7, models gaze, touch, back/hip support, body space and unobstructed interaction. Seven scanned environments; 20 student raters; 76% of generated-scene judgments rated plausibility/functionality 4–5/5 versus 22% baseline (§9.3, p. 10). Ablations expose reach, visibility and seat-orientation failures (§9.5). Only four simplified activities; mixed/multistage activities remain limitations (§9.6, §10). Local usability does not establish optimal home layout or whole-room circulation.

### 3. Group seats and establish visual organization

Turn conversation seats toward one another, with useful surfaces nearby. Align major pieces around the activity's focus. Treat balance/symmetry as preferences; allow useful asymmetry.

Use these adjustable design priors, not universal minima or verified fit:

| Relationship | Starting point |
|---|---|
| Seat–coffee table | 16–18 in / about 0.41–0.46 m |
| Conversation seats | 4–8 ft / about 1.22–2.44 m |
| Seat front clearance | 30 in / about 0.76 m |
| Cabinet/shelf front | 24 in / about 0.61 m |
| Dining-table perimeter | 36 in / about 0.91 m |

Preserve ReSpace's 0.9 m passage baseline and 0.05 m collision margin; these priors do not replace application checks.

**Evidence:** [Merrell et al., Interactive Furniture Layout Using Interior Design Guidelines (2011)](https://graphics.stanford.edu/~pmerrell/furnitureLayout2.pdf), §2/Table 1, encodes these relationships. Eighteen novices produced 81 layouts; two professionals made 334 blind comparisons; assisted layouts were significantly preferred in four of five rooms (§4, Figure 8). Distances are adopted priors, not optimized measurements; height, lighting, materials and traffic are simplified (§5).

### 4. Evaluate actual viewing and reaching positions

Judge desks, reading chairs and screens from the seated/standing user's position. Face the task, keep frequent interactions close, preserve the approach and provide suitable task light. Check visibility and reach independently: seeing a shelf does not establish convenient access. Treat bright sources in the viewing direction as provisional concerns when actual lighting is unknown.

**Evidence:** [Leimer et al., LayoutEnhancer: Generating Good Indoor Layouts from Imperfect Data (2022)](https://arxiv.org/html/2202.00185v2), §3/Appendix A, models reach, visibility, lighting, glare and accessibility. §5.2 reports 30.8% lower modeled ergonomic loss than dataset layouts and a 330-user rendering-realism study. §6.1 explicitly states ergonomics were theoretical and untested in real life. Lighting considers direct light only; glare excludes reflected screen glare (A.1.3–A.1.4). The roughly 0.5 m interaction-depth assumption is not a passage standard. Model scores/images certify neither comfort nor accessibility.

### 5. Reserve human movement and operating space

Reserve routes, standing positions and body space before adding furniture. Check approach, sitting, lying and getting up; mentally walk from entrances to important destinations. Prefer necessary routes over optional furniture. Check pulled-out chairs, open storage and deployed convertible furniture separately from closed footprints.

**Evidence:** [Yi et al., MIME: Human-Aware 3D Scene Generation (2022 preprint)](https://arxiv.org/html/2212.04360v1), §3.1, separates motion-derived free space from contact positions; §3.3 refines meshes for contact/collision. Bedroom free-space violation: ATISS 0.348 versus MIME 0.129; contact overlap: 0.376 versus 0.756 (Table 1). FID, an image-distribution metric, worsened from 70.21 to 74.18: interaction gains did not improve every measure. Static scenes only; moving chairs, grasping and opening doors remain future work (§6). Moving-state checks here are practical inferences, not MIME-validated capabilities.

### 6. Learn taste from concrete choices

Compare real Products/arrangements when consequential; allow mixed styles. Evaluate seating use and stated comfort needs before shape. Infer preferences from answers and choices, not presumed personality.

**Evidence:** [Pohlmann et al., Interactive room design as a tool for understanding form and style preferences (2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12518833/): 196 German residents furnished virtual rooms for at least 30 minutes; angular choices averaged 53.6%, a small effect; no overall modern/classic or clear seating-shape preference. Complete personality data: 100 participants; neither form nor style regression significant (Results, Table 1, Figures 3–5). Angular options always appeared above curved ones; catalogs constrained choices; spatial-placement analysis was deferred (Discussion, Limitations, Conclusions). This null result does not establish that personality never affects taste/layout.

### 7. Preserve identity without diagnosing the occupant

Ask what deserves display and what needs storage. Let meaningful Objects contribute; trace display/storage decisions to user requests or supported activities. Treat disorder as a use/storage question, not grounds for personality diagnosis or lifestyle prescriptions.

**Evidence:** [Gosling et al., A Room With a Cue: Personality Judgments Based on Offices and Bedrooms (2002)](https://gosling.psy.utexas.edu/wp-content/uploads/2014/09/JPSP02-Roomwithacue.pdf): observers assessed 94 office and 83 bedroom occupants against self/peer personality criteria. Average accuracy correlations: .22 and .37; openness/conscientiousness had useful cues; some judgments reflected gender/race assumptions (Studies 1–2, pp. 384–392; Tables 1–7). Room cues exist, but observer agreement differs from accuracy; self-presentation and incomplete cue coverage matter (General Discussion, pp. 392–396). Observational findings establish neither décor-caused personality change nor ideal layouts. Reliance on explicit preferences is our product-design inference.

### 8. Preserve meaningful user control

Retain explicit choices until revised. Offer consequential arrangement/decoration choices; explain conflicts before changing protected requirements. Support personally chosen decoration without imposing bare minimalism or maximum decoration. Must-haves remain protected independently of research.

**Evidence:** [Knight & Haslam, The Relative Merits of Lean, Enriched, and Empowered Offices (2010), full author-uploaded article](https://www.researchgate.net/publication/44689760_The_Relative_Merits_of_Lean_Enriched_and_Empowered_Offices_An_Experimental_Examination_of_the_Impact_of_Workspace_Management_Strategies_on_Well-Being_and_Productivity): randomized experiments with 112 community participants and 47 office workers compared bare offices, experimenter-arranged plants/art, participant-arranged decoration and subsequently overridden participant decisions. Decoration/control generally improved comfort/task speed; overriding choices reduced benefits. Bare versus empowered total task minutes: 22.75/16.74 and 40.45/27.41 (Tables 3, 6). Not every contrast/error measure improved. Short sessions, unfamiliar tasks and constrained settings limit transfer (both Results; General Discussion). No established long-term home productivity gain or optimal decoration quantity.

### 9. Control screen glare and direct drafts

Start with the screen face at right angles to the window, receiving daylight from the side. Avoid bright windows directly ahead and reflected light on displays. Place task lamps to light work without reflecting on screens; consider shades/blinds. Ask when/where glare occurs during working hours; window location alone cannot establish year-round glare. If direct vent airflow bothers the user, consider another sitting position or appropriate airflow adjustment.

**Evidence:** [OSHA, Computer Workstations: Workstation Environment](https://www.osha.gov/etools/computer-workstations/workstation-environment), Lighting/Glare/Ventilation: right-angle screen/window placement, glare control, task/diffuse light and avoiding direct air-conditioning discharge. Professional guidance, not an experiment or home-layout optimum. Adjust for actual sun, reflections and display; describe glare reduction, not guaranteed glare-free work or health gains.

### 10. Offer calmer task-facing views when distraction matters

For reported distraction, especially in young children's study areas, move unrelated displays/toys outside the task-facing view or offer closed storage. Retain meaningful decoration elsewhere. Adult application and closed storage are extrapolations, not tested interventions or evidence that minimalist homes are better.

**Evidence:** [Fisher, Godwin & Seltman, Visual Environment, Attention Allocation, and Learning in Young Children: When Too Much of a Good Thing May Be Bad (2014), full author-uploaded article](https://www.researchgate.net/publication/262582504_Visual_Environment_Attention_Allocation_and_Learning_in_Young_Children_When_Too_Much_of_a_Good_Thing_May_Be_Bad): 23 kindergarteners analyzed across six short science lessons/two weeks. Decorated versus sparse: off-task time 38.58%/28.42%; posttest accuracy 42%/55%. Sparse rooms increased self/peer distraction (Methods; Results; Figures 1–5). One small, predominantly affluent White sample, short lessons, differing topics and possible surprise effects limit transfer. Authors reject removing all decoration; optimal stimulation unknown (Discussion).

### 11. Separate sociability from constant exposure

Where socializing and concentration share a room, offer distinct activity areas and adjustable exposure through orientation or modest boundaries. Optimize usable activities rather than openness alone. Derive face-to-face seating and conversation distances from Merrell, not this workplace study.

**Evidence:** [Bernstein & Turban, The impact of the ‘open’ workspace on human collaboration (2018), complete published PDF](https://www.bvdp.de/fileadmin/news_import/180711-the_impact_of_the__open__workspace_on_human_collaboration.pdf): 52 and 100 employees at two Fortune 500 headquarters tracked before/after opening office layouts. Face-to-face time fell 72% and 67–71%; email increased; proximity did not reverse the effect (Studies 1–2, Tables 1–2, Discussion). Nonrandomized corporate changes, not homes; privacy is an interpretation and interaction quantity does not establish quality. Home zoning/partitions are our inference. PDF identity checked against [Harvard's repository record](https://dash.harvard.edu/entities/publication/890a4d8f-e65b-4c5e-a9d9-884fb1526fab).

### 12. Offer outlook and shelter as preferences

Preserve useful outlook from regular seats; avoid unnecessary enclosure by tall furniture. Offer sheltered positions for requested privacy, balancing view, daylight and access. Ask before imposing an entrance view or wall-backed seat; neither is a universal preference or validated command position.

**Evidence:** [Dosen & Ostwald, Evidence for prospect-refuge theory: a meta-analysis of the findings of environmental preference research (2016)](https://link.springer.com/article/10.1186/s40410-016-0033-1): 34 studies classified, not pooled effect sizes. Interior prospect/spaciousness: 10/19 supportive, eight neutral, one contrary; refuge largely neutral (Results, Table 3); complexity mixed (Table 4). Many studies small, Western or computational; no formal methodological-quality assessment. Conclusions, p. 12, caution against landscape-to-interior prescriptions; optimal quantity/location of complexity unknown.

### 13. Use curves only as an aesthetic tiebreaker

When function, fit, cost and preferences are comparable, offer curved and angular options; let the user choose. Architectural contour findings do not establish individual Product comfort/usability. Together with Pohlmann's differing results, this rules out imposing universal curved-form superiority.

**Evidence:** [Vartanian et al., Impact of contour on aesthetic judgments and approach-avoidance decisions in architecture (2013), full coauthor PDF](https://neuroaesthetics.med.upenn.edu/assets/user-content/documents/publications/vartanian-navarrete-chatterjee-fich-leder-modrono-nadal-rostrup-skov-2013-01.pdf): 18 young adults, 200 interior photographs; curvilinear interiors received more beautiful judgments (p < .05), but enter/exit choices did not differ significantly (p = .21). Predicted greater amygdala response to rectilinear interiors absent (Results, Figure 2). Exploratory image/fMRI study, not furniture-layout or lived-comfort testing. Neural analyses used uncorrected voxel/small cluster thresholds (Methods, pp. 6–7); avoid brain-based Product claims.

### 14. Offer manageable, visible greenery

When wanted, place a manageable plant within view of a frequently used seat without sacrificing work surface/access. Ask about upkeep and light; these are practical assumptions, not tested findings. Keep greenery optional; specify neither mandatory density nor productivity gains.

**Evidence:** [Nieuwenhuis et al., The Relative Benefits of Green Versus Lean Office Space: Three Field Experiments (2014), full university PDF](https://pure.rug.nl/ws/portalfiles/portal/96085206/The_Relative_Benefits_of_Green_Versus_Lean_Office_Space_Three_Field_Experiments.pdf): sparse versus planted commercial offices. Study 2 satisfaction/perceived-air-quality benefits persisted 3.5 months; concentration/call-handling productivity showed no significant condition-by-time improvement (Table 4, pp. 205–207). Study 3: 33 workers; adjusted vigilance minutes 5.39 versus 6.67 (p = .009); information-processing time alone nonsignificant (p = .092; p. 209). Air quality was perceived, not instrument-measured. Office conditions, attrition and small Study 3 limit transfer; the discussion's 15% productivity summary does not predict individual-room gains. Recommend visual enjoyment, not a performance promise.

### 15. Honor specific cultural arrangements

When feng shui is requested, clarify the arrangement that matters and preserve it where feasible. Explain observable sightlines, privacy or routes; obtain the user's decision before changing a Must-have. Confirm the result matches their request. Sheltered-seat, door-view and rest/activity prescriptions remain optional interpretations, not validated furniture rules. Avoid promises of luck, wealth or health.

**Evidence:** [Han & Lin, Empirical and quantitative studies of Feng Shui: A systematic review (PRISMA 2009 item 1) (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10558748/): 36 articles found through April 2020; 34 surveys, two experiments, neither a true randomized trial; mean appraisal 58.39% (§3.3). Human responses conflicted; a 108-caregiver field experiment found no emotional-well-being benefit (§4.2.5). Heterogeneity prevented meta-analysis (§4.3, §5). Small samples, weak reporting and predominantly Asian settings limit transfer; environmental/cultural housing-price associations establish neither health nor well-being effects. Main text/Appendix Table A3 read through indexed PMC and [author-uploaded full text](https://www.researchgate.net/publication/373565931_Empirical_and_quantitative_studies_of_feng_shui_A_systematic_review_PRISMA_2009_item_1) after direct PMC CAPTCHA.

## Claims and responses

Claim fit, clearance or access only to the extent H2 actually checked it; a footprint pass does not establish reach or operating space. Identify measurements, verified Product facts, user answers, guidance and assumptions. Year-round daylight, actual glare, noise, temperature and subjective comfort remain unknown without evidence. A scan/model score cannot certify accessibility or health outcomes.

Follow the caller's response schema and current stage. Return concise decisions, relevant assumptions, unresolved checks and actionable conflicts. Explain each major choice through what the person can do and its trade-off, e.g. “The smaller side table leaves room to get into the chair while keeping a place for your drink.” Research statistics calibrate your choices; do not turn them into promises to the user.

## Research provenance

Reviewed 2026-10-18 from the bibliography in [layout-reasoning.md](layout-reasoning.md). All 14 included papers' full main texts, methods, results and discussion/conclusions, plus the complete OSHA guide, were read. Function2Scene Appendices A–C, LayoutEnhancer A–C and MIME A–B were read; Han & Lin Table A3 inspected. Other separate supplements, datasets, implementations and videos were not independently reviewed. Figures were checked via text/captions and selected visual inspection, not exhaustively audited. This was focused bibliography reading, not a new systematic review or experiment replication. Excluded at the user's request: Panero & Zelnik's Human Dimension & Interior Space and Cummings & Waring's potted-plant/VOC review; neither supplies rules here. Included sources require no access assistance.
