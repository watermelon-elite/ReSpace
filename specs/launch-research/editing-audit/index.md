# Editing-specific reanalysis: evidence and corrections

Companion to the [video-editing style profile](../video-editing-style-profile.md). Research date: 18 October 2026.

## Scope

The existing [deep index](../deep/index.md) records prior full-film audiovisual coverage for all 20 selected references. This pass revisited those editorial reports and added **21 successful focused clip audits across 14 films at 8 fps**, using the watch-video skill and `gemini-3.5-flash-lite`. Six API attempts returned temporary 503 errors; subsequent focused calls succeeded where recorded below. Some public hosted sources could not be retrieved again; those entries remain explicitly prior-evidence-based.

This is sampled audiovisual inspection, plus direct viewing of extracted frames for selected details. It is not a human real-time screening or a frame-accurate edit list. A successful call does not guarantee the model returned useful sound analysis; missing audio detail is not filled in. Three research agents covered complementary groups, then cross-reviewed the drafts; a synthesis pass checked distinctions, links and wording.

## Fresh clip records

Requested ranges are requests, not asserted exact source cut boundaries. Reports preserve returned navigation timestamps, with quotation redactions disclosed at the top where applied. Read the correction register before using raw wording.

| Film | Requested source interval | Status | Report / log |
|---|---|---|---|
| 01 Pinterest Disco Treehouse | 0:05-0:29 | complete | [Report](rank-01-clip-1.txt) · [Log](rank-01-clip-1.log) |
| 02 reMarkable | 1:39-2:23 | complete | [Report](rank-02-clip-1.txt) · [Log](rank-02-clip-1.log) |
| 02 reMarkable | 2:02-2:17 | complete | [Report](rank-02-clip-2.txt) · [Log](rank-02-clip-2.log) |
| 03 Wispr | 0:00-0:21 | complete | [Report](rank-03-clip-1.txt) · [Log](rank-03-clip-1.log) |
| 04 Descript | 1:15-1:40 | success; terse observations | [Report](rank-04-clip-1.txt) · [Log](rank-04-clip-1.log) |
| 04 Descript | 1:50-2:05 | success; terse detailed visual bullets | [Report](rank-04-clip-2.txt) · [Log](rank-04-clip-2.log) |
| 07 Slack | 0:25-0:49 | complete | [Report](rank-07-clip-1.txt) · [Log](rank-07-clip-1.log) |
| 08 IKEA Make Room for Life | 0:10-0:23 | success | [Report](rank-08-clip-1.txt) · [Log](rank-08-clip-1.log) |
| 08 IKEA Make Room for Life | 0:58-1:20 | failed | [Log](rank-08-clip-2.log) |
| 08 IKEA Make Room for Life | 0:58-1:05 | success | [Report](rank-08-clip-3.txt) · [Log](rank-08-clip-3.log) |
| 08 IKEA Make Room for Life | 1:19-1:29 | success | [Report](rank-08-clip-4.txt) · [Log](rank-08-clip-4.log) |
| 09 Dollar Shave Club | 0:44-1:22 | failed: HTTP503 temporary high demand; later retry clip-2 succeeded | [Log](rank-09-clip-1.log) |
| 09 Dollar Shave Club | 0:44-1:22 | complete | [Report](rank-09-clip-2.txt) · [Log](rank-09-clip-2.log) |
| 10 Notion Mail | 0:00-0:26 | failed503; sandbox DNS attempt preceded escalation | [Log](rank-10-clip-1.log) |
| 10 Notion Mail | 0:00-0:20 | success; one shorter retry | [Report](rank-10-clip-2.txt) · [Log](rank-10-clip-2.log) |
| 12 Sonos | source offset 15s; excerpt 35s | 503 | [Log](rank-12-clip-1-retry.log) |
| 12 Sonos | source offset 15s; excerpt 35s | 503 | [Log](rank-12-clip-1.log) |
| 12 Sonos | source offset 18s; excerpt 15s | success | [Report](rank-12-clip-2.txt) · [Log](rank-12-clip-2.log) |
| 13 Daylight | 0:00-0:15 | success | [Report](rank-13-clip-1.txt) · [Log](rank-13-clip-1.log) |
| 13 Daylight | 1:06-1:28 | success | [Report](rank-13-clip-2.txt) · [Log](rank-13-clip-2.log) |
| 14 Playdate | 0:18-0:46 | failed503 | [Log](rank-14-clip-1.log) |
| 14 Playdate | 0:28-0:45 | success; one shorter retry | [Report](rank-14-clip-2.txt) · [Log](rank-14-clip-2.log) |
| 16 Headspace | 0:00-0:25 | success | [Report](rank-16-clip-1.txt) · [Log](rank-16-clip-1.log) |
| 16 Headspace | 0:55-1:20 | success | [Report](rank-16-clip-2.txt) · [Log](rank-16-clip-2.log) |
| 19 IKEA Place | 0:00-0:18 | success | [Report](rank-19-clip-1.txt) · [Log](rank-19-clip-1.log) |
| 19 IKEA Place | 0:39-0:59 | success | [Report](rank-19-clip-2.txt) · [Log](rank-19-clip-2.log) |
| 20 Notion AI | 0:00-0:21 | success | [Report](rank-20-clip-1.txt) · [Log](rank-20-clip-1.log) |

