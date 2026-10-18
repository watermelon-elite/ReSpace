# ReSpace

ReSpace turns a measured room and its user's preferences into a design containing existing Objects and purchasable Products.

## Room and observations

**Room**:
A single physical space being reviewed and redesigned, including its structure and existing Objects.

**Original room**:
The captured room before planning choices or design changes are applied.

**Object**:
Something already present in the scanned room, such as a sofa, lamp or framed print.
_Avoid_: Existing item, furniture when referring to all observed categories

**Wall feature**:
A fixed outlet, light switch or vent that informs placement and is never redesigned.
_Avoid_: Wall object

**Mount**:
Where an Object or Item rests: the floor, wall, ceiling or another Object or Item.

**Detection**:
One image observation of an object's category and two-dimensional location.

**3D detection**:
A Detection located within the measured room; several observations can describe the same Object.
_Avoid_: Sighting, lifted detection

**Measured room context**:
The measurements and identified Objects available from the native scan before the processed room is assembled.

**Room snapshot**:
A fixed processed room state used by a design, unaffected by subsequent observations.

**Saved room**:
A completed capture retained for review and redesign, with its observations, capture artifacts and associated designs.

## Planning and design

**Planning instruction**:
A user direction controlling what a future design may change, without altering the original room or an existing design.

**Kept**:
An Object whose position and presence the user has protected; moving or removing it requires an explicit unlock.
_Avoid_: Fixed when referring to the user's choice

**Let the design decide**:
The default planning state, allowing changes permitted by the selected intent and explicit constraints.

**Remove from design**:
A direction to exclude an Object from the proposal while preserving it in the original room.
_Avoid_: Delete detection

**Fixed**:
An Item that cannot move in a particular placement calculation, including unaffected Items, Kept Objects and permanent fixtures.
_Avoid_: Kept when referring to all immovable Items

**Anchor**:
A named spatial relationship to the room or another Object or Item, such as against a wall or on top of a table.
_Avoid_: Reference point, coordinate

**Addition**:
A new furnishing requested by category, with a Product choice and spatial Anchor resolved as planning progresses; one Addition can request several units.
_Avoid_: Slot

**Priority**:
An Addition's relative importance to the design, distinct from the rank of candidate Products.
_Avoid_: Product score

**Keep-clear zone**:
Floor area reserved for access through a door or opening; rugs and wall-mounted Items may overlap it.

**Item**:
One entry in a design: an Object left unchanged, moved or removed, or one placed unit of an Addition.

**Design**:
A proposed arrangement of existing Objects and selected Products for a Room.

**Design version**:
An immutable saved arrangement resulting from generation or a committed edit, including a partially successful edit whose failures are explained.
_Avoid_: Mutable snapshot

**Active design version**:
The version currently chosen for a Room, including a parent restored through Undo.

**Ghost**:
A faint representation of a removed Object that preserves visual context without occupying space in the proposed arrangement.

**Must-have**:
An explicit user requirement that cannot be silently omitted or materially changed.

**Room-use priorities**:
The user's activities, desired experience and relative importance of competing outcomes.

**Trade-off question**:
A question about a practical consequence or priority, using verified product evidence when it presents a concrete purchase choice.

**Decision revision**:
A particular set of planning choices and answers, distinct from an already saved design.

## Products and purchases

**Product**:
A real furnishing available through a merchant listing or the curated catalog.

**Product candidate**:
A stored Product under consideration, including candidates with incomplete or rejected evidence.

**Candidate pool**:
The broader discovered Products before ranking narrows the choices.

**Source shortlist**:
The ranked candidates retained from one discovery source for a particular decision.

**Product-verified choice**:
A Product with verified dimensions and an acceptable checked offer, whose final room placement may still await validation.

**Eligible product**:
A candidate satisfying the required evidence and constraints for the action currently being considered.

**Rejected candidate**:
A retained candidate excluded from selectable options, with its rejection reason preserved.

**Verified product dimensions**:
Actual measurements for the exact physical variant, supported by retailer or manufacturer evidence.
_Avoid_: Package dimensions, estimated size

**Purchase offer**:
A merchant's purchasable listing for an exact variant or verified pack, including its price and supplied contents.

**Offer check**:
Verification of the price and availability of a particular Purchase offer.

**Placed unit**:
A physical Item represented in the room; a purchased pack may supply several units.

**Paid surplus**:
Purchased units that are not placed in the design but remain part of its purchase cost.

**Purchase total**:
The full price of the new Products and whole packs needed by the design, including paid surplus and excluding tax, shipping and existing Objects.

**Relative value**:
A Product's price advantage or premium compared with similar discovered Products, distinct from absolute affordability.

**Swap alternative**:
An eligible Product that can replace a selected Product at its current placement within the approved budget.

**Find more**:
A request for additional eligible options without changing the current selection.
