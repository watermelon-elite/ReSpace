"""Conservative backend-compatible placement categories.

The external backend registry is absent here. Only IDs named by the checked-in
SPEC and room-json-steer.md are exported; unconfirmed identities remain `other`.
"""
import re

CATEGORIES = frozenset("""chair sofa stool armchair table coffee_table
desk bed cabinet shelf counter refrigerator rug lamp floor_lamp
ceiling_light plant wall_art mirror curtain tv outlet light_switch radiator vent
espresso_machine menu_board register display_case pendant_light bar_stool trash_bin other""".split())

ALIASES = {"storage_furniture": "cabinet", "shelving": "shelf", "countertop": "counter",
           "cabinets": "cabinet", "shades": "curtain", "switch": "light_switch",
           "television": "tv"}
TERMS = [("coffee table", "coffee_table"), ("side table", "table"),
         ("dining table", "table"), ("tv stand", "cabinet"),
         ("floor lamp", "floor_lamp"), ("table lamp", "lamp"),
         ("light switch", "light_switch"), ("fridge", "refrigerator"),
         ("switch", "light_switch"), ("countertop", "counter"), ("shade", "curtain"),
         ("television", "tv"), ("couch", "sofa"), ("bookshelf", "shelf")]


def category(identifier, label):
    text = label.lower().replace("_", " ")
    # Classify the object itself, rather than objects named in its surroundings.
    text = re.split(r"\s+(?:on|above|below|under|near|beside|behind|next to|in front of|with|at|by)\s+", text, maxsplit=1)[0]
    # An appliance's contextual label ("kettle on countertop") must not turn it
    # into the supporting counter. Keep broad perception classes within scope.
    scope = {"appliance": {"refrigerator", "espresso_machine"}, "electronics": {"tv"},
             "lighting_fixture": {"lamp", "floor_lamp", "ceiling_light", "pendant_light"}}.get(identifier, CATEGORIES)
    for term, value in TERMS+[(v.replace("_", " "), v) for v in sorted(CATEGORIES, key=lambda v: (-len(v), v)) if v != "other"]:
        if value in scope and re.search(r"\b"+re.escape(term)+r"s?\b", text):
            return value
    return identifier if identifier in CATEGORIES else ALIASES.get(identifier, "other")