## Direct frame checks

- **Descript:** [visual check](rank-04-visual-crosscheck.txt), [2fps strike-through sequence](rank-04-strikes-contact-sheet.jpg). Confirms graphic strikes continuing as rotated typography over the actor. Does not establish exact contact frames or isolated sound accents.
- **Sonos:** [visual check](rank-12-visual-recheck.md), [whole-film sheet](rank-12-contact-sheet.jpg), [denser setup sheet](rank-12-setup-contact-sheet.jpg). Confirms opening branding, daylight exterior and a setup relay across households. The successful fresh API report omitted audio detail.
- **Daylight:** [visual check](rank-13-visual-recheck.md), [1fps comparison sheet](rank-13-comparison-contact-sheet.jpg). Confirms two readers sharing the sofa and recurring text over sensory close-ups. Does not support a vertically scrolling multi-line text stack.

## Coverage by film

Every reference retains its previous full-film review. “Fresh” below means focused excerpts only, not a second complete analysis of the entire film.

| Film | This pass | Prior review and source/version record |
|---|---|---|
| 01 Pinterest Disco Treehouse | 1 successful focused audit | [Editorial review](../deep/rank-01-pinterest-disco-treehouse/report.md) · [Coverage](../deep/rank-01-pinterest-disco-treehouse/coverage.json) |
| 02 reMarkable | 2 successful focused audits | [Editorial review](../deep/rank-02-remarkable-get-your-brain-back/report.md) · [Coverage](../deep/rank-02-remarkable-get-your-brain-back/coverage.json) |
| 03 Wispr | 1 successful focused audit | [Editorial review](../deep/rank-03-wispr-break-up-keyboard/report.md) · [Coverage](../deep/rank-03-wispr-break-up-keyboard/coverage.json) |
| 04 Descript | 2 successful focused audits; direct frame check | [Editorial review](../deep/rank-04-descript/report.md) · [Coverage](../deep/rank-04-descript/coverage.json) |
| 05 HomePod | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-05-homepod/report.md) · [Coverage](../deep/rank-05-homepod/coverage.json) |
| 06 IKEA Kreativ | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-06-ikea-kreativ/report.md) · [Coverage](../deep/rank-06-ikea-kreativ/coverage.json) |
| 07 Slack | 1 successful focused audit | [Editorial review](../deep/rank-07-slack-so-yeah/report.md) · [Coverage](../deep/rank-07-slack-so-yeah/coverage.json) |
| 08 IKEA Make Room for Life | 3 successful focused audits | [Editorial review](../deep/rank-08-ikea-make-room/report.md) · [Coverage](../deep/rank-08-ikea-make-room/coverage.json) |
| 09 Dollar Shave Club | 1 successful focused audit | [Editorial review](../deep/rank-09-dollar-shave-club/report.md) · [Coverage](../deep/rank-09-dollar-shave-club/coverage.json) |
| 10 Notion Mail | 1 successful focused audit | [Editorial review](../deep/rank-10-notion-mail/report.md) · [Coverage](../deep/rank-10-notion-mail/coverage.json) |
| 11 Tylko Bedroom | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-11-tylko/report.md) · [Coverage](../deep/rank-11-tylko/coverage.json) |
| 12 Sonos | 1 successful focused audit; direct frame check | [Editorial review](../deep/rank-12-sonos/report.md) · [Coverage](../deep/rank-12-sonos/coverage.json) |
| 13 Daylight | 2 successful focused audits; direct frame check | [Editorial review](../deep/rank-13-daylight/report.md) · [Coverage](../deep/rank-13-daylight/coverage.json) |
| 14 Playdate | 1 successful focused audit | [Editorial review](../deep/rank-14-playdate/report.md) · [Coverage](../deep/rank-14-playdate/coverage.json) |
| 15 Dropbox | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-15-dropbox/report.md) · [Coverage](../deep/rank-15-dropbox/coverage.json) |
| 16 Headspace | 2 successful focused audits | [Editorial review](../deep/rank-16-headspace/report.md) · [Coverage](../deep/rank-16-headspace/coverage.json) |
| 17 Granola | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-17-granola/report.md) · [Coverage](../deep/rank-17-granola/coverage.json) |
| 18 Floyd | Prior full-film AV; fresh public-source retrieval unavailable | [Editorial review](../deep/rank-18-floyd/report.md) · [Coverage](../deep/rank-18-floyd/coverage.json) |
| 19 IKEA Place | 2 successful focused audits | [Editorial review](../deep/rank-19-ikea-place/report.md) · [Coverage](../deep/rank-19-ikea-place/coverage.json) |
| 20 Notion AI | 1 successful focused audit | [Editorial review](../deep/rank-20-notion-ai/report.md) · [Coverage](../deep/rank-20-notion-ai/coverage.json) |

