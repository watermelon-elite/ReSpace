# ReSpace video smoke tests

Tested 2026-10-18 with Recordly 1.4.0 on macOS and the anonymous FreeMockup editor. This is a preparation experiment, not final footage or a change to the app. No paid features were used. Nothing was imported into Compound or another video editor.

**15 treatments attempted: 10 usable MP4 samples, one reproducible visual failure, and four FreeMockup cases without a verified downloaded file.** “Usable” means a sample suitable for evaluating the treatment, not ready for the launch film. Demo copy, status-bar time, empty regions, and framing still need final-shot preparation.

Open [the playable gallery](index.html), [the contact sheet](contact-sheet.jpg), or [the machine-readable manifest](manifest.json). The gallery uses relative files and works without an account. The manifest records file dimensions, timing and decode checks where available.

## Test catalogue

| Case | Treatment and settings | Result / production lesson |
| --- | --- | --- |
| F01 | Upright 3D phone; landscape Animation 1, gray, 100%; Room screenshot | **Export verified:** 1920×1080, 30fps, 7s. A useful short product-introduction shot. |
| F02 | Dark tilted phone; landscape Animation 2, #111827, 200%; Room screenshot | **Incomplete export:** last observed at 47%. Hidden tabs pause capture; no completed file retained. |
| F03 | 4K portrait reveal; portrait Animation 9, gray, 200%; Rooms screenshot | **Render completed, download unverified:** UI reported 2160×3840, 30fps, 105 frames, 3.5s, 2.5MB. The in-app browser download event timed out. This is not a file-quality or 4K playback pass. |
| F04 | Macro phone; landscape Animation 3, gray, 200%; Room details screenshot | **Preview checked:** strong perspective and cropped edges; suitable for a brief detail insert, not reading the whole screen. No export retained. |
| F05 | Overhead video-textured phone; landscape Animation 4, Pearl gradient; 200% then 50%; 8s navigation video | **Limited preview:** real video imported and mapped onto the phone. Continuous video playback/export remains unverified. The source changes screens at about 5.8s; the fast 5s animation ends too early. The slow preview still showed the initial frame after playback. |
| R01 | Default frame; Tahoe Light wallpaper, 67% shadow, 8% radius, 20% padding, 16:9 | **Export verified:** useful baseline, but the wallpaper competes with the app and the portrait UI is small. |
| R02 | White background, 1.8× manual zoom, default timing/shadow; zoom 0.488–1.488s | **Export verified:** focused movement works. Reduce the default heavy shadow for a cleaner finish. |
| R03 | White background, 1.8× zoom plus blue arrow, annotation 0.5–1.5s | **Export verified:** zoom plus directional callout works on a real navigation recording. |
| R04 | Smooth dark close-up; 1.8×, 650ms in/out, focus (0.5,0.65), #111827, 25% shadow, 10% padding; zoom 0.7–3.3s | **Export verified:** recommended starting point for room inspection. |
| R05 | Snappy punch; 2.2×, 120ms in/out, zoom blur off, #f4efe7; focus (0.5,0.75), zoom 0.6–3s | **Export verified:** aggressively emphasizes the input field and crops the room. Use for a quick beat. |
| R06 | Connected glide; two 1.8× zooms, 0.4–1.4s at (0.5,0.3) and 2.2–3.6s at (0.5,0.75), 700ms bridge | **Export verified:** connected movement works. First target includes empty UI; select meaningful targets for the final shot. |
| R07 | Room details arrow; blue right arrow, 0.5–3.5s, position (50,35), size (16,10), warm background, 25% shadow, 10% padding | **Export verified:** points toward the 40/50 counts while retaining readable screen context. Recommended callout starting point. |
| R08 | “Measured room” text on held Room details | **Visual failure:** output text appears, but the underlying phone becomes uniform gray. Repeated using native Text/Blur controls; unresolved. Keep out of production for now. |
| R09 | Portrait Objects; 9:16, white preview, 5% padding, 25% shadow | **Export verified with caveat:** readable portrait layout. Outer padding exported black despite the white preview; fix/check borders before final use. |
| R10 | Native 2× navigation, dark background, no zoom; 16.208s of source to 8.104s timeline | **Export verified:** about 8.13s at 30fps. Useful for compressing navigation; leave readable holds around decisions. |

