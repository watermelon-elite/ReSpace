from copy import deepcopy
import pytest

from respace.discovery import ProductService
from test_discovery import hit, service


def test_bounded_discovery_persists_each_query_listing_attempt_and_score_before_redelivery(store):
    products, shopping, verifier = service(store, [[hit(1), hit(2)], [hit(3)], []], transient={"1"})
    listing_calls, score_calls = [], []
    original_listings, original_score = shopping.listings, products.ranker.score
    def listings(candidate):
        listing_calls.append(candidate["candidate_id"])
        return original_listings(candidate)
    def score(choice, request):
        score_calls.append(choice["variant_id"])
        return original_score(choice, request)
    shopping.listings, products.ranker.score = listings, score
    request = {"category": "chair", "room_id": "r", "approved_ceiling": "500.00"}
    for _ in range(100):
        before = len(shopping.queries) + len(verifier.calls) + len(listing_calls) + len(score_calls)
        result = products.search(request, "durable", bounded=True)
        after = len(shopping.queries) + len(verifier.calls) + len(listing_calls) + len(score_calls)
        assert after - before <= 1
        # Discard the response and reconstruct the service after every committed stage.
        products = ProductService(store, shopping, verifier, products.ranker)
        if result["state"] != "running":
            break
    else:
        raise AssertionError("Search did not complete")
    assert len(shopping.queries) == 3 and len(set(shopping.queries)) == 3
    assert len(listing_calls) == 3 and len(score_calls) == 3
    assert verifier.calls.count("1") == 2
    assert len(result["displayed_choices"]) == 3
    assert products.search(request, "durable", bounded=True) == result


def test_bounded_find_more_continues_running_fingerprint_without_hiding_prior_choices(store):
    products, shopping, verifier = service(store, [[hit(1), hit(2), hit(3)], [], []])
    initial = products.search({"category": "chair", "room_id": "r"}, "initial")
    selected = deepcopy(initial["displayed_choices"][0])
    selected["selection_id"] = "selected"
    design = {"design_id": "design", "room_id": "r", "scene": {"items": [{"id": "item", "origin": "new",
        "status": "new", "category": "chair", "selection_id": "selected", "variant_id": selected["variant_id"],
        "product": selected}], "selections": {"selected": selected}, "purchase_summary": {"approved_ceiling": "1000.00"}}}
    shopping.batches = [[hit(4), hit(5), hit(6)], [], []]
    frozen = deepcopy(design)
    for _ in range(100):
        result = products.find_more(design, "item", {}, "more", {"active_revision": 1}, bounded=True)
        products = ProductService(store, shopping, verifier, products.ranker)
        if result["state"] != "running":
            break
    else:
        raise AssertionError("Find more did not complete")
    assert len(shopping.queries) == 6
    assert len(result["displayed_choices"]) == 3 and len(result["prior_displayed_choices"]) == 2
    assert design == frozen