## Correction register

These corrections govern the profile. Raw reports remain evidence of what the analysis returned, not unquestioned factual descriptions.

| Source / issue | Treatment in the profile |
|---|---|
| Pinterest: focused pass omits audio; paths and direction vary between reports | Sound remains attributed to prior AV. Surface-following motion is retained; an exact universal wipe direction or literal card-to-object trajectory is not asserted. |
| reMarkable: first recheck compresses eye-to-product sequence and disagrees on live-action boundary | Shorter second recheck distinguishes eye, pupil, abstract texture, drawn eye, hand/diagram and photographic tablet/table. E008 is a sequence of stages, not one proven seamless morph. E009 concerns the surrounding sensory reset. |
| Wispr: fresh report labels failed typing as speech-to-text | Rejected. Opening depicts typing errors. Oversized keyboard appearance is retained without resolving held-versus-worn prop construction. |
| Slack: earliest branding and card wording | Dedicated identity card is distinct from earlier incidental product presence. Integration logos accompany a continuing interview. A phone/card gag does not prove a practical technique. |
| Dollar Shave Club: apparent route versus one take; time disagreement | Presenter route is editorial structure, not a literal continuous take. Fresh whole-second prop/mascot points disagree with earlier broader ranges; no exact cut boundary is asserted. |
| Descript: exact keyboard key; supposed original chroma-key method | Neither is established. Strike-through graphics over actor are independently visible. Rewind and starfield recipes are proposals. |
| Notion Mail: rule-to-result continuity | The fresh report describes a cut to labeled inbox results. The film does not establish instant uninterrupted processing. Ambiguous cursor hover is not promoted to an app-launch fact. |
| Playdate: interior hardware reveal; exact montage duration | Contradictory descriptions are omitted. Hand/drop and rotational montage retained. A sampled 0.25-second estimate is not treated as measured. |
| HomePod: room first versus table first | Table deformation precedes larger room expansion. Mirror/double and return are retained without claiming original practical/CG technique or a precise invisible cut. Later solo sequence is not called an ensemble. |
| Sonos: dusk opening, unbranded opening, one continuous installation | Direct frames show daylight and opening brandmarks. Setup crosses households. Fresh report’s inferred family relationship and phone-screen hard cut are not adopted. |
| IKEA Make Room for Life: hush, silence and music drop | Dedicated previous 10 fps check and new 8 fps check support continuous music. Hush-to-dance is visual counterpoint. Ending scale progression is supported; a continuous window-crossing camera shot is not established. |
| Daylight: graphic match labels and sliding text stack | Macro-to-portrait can simply be a cut. Shared sofa comparison and recurring text treatment are visible; stack animation is not confirmed. Display/health claims remain advertising claims, not validated findings. |
| Headspace: stressed central character; mind character called brand logo | Opening central character is calm amidst surrounding pressure. Personified mind is a concept character. Park-to-circle close is retained; exact easing and first closing frame are not measured. |
| Floyd: ReSpace identity, customer testimonials, impossible needle timestamp | Film is Floyd; visible identifiers establish founders, not verified customer testimonials. Needle sequence belongs around01:36.667–01:38.000. Visible record action does not prove a soundtrack-start handoff. |
| IKEA Place: immediate UI-to-real-room match and exactly aligned device match cuts | Ending is a delayed bookend. Repeated handheld-device framing is not proven pixel-aligned. Original practical/CG method is unknown. |
| Notion AI: cursor direction and desktop-to-phone morph | Direction conflict omitted. Tall mobile stage is a composition reset, not a proven hardware morph or elaborate VFX. |

