# Reconstruction vocabulary (historical branch reference)

The canonical product glossary is [CONTEXT.md](CONTEXT.md). This incoming branch vocabulary supplies reconstruction background; its generic Design version definition does not override immutable backend versions or the viewing-only walkthrough decision in SPEC §3.5.

ReSpace captures real rooms and creates explorable versions of those rooms that people can redesign.

## Language

**Capture**:
The recorded observations of a real space from one scanning session.
_Avoid_: Model, design

**Reconstruction**:
A representation of the captured space derived from observations and any completion needed to make the room seamless.
_Avoid_: Capture, redesign

**Room snapshot**:
A fixed description of a room and its identified contents at a particular point in time.
_Avoid_: Design version

**Design version**:
A saved arrangement and appearance of a room, including changes to its captured contents and any added items.
_Avoid_: Scan, reconstruction

**Walkthrough**:
An experience in which a person can move their viewpoint through a three-dimensional representation of a space.
_Avoid_: Video tour, inspiration image

**Room structure**:
The fixed architectural shape and built-in contents of the room, including walls, cabinets, counters, doors, and windows, which do not move during redesign.
_Avoid_: Movable furniture, finish

**Movable item**:
A furniture or decor item whose placement can change independently of the room structure.
_Avoid_: Wall, room structure

**Wall decor**:
A movable item mounted on a wall, including posters, paintings, and whiteboards, with its own captured appearance and identity.
_Avoid_: Wallpaper, wall finish

**Finish**:
The visible surface treatment of a room surface, such as wallpaper, paint, or tile, that can change while the surface's shape stays fixed.
_Avoid_: Structural change

**Finished room**:
A completed, seamless room reconstruction ready for the user's walkthrough; intermediate reconstruction results are not presented as the room.
_Avoid_: Scan preview, partial model
