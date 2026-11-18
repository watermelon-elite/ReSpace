# UI studio

Edit the real SwiftUI screens with sample data, without a backend or LiDAR.

## Live editing in Xcode

1. Open `ReSpace.xcodeproj` and select the **ReSpace UI** scheme and an iPhone Simulator.
2. Open a screen's Swift file and choose **Editor → Canvas** (Option–Command–Return).
3. Resume its named preview. Edit the screen normally; the canvas refreshes as code compiles.

Previews are included in `ContentView.swift`, `RoomViews.swift`, `DesignView.swift`,
`OperationViews.swift`, `ProductViews.swift`, `ShoppingListViews.swift` and
`ShoppingShareView.swift`. Shared colours, typography and controls live in
`DesignSystem.swift`. Pin a preview in the canvas while editing shared controls.

The first preview and structural changes can require a build. Canvas updates do
not update a separately running Simulator app.

## Recording

Run the **ReSpace UI** scheme (Command–R). Choose a screen in **UI studio**.
The picker disappears completely. Long-press a non-control area for 1.5 seconds
to return to the picker. Relaunching or reopening a screen from the picker resets
its sample session. Use Simulator's screenshot and recording controls for assets.

In the Debug Simulator and UI studio, Scan your room opens setup explaining that capture requires a LiDAR iPhone. On a supported physical iPhone, the
main app still uses the real scan setup. Questions, navigation, selection,
room instructions and shopping/share sheets use the actual views with simulated
responses. Text requests receive a prepared response; no AI or placement solver
runs. The room displays bundled placeholder artwork instead of starting the 3D
renderer, keeping previews fast and avoiding Simulator rendering problems.
Camera gestures and visual furniture changes are not simulated. Product images
use the existing fallback until artwork is supplied. Merchant links are intercepted in the demo. Native
sharing and saving images remain real actions when explicitly selected.

## Files and isolation

- `ReSpace/UIDemo.swift`: screen picker, preview wrapper and in-memory API responses.
- `ReSpace/Preview Content/UIDemo.json`: editable sample copy, prices and geometry.
- `ReSpace UI.xcscheme`: launches the existing Debug target with `--ui-demo`.

The demo bypasses the backend, Keychain identity, saved Rooms, request queue and
draft persistence. Shopping lists are constructed in memory. Sample code is
compiled only in Debug; the fixture is a development asset excluded from archives.
The normal **ReSpace** scheme continues to run the real app.

Both schemes use the same screen implementations and design system. There is no
second UI to copy into production: edits to a screen update both on the next
build. The differences are sample data and the studio's static room illustration;
the main app keeps its interactive 3D renderer. Both use `RSRoomCard` for the home
screen. The production library has no bundled Kitchenette or Meeting room entry; real local captures use their own photo thumbnails.

`ReSpace/Ollo.swift` provides the shared companion and one-pass pose animation.
The nine existing transparent sprites are bundled in `Assets.xcassets`. Ollo
appears in scan guidance, questions and operation results. The Design composer reserves its space for input and camera controls.
The normal home screen uses a native Rooms list, a Settings button and one Scan room action. Settings owns the reconstruction connection check. With `RESPACE_DESIGN_FEATURES=NO`, planning and shopping are hidden while scan/reconstruction is validated; the UI studio can still preview those later stages with sample data.
Keyboard focus shrinks the composer character; accessibility text sizes hide it
before reducing text space. Reduce Motion uses still poses. Gestures run once per
session/event, and saved designs loaded from history do not trigger a hop.

## Pipeline audit launch flags (Debug only)

`--ui-demo --ui-screen Design --ui-live-scene` opens the actual RealityKit renderer using fixture measurements and representative geometry. Omitting `--ui-live-scene` keeps the static studio illustration. This is visual test data, not a scan or a live recommendation.

Add `--ui-large-type` for accessibility3 text, or `--ui-design-error` for initial Design-load failure. Other screen names include `Question`, `Product`, `Shopping list`, `My Rooms` and `Room review`. Launch without `--ui-demo` to inspect the real saved library, empty state and connection recovery. No fixture is imported into normal persistence by these flags.


`--ui-walkthrough-audit` opens the actual SceneKit walkthrough renderer on a private
export copied to the app container’s `Documents/WalkthroughAudit/` directory.
This Debug-only route is labeled unpublished, makes no generation requests and
does not import the scene into the saved Rooms library. Use it to compare native
appearance with browser export previews before publication; a rendered checkpoint
is not a completed or visually approved room.
