"""Versioned vocabulary shared by measurement, planning, products and rendering."""

CATEGORY_VERSION = 1

# Measured defaults never substitute for verified purchasable dimensions.
_SIZES = {
    "sofa": (2, .9, .85), "armchair": (.85, .85, .9), "chair": (.5, .5, .9),
    "stool": (.4, .4, .5), "table": (1.2, .8, .75), "dining_table": (1.6, .9, .75),
    "coffee_table": (1, .6, .4), "side_table": (.5, .5, .5), "desk": (1.2, .6, .75),
    "nightstand": (.5, .4, .55), "dresser": (1, .5, .8), "counter": (1.2, .6, .9),
    "shelf": (.8, .35, 1.8), "cabinet": (.8, .5, 1), "tv_stand": (1.5, .4, .5),
    "bed": (1.5, 2, .6), "tv": (1.1, .08, .65), "floor_lamp": (.4, .4, 1.6),
    "table_lamp": (.25, .25, .45), "plant": (.4, .4, .7), "decor": (.2, .2, .25),
    "mirror": (.6, .04, 1), "wall_art": (.6, .04, .5), "rug": (2, 1.5, .02),
    "curtain": (1.5, .08, 2), "ceiling_light": (.4, .4, .3),
    "outlet": (.08, .02, .08), "light_switch": (.08, .02, .12),
    "radiator": (.8, .2, .6), "vent": (.25, .02, .2),
    "sink": (.6, .5, .9), "toilet": (.5, .7, .8), "bathtub": (.8, 1.7, .6),
    "refrigerator": (.7, .7, 1.8), "stove": (.6, .6, .9),
    "oven": (.6, .6, .6), "dishwasher": (.6, .6, .85), "washer_dryer": (.6, .65, .9),
    "fireplace": (1, .4, 1), "stairs": (1, 2, 2),
}
DETECTION_LABELS = (
    "table_lamp", "floor_lamp", "plant", "wall_art", "mirror", "rug", "curtain",
    "ceiling_light", "outlet", "light_switch", "radiator", "vent",
)
WALL_FEATURES = frozenset(("outlet", "light_switch", "vent"))
PERMANENT_CATEGORIES = frozenset(("radiator", "sink", "toilet", "bathtub", "stove",
                                  "oven", "dishwasher", "fireplace", "stairs"))
SUPPORT_CATEGORIES = frozenset(("table", "dining_table", "coffee_table", "side_table",
                                "desk", "nightstand", "dresser", "counter", "shelf", "cabinet"))
_NATIVE = {
    "sofa": "sofa", "chair": "chair", "table": "table", "storage": "cabinet",
    "bed": "bed", "television": "tv", "sink": "sink", "toilet": "toilet",
    "bathtub": "bathtub", "refrigerator": "refrigerator", "stove": "stove",
    "oven": "oven", "dishwasher": "dishwasher", "washerDryer": "washer_dryer",
    "fireplace": "fireplace", "stairs": "stairs",
}


def _category(category, size):
    mount = ("wall" if category in WALL_FEATURES | {"tv", "mirror", "wall_art", "curtain"}
             else "ceiling" if category == "ceiling_light" else "floor")
    collision = "none" if category in WALL_FEATURES else "rug" if category == "rug" else mount
    return {"id": category, "mount": mount, "collision_class": collision,
            "default_size": list(size), "plausible_range": {"min": [.01, .01, .01], "max": [10, 10, 5]},
            "standin": category, "default_tint": "#B9ADA0",
            "native_sources": [k for k, v in _NATIVE.items() if v == category],
            "detection_label": category if category in DETECTION_LABELS else None,
            "absorbs": [category]}


CATEGORIES = {category: _category(category, size) for category, size in _SIZES.items()}
CATEGORIES["cabinet"]["absorbs"] += ["shelf"]
CATEGORIES["chair"]["absorbs"] += ["stool"]
CATEGORIES["rug"]["plausible_range"]["min"][2] = .0001
for _panel in ("wall_art", "mirror", "tv"):
    CATEGORIES[_panel]["plausible_range"]["min"][1] = .0001


def native_category(category, attributes=None):
    """Unknown native classifications stay unknown; attributes may refine known cases."""
    import json

    case = next(iter(category), "") if isinstance(category, dict) else category
    mapped = _NATIVE.get(case)
    attrs = json.dumps(attributes or {}).lower()
    if case == "storage" and "shelf" in attrs:
        return "shelf"
    if case == "chair" and "stool" in attrs:
        return "stool"
    if case == "table":
        for token, refined in (("dining", "dining_table"), ("coffee", "coffee_table"),
                               ("desk", "desk"), ("side", "side_table"), ("night", "nightstand")):
            if token in attrs:
                return refined
    return mapped
