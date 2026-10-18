---
status: accepted
---

# Keep walkthrough edits in a persistent three-dimensional scene

ReSpace must provide a realistic explorable room and support Gemini-driven natural-language edits, as requested on October 17, 2026. Store edits against identified room surfaces and objects in a persistent scene so that movement between viewpoints and saved design versions shows the same change; a generated image from one camera is insufficient for this requirement. This commits the pipeline to scene identity, separable assets, and consistent background handling. The rendering representation remains unresolved; the subsequently accepted completion and presentation policy is recorded in ADR-0003.
