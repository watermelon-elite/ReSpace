from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from respace.products import (
    ProductError, build_budget_proposal, calculate_purchases, dimension_evidence,
    optional_refresh_required, rank_choices, variant_identity,
)


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def offer(variant="v_chair", price="100.00", units=2):
    return {"schema_version": 1, "offer_id": f"o_{variant}", "variant_id": variant,
            "merchant": "Example", "product_url": "https://example.com/chair",
            "price": price, "currency": "USD", "availability": "in_stock",
            "exact_variant": True, "checked_at": NOW.isoformat(),
            "pack_contents": {"verified": True, "components": [{"variant_id": variant,
                "units": units, "dimensions": [0.5, 0.5, 0.8]}]}}


def choice(variant, price, practical=80, source="live"):
    return {"variant_id": variant, "category": "chair", "title": "Chair",
            "dimensions": [0.5, 0.5, 0.8], "source": source,
            "dimension_evidence": {"variant_id": variant, "dimensions": [0.5, 0.5, 0.8], "outcome": "verified", "verified_at": NOW.isoformat(), "expires_at": (NOW + timedelta(days=7)).isoformat()},
            "offer": offer(variant, price, 1), "features": {},
            "practical_score": practical, "style_score": 80,
            "practical_reason": "Meets requested function", "style_reason": "Matches requested style"}


def test_single_axis_limit_rejects_oversize_without_inventing_other_limits():
    from respace.products import choice_eligible
    product = choice('table', '100.00')
    assert choice_eligible(product, {'max_dimensions': [0.5, None, None]}, now=NOW)
    assert not choice_eligible(product, {'max_dimensions': [0.49, None, None]}, now=NOW)


def test_whole_packs_surplus_removal_and_decimal_cents():
    selected = offer()
    items = [{"id": f"i_{i}", "origin": "new", "status": "new",
              "variant_id": "v_chair", "offer_id": selected["offer_id"]} for i in range(3)]
    result = calculate_purchases(items, {selected["offer_id"]: selected}, "300.00")
    assert result["total"] == "200.00"
    assert result["lines"][0]["paid_surplus_count"] == 1
    assert result["lines"][0]["purchased_pack_count"] == 2
    assert calculate_purchases(items[:2], {selected["offer_id"]: selected}, "300.00")["total"] == "100.00"
    items[0]["origin"] = "existing"
    assert calculate_purchases(items, {selected["offer_id"]: selected}, "300.00")["total"] == "100.00"


def test_replacement_product_on_original_object_is_purchased_without_losing_original_identity():
    selected=offer()
    item={'id':'i_original','object_id':'original','origin':'existing','status':'existing','replacement_of_object_id':'original','variant_id':'v_chair','offer_id':selected['offer_id']}
    assert calculate_purchases([item],{selected['offer_id']:selected},'300.00')['total']=='100.00'
    assert calculate_purchases([{**item,'status':'removed'}],{selected['offer_id']:selected},'300.00')['total']=='0.00'


def test_dimensions_convert_all_axes_and_reject_package_missing_axis():
    raw = {"exact_variant": True, "classification": "item", "measurements": [
        {"axis": axis, "label": axis.title(), "value": value, "unit": "in"}
        for axis, value in (("width", "20"), ("depth", "10"), ("height", "30"))]}
    result = dimension_evidence("v", "https://example.com/chair", raw, now=NOW)
    assert result["dimensions"] == [0.508, 0.254, 0.762]
    assert result["original_measurements"] == raw["measurements"]
    raw["classification"] = "package"
    assert dimension_evidence("v", "https://example.com/chair", raw, now=NOW)["outcome"] == "package_dimensions"
    raw["classification"] = "item"
    raw["measurements"].pop()
    assert dimension_evidence("v", "https://example.com/rug", raw, now=NOW)["outcome"] == "missing_dimensions"