def test_bounded_selection_verification_persists_listing_and_ranking_outputs(store):
    from datetime import datetime, timedelta, timezone

    products, shopping, verifier = service(store, [[hit(1), hit(2)], [], []])
    choices = products.search({"category": "chair", "room_id": "r"}, "initial")["displayed_choices"]
    with store.transaction():
        for choice in choices:
            offer = store.get("offers", choice["offer_id"])
            offer["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            store.put("offers", offer["offer_id"], offer)
    listing_calls, score_calls = [], []
    original_listings, original_verify, original_score = shopping.listings, verifier.verify, products.ranker.score
    def listings(candidate):
        listing_calls.append(candidate["candidate_id"])
        return original_listings(candidate)
    def changed(candidate):
        result = original_verify(candidate)
        result["variant"]["features"] = {"material": "wood"}
        return result
    def score(choice, request):
        score_calls.append(choice["variant_id"])
        return original_score(choice, request)
    shopping.listings, verifier.verify, products.ranker.score = listings, changed, score
    before_verify = len(verifier.calls)
    for _ in range(100):
        before = len(verifier.calls) + len(listing_calls) + len(score_calls)
        result = products.verify_selection(choices, "500.00", bounded=True, verification_id="checked",
                                           context={"room_id": "r", "operation_id": "operation"})
        after = len(verifier.calls) + len(listing_calls) + len(score_calls)
        assert after - before <= 1
        products = ProductService(store, shopping, verifier, products.ranker)
        if result["state"] == "completed":
            break
    else:
        raise AssertionError("Selection verification did not complete")
    assert len(result["selected"]) == 2
    assert len(verifier.calls) - before_verify == 2
    assert len(listing_calls) == 2 and score_calls
    assert products.verify_selection(choices, "500.00", bounded=True, verification_id="checked",
        context={"room_id": "r", "operation_id": "operation"}) == result


def test_each_merchant_listing_is_a_separate_durable_verification_attempt(store):
    products, shopping, verifier = service(store, [[hit(1)], [], []])
    listing_calls = []
    def listings(candidate):
        listing_calls.append(candidate["candidate_id"])
        return [{"product_url": f"https://example.com/{merchant}/1", "merchant": merchant, "title": candidate["title"]}
                for merchant in ("a", "b", "c")]
    shopping.listings = listings
    for _ in range(100):
        before = len(verifier.calls)
        result = products.search({"category": "chair", "room_id": "r"}, "many-listings", bounded=True)
        assert len(verifier.calls) - before <= 1
        products = ProductService(store, shopping, verifier, products.ranker)
        if result["state"] != "running":
            break
    assert len(listing_calls) == 1 and len(verifier.calls) == 3
    assert {choice["offer"]["merchant"] for choice in result["displayed_choices"]} == {"a", "b", "c"}


def test_bounded_stale_offer_refresh_reuses_completed_queries_and_persisted_scores(store):
    from datetime import datetime, timedelta, timezone

    products, shopping, verifier = service(store, [[hit(1), hit(2)], [], []])
    initial = products.search({"category": "chair", "room_id": "r"}, "initial")
    with store.transaction():
        for choice in initial["displayed_choices"]:
            offer = store.get("offers", choice["offer_id"])
            offer["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            store.put("offers", offer["offer_id"], offer)
    score_calls = []
    original_score = products.ranker.score
    def score(choice, request):
        score_calls.append(choice["variant_id"])
        return original_score(choice, request)
    products.ranker.score = score
    before_verify = len(verifier.calls)
    for _ in range(100):
        result = products.search({"category": "chair", "room_id": "r"}, "refresh", bounded=True)
        products = ProductService(store, shopping, verifier, products.ranker)
        if result["state"] != "running":
            break
    assert result["state"] == "completed"
    assert len(shopping.queries) == 6
    assert len(verifier.calls) - before_verify == 2
    assert len(score_calls) == 4  # Two provisional views, then two refreshed evidence views.


@pytest.mark.asyncio
async def test_bounded_planning_resumes_discovery_and_selection_without_repeating_model_actions(store):
    from respace.operations import OperationService
    from respace.planning import PlanningController
    from test_operations import room

    products, shopping, verifier = service(store, [[hit(1), hit(2)], [], []])
    room(store, "r")
    with store.transaction():
        store.put("captures", "capture", {"capture_id": "capture", "room_id": "r", "state": "complete", "measured_context": {}})
    operations = OperationService(store)
    operations.submit("device", "r", "generation", {"operation_id": "flow", "capture_id": "capture",
        "planning_revision": 0, "expected_active_revision": 0, "budget": "500.00", "intent": "add", "text": "chair"})
    class Model:
        calls = 0
        async def act(self, context):
            self.calls += 1
            if not context["actions"]:
                return {"action": "search_products", "payload": {"category": "chair", "function": "reading"}}
            chosen = context["actions"][0]["result"]["displayed_choices"][0]
            return {"action": "finalize_selection", "payload": {"selected": [{"variant_id": chosen["variant_id"],
                "offer_id": chosen["offer_id"], "quantity": 1}]}}
    model = Model()
    async def spatial(operation_id, selection, *, bounded=False):
        assert bounded
        operations.finish(operation_id, "succeeded", {"result_kind": "controlled_spatial_result"})
    for _ in range(100):
        await PlanningController(store, operations, products, model, spatial).run("flow", bounded=True)
        current = store.get("operations", "flow")
        if current["state"] in ("succeeded", "failed", "rejected"):
            break
    assert current["state"] == "succeeded"
    assert model.calls == 2 and len(shopping.queries) == 6
    assert len(current["controller"]["actions"]) == 1
    assert len(store.list("selections", "r")) == 1
    assert len(store.list("selection_verifications", "r")) == 1
    assert len(verifier.calls) == 2


@pytest.mark.asyncio
async def test_bounded_budget_question_verifies_sets_before_asking_once(store):
    from datetime import datetime, timedelta, timezone
    from respace.operations import OperationService
    from respace.planning import PlanningController
    from test_operations import room

    products, _, verifier = service(store, [[hit(1)], [], []])
    choice = products.search({"category": "chair", "room_id": "r"}, "source")["displayed_choices"][0]
    room(store, "r")
    with store.transaction():
        store.put("captures", "capture", {"capture_id": "capture", "room_id": "r", "state": "complete", "measured_context": {}})
        offer = store.get("offers", choice["offer_id"])
        offer["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        store.put("offers", offer["offer_id"], offer)
    operations = OperationService(store)
    operation = operations.submit("device", "r", "generation", {"operation_id": "budget", "capture_id": "capture",
        "planning_revision": 0, "expected_active_revision": 0, "budget": "90.00", "intent": "add"})
    operation["controller"] = {"initial_products": {"displayed_choices": [choice]}, "actions": []}
    with store.transaction():
        store.put("operations", "budget", operation)
    class Model:
        calls = 0
        async def act(self, context):
            self.calls += 1
            return {"action": "ask_user", "payload": {"kind": "budget", "text": "Approve the required chair?",
                "proposed_selected": [{"variant_id": choice["variant_id"], "offer_id": choice["offer_id"], "quantity": 1}],
                "alternative_sets": [], "reason": "No verified required chair fits the ceiling",
                "functional_consequences": ["Adds one required reading chair"]}}
    model = Model()
    for _ in range(50):
        await PlanningController(store, operations, products, model, None).run("budget", bounded=True)
        current = store.get("operations", "budget")
        if current["state"] == "needs_clarification":
            break
    assert current["pending_question"]["budget_proposal"]["new_ceiling"] == "100.00"
    assert model.calls == 1 and len(verifier.calls) == 2
    assert len(store.list("budget_proposals", "r")) == 1
    frozen = deepcopy(current["pending_question"])
    await PlanningController(store, operations, products, model, None).run("budget", bounded=True)
    assert store.get("operations", "budget")["pending_question"] == frozen


def test_selection_keeps_structured_requirements_and_rejects_changed_avoid_features(store):
    from datetime import datetime, timedelta, timezone
    from respace.products import ProductError

    products, _, verifier = service(store, [[hit(1)], [], []])
    chosen = products.search({"category": "chair", "room_id": "r"}, "source")["displayed_choices"][0]
    chosen.update(requirements={"material": "wood"}, avoid={"condition": "used"})
    with store.transaction():
        variant = store.get("variants", chosen["variant_id"])
        variant["features"] = {"material": "wood", "condition": "new"}
        store.put("variants", variant["variant_id"], variant)
    verified = products.verify_selection([chosen], "500.00")[0]
    assert verified["requirements"] == {"material": "wood"} and verified["avoid"] == {"condition": "used"}
    with store.transaction():
        offer = store.get("offers", chosen["offer_id"])
        offer["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        store.put("offers", offer["offer_id"], offer)
    original_verify = verifier.verify
    def became_used(candidate):
        result = original_verify(candidate)
        result["variant"]["features"] = {"material": "wood", "condition": "used"}
        return result
    verifier.verify = became_used
    with pytest.raises(ProductError, match="no longer has an eligible"):
        products.verify_selection([verified], "500.00")


@pytest.mark.asyncio
async def test_planning_resolves_same_category_requirement_and_avoid_maps(store):
    from respace.operations import OperationService
    from respace.planning import PlanningController
    from test_operations import room

    products, _, _ = service(store, [[hit(1)], [], []])
    choice = products.search({"category": "chair", "room_id": "r"}, "source")["displayed_choices"][0]
    room(store, "r")
    operations = OperationService(store)
    operation = operations.submit("device", "r", "generation", {"operation_id": "op", "budget": "500.00"})
    operation["controller"] = {"initial_products": {"displayed_choices": [choice]}, "actions": [
        {"action": "search_products", "payload": {"category": "chair", "must_have": {"material": "wood"}}},
        {"action": "search_products", "payload": {"category": "chair", "avoid": {"condition": "used"}}}]}
    operation["controller"]["pending_action"] = {"action": "finalize_selection", "reason": "Requested chair",
        "payload": {"selected": [{"variant_id": choice["variant_id"], "offer_id": choice["offer_id"]}]}}
    with store.transaction():
        store.put("operations", "op", operation)
        store.put("captures", "capture", {"capture_id": "capture", "room_id": "r", "state": "complete"})
    controller = PlanningController(store, operations, products, None, None)
    await controller.run("op", bounded=True)
    selected = operations.get("device", "op")["controller"]["selection_verification"]["choices"][0]
    assert selected["requirements"] == {"material": "wood"} and selected["avoid"] == {"condition": "used"}


def test_selection_refresh_cursor_survives_failure_after_reusable_evidence_commit(store, monkeypatch):
    from datetime import datetime, timedelta, timezone

    products, shopping, verifier = service(store, [[hit(1)], [], []])
    selected = products.search({"category": "chair", "room_id": "r"}, "source")["displayed_choices"]
    with store.transaction():
        offer = store.get("offers", selected[0]["offer_id"])
        offer["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        store.put("offers", offer["offer_id"], offer)
    context = {"room_id": "r", "operation_id": "op"}
    products.verify_selection(selected, "500.00", bounded=True, verification_id="check", context=context)
    original_put = store.put
    failed = False
    def interrupted_cursor(kind, record_id, payload):
        nonlocal failed
        work = payload.get("cursor", {}).get("evidence_search", {}).get("verification_work", {})
        # Fail the cursor-only transaction after the reusable evidence transaction.
        if kind == "selection_verifications" and work.get("listing_index") == 1 and store.depth == 1 and not failed:
            failed = True
            raise RuntimeError("Worker stopped before standalone cursor commit")
        return original_put(kind, record_id, payload)
    monkeypatch.setattr(store, "put", interrupted_cursor)
    with pytest.raises(RuntimeError):
        products.verify_selection(selected, "500.00", bounded=True, verification_id="check", context=context)
    assert len(verifier.calls) == 2
    assert store.get("selection_verifications", "check")["cursor"]["evidence_search"]["verification_work"]["listing_index"] == 1
    restarted = ProductService(store, shopping, verifier, products.ranker)
    for _ in range(20):
        result = restarted.verify_selection(selected, "500.00", bounded=True, verification_id="check", context=context)
        if result["state"] == "completed":
            break
    assert result["state"] == "completed" and len(verifier.calls) == 2
