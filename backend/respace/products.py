"""Exact-variant evidence, source-neutral ranking and whole-offer purchases."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import math
import re
from statistics import median
from typing import Any
from urllib.parse import urlsplit, urlunsplit


RULE_VERSION = "practical60-style30-value10-evidence-first-v2"
UNITS = {"m": Decimal(1), "cm": Decimal("0.01"), "mm": Decimal("0.001"),
         "in": Decimal("0.0254"), "inch": Decimal("0.0254"),
         "inches": Decimal("0.0254"), '"': Decimal("0.0254"), "″": Decimal("0.0254"),
         "ft": Decimal("0.3048"), "foot": Decimal("0.3048"), "feet": Decimal("0.3048"),
         "'": Decimal("0.3048"), "′": Decimal("0.3048")}


class ProductError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def stable_id(prefix: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return prefix + "_" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def money(value: Any, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,2})?", value):
        raise ProductError("invalid_money", "USD amounts must be nonnegative decimal strings with at most two fractional digits")
    result = Decimal(value)
    if positive and result <= 0:
        raise ProductError("invalid_money", "Price or budget must be positive")
    return result


def amount(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def recent(value: str | None, days: float, now: datetime | None = None) -> bool:
    if not value:
        return False
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age = (now or datetime.now(timezone.utc)) - checked
        return timedelta(0) <= age < timedelta(days=days)
    except (ValueError, TypeError):
        return False


def canonical_url(value: Any) -> str:
    try:
        url = urlsplit(value)
        port = url.port
    except (ValueError, TypeError):
        raise ProductError("invalid_url", "Product evidence URL must be a public HTTPS URL") from None
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or port not in (None, 443) or len(value) > 4096):
        raise ProductError("invalid_url", "Product evidence URL must be a public HTTPS URL")
    return urlunsplit(("https", url.netloc.lower(), url.path or "/", url.query, ""))


def variant_identity(facts: dict) -> str:
    options = facts.get("options", {})
    if facts.get("identity_verified") and facts.get("gtin"):
        key = ["gtin", str(facts["gtin"]), options]
    elif facts.get("identity_verified") and facts.get("manufacturer") and facts.get("mpn"):
        key = ["mpn", facts["manufacturer"].casefold(), facts["mpn"], options]
    else:
        key = ["merchant", facts.get("merchant"), facts.get("source_key"),
               facts.get("product_url"), options]
    return stable_id("v", key)


def dimension_evidence(variant_id: str, source_url: str, facts: dict,
                       *, now: datetime | None = None, category: dict | None = None) -> dict:
    checked = now or datetime.now(timezone.utc)
    original = deepcopy(facts.get("measurements", []))
    result = {"schema_version": 1, "evidence_id": stable_id("dim", [variant_id, timestamp(checked), facts]),
              "variant_id": variant_id, "source_url": canonical_url(source_url),
              "original_measurements": original, "classification": facts.get("classification", "unknown"),
              "verified_at": timestamp(checked), "expires_at": timestamp(checked + timedelta(days=7)),
              "dimensions": None, "outcome": "missing_dimensions"}
    if not facts.get("exact_variant"):
        result["outcome"] = "ambiguous_variant"
        return result
    if result["classification"] != "item":
        result["outcome"] = "package_dimensions" if result["classification"] == "package" else "ambiguous_dimensions"
        return result
    axes = {}
    for measurement in original:
        axis, unit = measurement.get("axis"), measurement.get("unit", "").lower()
        if axis not in ("width", "depth", "height") or axis in axes or unit not in UNITS or not measurement.get("label"):
            result["outcome"] = "ambiguous_dimensions"
            return result
        try:
            raw_value = str(measurement["value"])
            if "/" in raw_value:
                fraction = sum((Fraction(part) for part in raw_value.split()), Fraction(0))
                converted = Decimal(fraction.numerator) / Decimal(fraction.denominator)
            else:
                converted = Decimal(raw_value)
            value = converted * UNITS[unit]
        except (InvalidOperation, KeyError, ValueError, ZeroDivisionError):
            result["outcome"] = "invalid_dimensions"
            return result
        if not value.is_finite() or value <= 0 or value > 100:
            result["outcome"] = "invalid_dimensions"
            return result
        axes[axis] = float(value)
    assumed_axes = {}
    if category and category.get('id') == 'rug' and set(axes) == {'width', 'depth'}:
        assumed_axes['height'] = category['default_size'][2]
        axes.update(assumed_axes)
    if len(axes) != 3:
        return result
    size = [axes[axis] for axis in ("width", "depth", "height")]
    if category and category.get("plausible_range"):
        limits = category["plausible_range"]
        if isinstance(limits, dict):
            lower, upper = limits["min"], limits["max"]
        else:
            lower, upper = limits
        if any(not lo <= value <= hi for value, lo, hi in zip(size, lower, upper, strict=True)):
            result["outcome"] = "dimension_range_conflict"
            return result
    result.update(dimensions=size, outcome="verified")
    if assumed_axes:
        result.update(assumed_axes=assumed_axes, verified_axes=[axis for axis in axes if axis not in assumed_axes],
            warnings=['Rug thickness is not published; the category thickness is used only for representative geometry.'])
    return result


def validate_pack(offer: dict) -> list[dict]:
    contents = offer.get("pack_contents", {})
    components = contents.get("components", [])
    if not contents.get("verified") or not components:
        raise ProductError("ambiguous_pack", "Supplied pack contents are not verified")
    seen = set()
    for component in components:
        size = component.get("dimensions", [])
        units = component.get("units")
        if (not component.get("variant_id") or component["variant_id"] in seen
                or not isinstance(units, int) or isinstance(units, bool) or units < 1
                or len(size) != 3 or any(isinstance(v, bool) or not isinstance(v, (float, int))
                    or not math.isfinite(v) or v <= 0 for v in size)):
            raise ProductError("ambiguous_pack", "Each pack component needs a unique exact variant, positive quantity and verified dimensions")
        seen.add(component["variant_id"])
    return components


def offer_eligible(offer: dict, *, now: datetime | None = None, freshness: bool = True) -> bool:
    try:
        money(offer.get("price"), positive=True)
        canonical_url(offer.get("product_url"))
        validate_pack(offer)
    except ProductError:
        return False
    return (offer.get("currency") == "USD" and offer.get("availability") in ("in_stock", "unverified")
            and offer.get("exact_variant") is True
            and (not freshness or recent(offer.get("checked_at"), 1, now)))


def choice_eligible(choice: dict, request: dict, *, now: datetime | None = None, allow_stale_offers: bool = False) -> bool:
    evidence = choice.get("dimension_evidence", {})
    if evidence.get("outcome") != "verified" or not recent(evidence.get("verified_at"), 7, now):
        return False
    if (evidence.get("variant_id") != choice.get("variant_id") or evidence.get("dimensions") != choice.get("dimensions")
            or choice.get("offer", {}).get("variant_id") != choice.get("variant_id")):
        return False
    if not offer_eligible(choice.get("offer", {}), now=now, freshness=not allow_stale_offers):
        return False
    component = next((c for c in choice["offer"]["pack_contents"]["components"] if c["variant_id"] == choice["variant_id"]), None)
    if component is None or component["dimensions"] != choice["dimensions"]:
        return False
    if request.get("category") and choice.get("category") != request["category"]:
        return False
    size = choice.get("dimensions", [])
    if len(size) != 3 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in size):
        return False
    if request.get("max_dimensions") and any(limit is not None and v > limit for v, limit in zip(size, request["max_dimensions"], strict=True)):
        return False
    if request.get('max_dimensions') and any(limit is not None and axis in evidence.get('assumed_axes', {})
            for axis, limit in zip(('width', 'depth', 'height'), request['max_dimensions'], strict=True)):
        return False
    features = choice.get("features", {})
    if any(features.get(key) != value for key, value in request.get("must_have", {}).items()):
        return False
    if any(features.get(key) == value for key, value in request.get("avoid", {}).items()):
        return False
    if request.get("approved_ceiling"):
        units = next((c["units"] for c in validate_pack(choice["offer"]) if c["variant_id"] == choice["variant_id"]), 0)
        quantity = request.get("quantity", 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ProductError("invalid_quantity", "Requested physical quantity must be a positive integer")
        if not units or money(choice["offer"]["price"]) * ((quantity + units - 1) // units) > money(request["approved_ceiling"]):
            return False
    return True


def _comparable(a: dict, b: dict) -> bool:
    if a["category"] != b["category"] or a["variant_id"] == b["variant_id"]:
        return False
    dimensions = 2 if a['category'] == 'rug' else 3
    if any(not 0.75 <= x / y <= 1.33333334 for x, y in zip(a["dimensions"][:dimensions], b["dimensions"][:dimensions], strict=True)):
        return False
    keys = ("function", "material", "capacity", "condition")
    return all(a.get("features", {}).get(k) == b.get("features", {}).get(k) for k in keys)


def _unit_price(choice: dict) -> Decimal:
    components = validate_pack(choice["offer"])
    if len(components) != 1 or components[0]["variant_id"] != choice["variant_id"]:
        raise ProductError("incomparable_bundle", "Mixed bundles do not have a comparable single-unit price")
    return money(choice["offer"]["price"], positive=True) / components[0]["units"]


def verification_priority(choice: dict) -> int:
    offer = choice.get('offer', {})
    return int(offer.get('availability') != 'in_stock'
        or any(choice.get('dimension_evidence', {}).get('conflicts', {}).values())
        or any(offer.get('evidence', {}).get('conflicts', {}).values()))


def choice_offer_key(choice: dict) -> tuple[int, Decimal, str]:
    return verification_priority(choice), money(choice['offer']['price']), choice['offer']['offer_id']


def verification_warnings(choice: dict) -> list[str]:
    evidence, offer = choice.get('dimension_evidence', {}), choice.get('offer', {})
    warnings = list(evidence.get('warnings', [])) + list(offer.get('warnings', []))
    conflicts = {**evidence.get('conflicts', {}), **offer.get('evidence', {}).get('conflicts', {})}
    warnings.extend(f'Conflicting {field} evidence; confirm the selected option on the merchant page.'
                    for field, values in conflicts.items() if values)
    if offer.get('availability') == 'unverified':
        warnings.append('Availability is uncertain; confirm stock on the merchant page.')
    return list(dict.fromkeys(warnings))


def rank_choices(choices: list[dict], request: dict, *, now: datetime | None = None,
                 allow_stale_offers: bool = False, allow_unscored: bool = False) -> tuple[list[dict], dict]:
    """One frozen benchmark for both sources; merchant offers never multiply samples."""
    selected: dict[str, dict] = {}
    for choice in choices:
        if not choice_eligible(choice, request, now=now, allow_stale_offers=allow_stale_offers):
            continue
        previous = selected.get(choice["variant_id"])
        if previous is None or choice_offer_key(choice) < choice_offer_key(previous):
            selected[choice["variant_id"]] = choice
    members = []
    for choice in sorted(selected.values(), key=lambda c: c["variant_id"]):
        if not recent(choice["offer"].get("checked_at"), 1, now):
            continue
        try:
            unit_price = _unit_price(choice)
        except ProductError:
            continue
        members.append({"variant_id": choice["variant_id"], "offer_id": choice["offer"]["offer_id"],
                        "unit_price": str(unit_price), "checked_at": choice["offer"]["checked_at"],
                        "inclusion_reason": "Same type/function, approximate size/capacity, known material/features and condition"})
    snapshot: dict = {"schema_version": 1, "rule_version": RULE_VERSION, "created_at": timestamp(now),
                "context": {key: deepcopy(request[key]) for key in ("category", "function", "quantity", "must_have", "avoid", "max_dimensions", "styles") if key in request},
                "members": members, "sample_count": len(members), "comparisons": {}}
    snapshot["snapshot_id"] = stable_id("comparison", snapshot)
    ranked = []
    for choice in selected.values():
        if allow_unscored and ('practical_score' not in choice or 'style_score' not in choice):
            continue
        comparable = [m for m in members if _comparable(choice, selected[m["variant_id"]])]
        value, benchmark = Decimal(50), None
        uncertainty: str | None = "insufficient comparison evidence"
        if not recent(choice["offer"].get("checked_at"), 1, now):
            uncertainty = "stale price; provisional ranking requires an offer check"
        elif len(comparable) >= 3:
            benchmark = median(Decimal(m["unit_price"]) for m in comparable)
            try:
                value = min(Decimal(100), max(Decimal(0), Decimal(50) + 100 * (1 - _unit_price(choice) / benchmark)))
                uncertainty = None
            except ProductError:
                pass
        practical, style = choice.get("practical_score"), choice.get("style_score")
        if any(isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100 for score in (practical, style)):
            raise ProductError("invalid_ranking", "Practical and style scores must be finite values from 0 to 100")
        score = Decimal(str(practical)) * Decimal("0.6") + Decimal(str(style)) * Decimal("0.3") + value * Decimal("0.1")
        result = deepcopy(choice)
        same_variant_offers = {c["offer"]["offer_id"]: deepcopy(c["offer"]) for c in choices
                               if c["variant_id"] == choice["variant_id"] and offer_eligible(c.get("offer", {}), now=now)}
        result["offers"] = sorted(same_variant_offers.values(), key=lambda offer: choice_offer_key({'offer': offer}))
        warnings = verification_warnings(choice)
        result.update(schema_version=1, comparison_snapshot_id=snapshot["snapshot_id"], rule_version=RULE_VERSION,
                      scores={"practical": practical, "style": style, "value": float(value), "overall": float(score)},
                      reasons={"practical": choice.get("practical_reason", ""), "style": choice.get("style_reason", ""),
                               "value": uncertainty or "Price relative to the median of comparable discoveries"},
                      verification_warnings=warnings, uncertainty=uncertainty)
        snapshot["comparisons"][choice["variant_id"]] = {"members": [m["variant_id"] for m in comparable],
            "sample_count": len(comparable), "median": str(benchmark) if benchmark else None, "uncertainty": uncertainty}
        ranked.append(result)
    ranked.sort(key=lambda c: (verification_priority(c), -c["scores"]["overall"], -int(c.get("render", {}).get("kind") == "catalog"), c["variant_id"]))
    return ranked, snapshot


def optional_refresh_required(provisional_score: float, weakest_score: float, eligible_count: int,
                              *, mandatory: bool = False, same_benchmark: bool = True) -> bool:
    if not same_benchmark:
        raise ProductError("stale_comparison", "Rerank both sources on the current benchmark before applying a refresh cutoff")
    return mandatory or eligible_count < 3 or provisional_score > weakest_score + 5


def is_product_item(item: dict) -> bool:
    return item.get('origin')=='new' or bool(item.get('replacement_of_object_id'))


def calculate_purchases(items: list[dict], offers: dict[str, dict] | list[dict], approved_ceiling: str) -> dict:
    ceiling = money(approved_ceiling)
    by_id = {offer["offer_id"]: offer for offer in offers} if isinstance(offers, list) else offers
    demands: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    all_ids = set()
    for item in items:
        if not is_product_item(item) or item.get("status") == "removed":
            continue
        item_id = item.get("item_id", item.get("id"))
        if not item_id or item_id in all_ids or not item.get("offer_id") or not item.get("variant_id"):
            raise ProductError("invalid_purchase", "New placed Items require unique IDs and exact offer/variant references")
        all_ids.add(item_id)
        demands[item["offer_id"]][item["variant_id"]].append(item_id)
    lines, total = [], Decimal(0)
    for offer_id, wanted in sorted(demands.items()):
        offer = by_id.get(offer_id)
        if not offer or not offer_eligible(offer, freshness=False):
            raise ProductError("unverified_offer", "Purchase requires an exact USD offer with verified supplied contents and checked availability")
        components = validate_pack(offer)
        if not set(wanted) <= {c["variant_id"] for c in components}:
            raise ProductError("ambiguous_pack", "Offer does not supply the requested physical variant")
        packs = max((len(wanted.get(c["variant_id"], [])) + c["units"] - 1) // c["units"] for c in components)
        supplied = sum(c["units"] * packs for c in components)
        placed_ids = sorted(i for ids in wanted.values() for i in ids)
        line_total = money(offer["price"], positive=True) * packs
        lines.append({"schema_version": 1, "offer_id": offer_id, "variant_id": offer["variant_id"],
                      "offer": deepcopy(offer), "unit_pack_price": amount(money(offer["price"])),
                      "purchased_pack_count": packs, "verified_contents": deepcopy(offer["pack_contents"]),
                      "supplied_unit_count": supplied, "placed_unit_count": len(placed_ids),
                      "placed_item_ids": placed_ids, "paid_surplus_count": supplied - len(placed_ids),
                      "line_total": amount(line_total), "checked_at": offer["checked_at"],
                      "components": [{**deepcopy(c), "supplied_unit_count": c["units"] * packs,
                          "placed_item_ids": sorted(wanted.get(c["variant_id"], [])),
                          "paid_surplus_count": c["units"] * packs - len(wanted.get(c["variant_id"], []))} for c in components]})
        total += line_total
    return {"schema_version": 1, "currency": "USD", "lines": lines, "total": amount(total),
            "approved_ceiling": amount(ceiling), "within_budget": total <= ceiling,
            "tax_excluded": True, "shipping_excluded": True, "existing_objects_excluded": True, "warnings": []}


def build_budget_proposal(old_ceiling: str, purchase_summary: dict, alternatives: list[dict], reason: str,
                          *, now: datetime | None = None, functional_consequences: list[str] | None = None) -> dict | None:
    ceiling, total = money(old_ceiling), money(purchase_summary["total"])
    if total <= ceiling or any(money(option["total"]) <= ceiling for option in alternatives):
        return None
    if not reason.strip() or not purchase_summary.get("lines"):
        raise ProductError("invalid_budget_proposal", "A concrete reason and complete affected purchase set are required")
    for line in purchase_summary["lines"]:
        if not recent(line.get("checked_at"), 1, now) or not offer_eligible(line.get("offer", {}), now=now):
            raise ProductError("unverified_budget_proposal", "Budget choices require recently checked exact offers")
    return {"schema_version": 1, "old_ceiling": amount(ceiling), "new_ceiling": amount(total), "currency": "USD",
            "resulting_total": amount(total), "ceiling_increase": amount(total - ceiling),
            "affected_purchases": deepcopy(purchase_summary["lines"]), "checked_alternatives": deepcopy(alternatives),
            "functional_consequences": functional_consequences or [], "explanation": reason,
            "requires_explicit_approval": True}