def test_ranking_shared_benchmark_relative_value_and_refresh_boundary():
    choices = [choice("candidate", "150.00"), choice("b", "200.00", source="stored"),
               choice("c", "200.00"), choice("d", "200.00")]
    ranked, snapshot = rank_choices(choices, {}, now=NOW)
    selected = next(c for c in ranked if c["variant_id"] == "candidate")
    assert selected["scores"]["value"] == 75
    assert selected["scores"]["overall"] == 79.5
    assert snapshot["sample_count"] == 4
    assert [optional_refresh_required(score, 80, 3) for score in (84, 85, 86)] == [False, False, True]
    assert optional_refresh_required(1, 80, 2)
    for price, expected in (("150.00", 75), ("200.00", 50), ("250.00", 25), ("900.00", 0)):
        choices[0]["offer"]["price"] = price
        ranked, _ = rank_choices(choices, {}, now=NOW)
        assert next(c for c in ranked if c["variant_id"] == "candidate")["scores"]["value"] == expected
    ranked, _ = rank_choices(choices[:3], {}, now=NOW)
    assert all(c["scores"]["value"] == 50 for c in ranked)


def test_title_is_not_identity_and_options_distinguish_gtin():
    a = {"title": "Chair", "merchant": "A", "source_key": "1"}
    b = {**a, "merchant": "B"}
    assert variant_identity(a) != variant_identity(b)
    a.update({"gtin": "1234567890123", "identity_verified": True, "options": {"color": "red"}})
    b.update({"gtin": "1234567890123", "identity_verified": True, "options": {"color": "red"}})
    assert variant_identity(a) == variant_identity(b)
    b["options"] = {"color": "blue"}
    assert variant_identity(a) != variant_identity(b)


def test_budget_proposal_requires_whole_checked_purchase_set():
    selected = offer()
    items = [{"id": "i", "origin": "new", "status": "new", "variant_id": "v_chair", "offer_id": selected["offer_id"]}]
    summary = calculate_purchases(items, {selected["offer_id"]: selected}, "90.00")
    proposal = build_budget_proposal("90.00", summary, [], "Required chair has no verified substitute", now=NOW)
    assert proposal["old_ceiling"] == "90.00"
    assert proposal["new_ceiling"] == "100.00"
    assert proposal["requires_explicit_approval"] is True
    assert build_budget_proposal("110.00", summary, [], "Upgrade", now=NOW) is None
    cheaper = deepcopy(summary)
    cheaper["total"] = "80.00"
    assert build_budget_proposal("90.00", summary, [cheaper], "Upgrade", now=NOW) is None
    summary["lines"][0]["checked_at"] = (NOW - timedelta(days=2)).isoformat()
    with pytest.raises(ProductError):
        build_budget_proposal("90.00", summary, [], "Upgrade", now=NOW)


def test_hard_requirements_and_evidence_identity_precede_price_ranking():
    cheap = choice("cheap", "1.00", practical=10)
    good = choice("good", "150.00", practical=95)
    ranked, _ = rank_choices([cheap, good], {}, now=NOW)
    assert ranked[0]["variant_id"] == "good"
    cheap["dimension_evidence"]["variant_id"] = "different_variant"
    ranked, _ = rank_choices([cheap, good], {}, now=NOW)
    assert [c["variant_id"] for c in ranked] == ["good"]
    assert rank_choices([good], {"must_have": {"material": "wood"}}, now=NOW)[0] == []


def test_one_variant_groups_offers_without_counting_merchants_as_comparables():
    expensive = choice("one", "250.00")
    cheaper = deepcopy(expensive)
    cheaper["offer"].update(offer_id="other_merchant", price="150.00", merchant="Other")
    ranked, snapshot = rank_choices([expensive, cheaper], {}, now=NOW)
    assert len(ranked) == 1 and snapshot["sample_count"] == 1
    assert ranked[0]["offer"]["price"] == "150.00"
    assert len(ranked[0]["offers"]) == 2
    assert ranked[0]["scores"]["value"] == 50


def test_versioned_transport_fixture_has_complete_evidence_purchases_and_search():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "product-contract-v1.json").read_text())
    selected = fixture["selection"]
    assert fixture["schema_version"] == selected["schema_version"] == 1
    assert selected["variant"]["image_references"] and selected["dimension_evidence"]["source_url"]
    assert selected["dimension_evidence"]["dimensions"] == selected["dimensions"]
    assert fixture["purchase_summary"]["total"] == "200.00"
    assert fixture["purchase_summary"]["lines"][0]["paid_surplus_count"] == 1
    assert fixture["budget_proposal"]["old_ceiling"] == "150.00"
    assert len(fixture["search"]["displayed_choices"]) == 3
    assert fixture["rejected_dimension_evidence"]["outcome"] == "missing_dimensions"