## Sources and what was actually tested

`sources/` contains five screenshots of the running ReSpace iPhone Simulator: Rooms, design progress, Room, Room details, and Objects. Not every screenshot became an exported test. `room-details.mov` is a real 27.418s navigation recording, 1206×2622, with variable timing. `room-details-8s.mp4` is a trimmed/normalized input for the browser test.

Files named `*-hold.mp4` are four-second holds made from real screenshots. R07–R09 use those holds; their exports establish framing/annotation behavior, not moving-app playback. R01–R06 and R10 use the real navigation recording. F01–F04 use screenshots; F05 uses video.

FFmpeg was used only for source trimming/normalization, screenshot holds, metadata/decode checks and preview images. All zooms, arrows, framing and 3D phone effects in the samples were rendered by Recordly or FreeMockup. No effects were recreated in another editor. The app's implementation was not changed for these tests.

## Fast repeatable workflow

1. Capture the final actions cleanly on the real iPhone; use Simulator for repeatable saved-room screens. Keep an undecorated master. Prepare demo text and status bars, dismiss keyboards when appropriate, and hold each important state long enough to read.
2. Choose one action per clip. Trim the source so the desired action occurs inside the effect's duration. The 5.8s transition in F05 demonstrates why preset duration and source in-point must be chosen together.
3. In Recordly, import the source, choose aspect ratio and a restrained background, then add manual zoom regions. Start with R04's 1.8× / 650ms movement and a lighter shadow. Use R07-style arrows selectively. Imported iPhone footage does not supply mouse tracking; automatic cursor zoom was not validated here.
4. In FreeMockup, import a screenshot for the most predictable hero shot, choose a free iPhone preset and baked background, and test HD first. Keep the exporting tab visible. Verify the downloaded file before investing in a series. Moving-video synchronization, 4K download reliability, transparency and multi-device composition were not established by this run.
5. Review each resulting file at delivery size: readable UI, correct crop, clean beginning/end, actual screen changes, matching background and no unexpected gray/black frames. Once the visual language is approved, record final screens and repeat only the chosen treatments.

For the eventual film, use flat/near-flat screen close-ups for explanation, brief 3D phone shots for introduction/reveal, and one consistent background/shadow system. This is an editorial recommendation from these samples, not a completed final edit.

## Recordly projects and export behavior

`projects/` retains ten editable `.recordly` snapshots. Some variants were prepared as copies of the native project data, then opened and rendered in Recordly. Project media paths refer to this checkout; moving the folder requires relinking. The installed app's project browser also has the smoke-test projects. Recordly was left on R09.

Screen Recording and Accessibility permissions are now recognized. The native Save panel was unreliable under automation. Where Save could not complete, the fully rendered `recordly-export-*.mp4` file was copied from the macOS temporary directory before closing the dialog; those are the app's encoded output files. A manual save also succeeded for some cases. This workaround should not be necessary when operating the Save panel manually.

**Speed-region timing:** native `clipRegions.startMs/endMs` use the output timeline. The corrected R10 sets a 2× clip ending at 8104ms and trims the source from 16208ms onward. An initial hand-prepared fixture used inconsistent timing; it was corrected through the app's native 1× → 2× controls and re-exported. Do not interpret the initial fixture as a speed-control defect.

`failures/` retains the initial text-overlay export and initial inconsistent speed fixture for comparison. The gallery's R08 is the repeated native-control failure. No success claim should be made for that case.

## Scope still open for final production

- Physical iPhone capture, scan motion, cursor/tap tracking and audio were not validated by these Simulator/import tests.
- F02 needs a completed export; F03 needs a downloaded file and playback check; F04 needs an export; F05 needs verified moving-screen synchronization.
- R08 needs a root-cause fix or a different caption method; R09 needs a background-border check.
- These samples contain temporary app state and are for choosing effects. They should not be used as final launch footage.

Tool links and the earlier documentation research are in [app-capture-tools.md](../../specs/launch-research/app-capture-tools.md).