## Timestamp interpretation

The new Sonos file was physically excerpted from source 18–33 seconds. Its returned 00:00–00:15 values are clip-relative; add 18 seconds only when locating the original source. Entries preserve the returned values or pair them with the prior source navigation range and disclose the offset.

Several direct YouTube clips—especially IKEA Make Room, Headspace and IKEA Place—say “clip-relative” while returning values in the original source interval, sometimes larger than the entire clip duration. This is an internal model inconsistency. The profile retains those returned values as approximate source navigation and does **not** mechanically add the request start. Use visible scene content and the linked prior review to locate the edit, then mark exact in/out frames in editing software.

Daylight was supplied as the original public local file with requested source intervals. Its second report uses source-range values. For all films, three decimal places in a report do not establish millisecond accuracy. No measured average cut duration, BPM alignment or retention effect is claimed.

## Source and reproducibility notes

[Coverage manifest](coverage.json) preserves requests, models, results, retrieval limitations and per-run notes. It includes historical failed calls so failures cannot be mistaken for missing footage analysis. Empty failed-report files are not evidence and are not linked as successful reports above.

The six sources without fresh successful clips are HomePod, IKEA Kreativ, Tylko, Dropbox, Granola and Floyd. Public player access returned 401/403 or did not expose usable media in this pass. Existing full-film coverage was used rather than substituting a different campaign. Tylko’s credited sound-studio source version and HomePod’s selected Vimeo upload retain the version caveats in their original coverage records.

Fresh public Wistia files were recovered for Descript (`2rb6egpph3`) and Daylight (`u8xn64uj9r`); Sonos media was recovered from its public embedded player. Temporary local media are research inputs, not bundled distribution copies. Screenshots are limited analytical contact sheets. Original project files, audio stems and original production methods were unavailable.

Quotation-redacted companions are labeled. Unmodified fresh responses were retained in the temporary research workspace; temporary files are not promised as durable artifacts. Prior deep reports keep their original disclosure conventions. The final library paraphrases mechanisms instead of reproducing dialogue or lyrics.

## Library data

- [80 structured effects](effects.json)
- [32 structured fundamentals](fundamentals.json)
- [Reusable Markdown profile](../video-editing-style-profile.md)

Recreation steps and parameter suggestions are original editorial proposals. They should not be cited as documentation of how a reference production was made.
