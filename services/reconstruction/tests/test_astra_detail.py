import copy
import json

import numpy as np
import open3d as o3d
import pytest

from respace_reconstruction import astra, astra_detail, astra_room, astra_spending
from respace_reconstruction.astra_spending import Spending, BudgetExhausted
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import digest
from test_astra_room import room_plan
from test_walkthrough import room_capture


def reply(data, inputs=1000, outputs=1000):
    return {"status": "completed", "service_tier": "default", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(data)}]}],
        "usage": {"input_tokens": inputs, "output_tokens": outputs,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}}


def detailed_reply():
    entity = copy.deepcopy(room_plan()["entities"][0])
    entity["evidence_frame_ids"] = ["frame-0"]
    entity["parts"][0]["material_id"] = "wood"
    entity["parts"][1]["material_id"] = "cloth"
    # Exercise shaped parts and material slots within the recognition profile.
    for i in range(6):
        part = copy.deepcopy(entity["parts"][0])
        part["center"] = {"x": -.3+i*.04, "y": .2, "z": -.5}
        part["size"] = {"x": .02, "y": .2, "z": .02}
        entity["parts"].append(part)
    return reply({"objects": [{"entity": entity, "materials": [
        {"id": "wood", "color": {"r": .4, "g": .3, "b": .2}, "roughness": .45, "metallic": 0., "texture_family": "wood"},
        {"id": "cloth", "color": {"r": .8, "g": .15, "b": .1}, "roughness": .9, "metallic": 0., "texture_family": "fabric"}]}]})


def configure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 1000)


def test_staged_default_uses_semantic_models_without_detail_photos_and_keeps_receipts(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    calls = []
    def generate(body, key):
        calls.append(body)
        return reply(room_plan()) if len(calls) == 1 else detailed_reply()
    monkeypatch.setattr(astra, "call_astra", generate)
    result = astra_room.process_astra_room(tmp_path, 1)
    output = tmp_path/"results/1"
    bundle = SceneBundle.model_validate_json((output/"scene.json").read_text())
    bundle.validate_files(output, {a["filename"] for a in result["assets"]})
    quality = json.loads((output/"quality.json").read_text())
    assert len(calls) == 2
    assert "INVENTORY stage" in calls[0]["instructions"]
    assert all(call["reasoning"]["effort"] == "high" for call in calls)
    assert calls[1]["text"]["format"]["name"] == "respace_object_batch"
    context = json.loads(calls[1]["input"][0]["content"][0]["text"])["objects"][0]
    assert context["entity"]["model_description"] == room_plan()["entities"][0]["model_description"]
    assert "selected_photos" not in context and "observed_mesh_region" not in context
    assert any(c["type"] == "input_image" for c in calls[0]["input"][0]["content"])
    assert all(c["type"] == "input_text" for c in calls[1]["input"][0]["content"])
    assert quality["budget"]["ceiling_usd"] == 10.
    assert quality["budget"]["known_cost_usd"] == .024
    assert quality["objects"][0]["detail"] == "detailed"
    saved = json.loads((output/"astra-furnishings.json").read_text())
    assert len(saved["entities"][0]["parts"]) == 8
    assert "material_id" in saved["entities"][0]["parts"][0]
    assert any("metallic" in material for material in saved["materials"])
    chair = next(e for e in bundle.entities if e.id == "chair")
    assert len(chair.material_ids) >= 2
    assert len({m.roughness for m in bundle.materials if m.owner_id == "chair"}) == 2
    assert quality["geometry_profile"] == "semantic_object_models"
    assert "map_Kd material-v1-wood-color.png" in (output/"entity_chair.mtl").read_text()
    assert "map_Kd material-v1-fabric-color.png" in (output/"entity_chair.mtl").read_text()
    assert quality["material_textures"]["textured_entity_count"] == len(bundle.entities)
    assert "vt " in (output/"entity_chair.obj").read_text()
    assert not list(output.glob("*.jpg"))
    for asset in result["assets"]:
        assert digest(output/asset["filename"]) == asset["sha256"]
    assert (tmp_path/"work/sol-v1/inventory/response.json").exists()
    assert len(list((tmp_path/"work/sol-v1/batches").glob("*/response.json"))) == 1
    # A new result revision reuses paid checkpoints and the durable ledger.
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 2
    repeated = json.loads((tmp_path/"results/2/quality.json").read_text())
    assert repeated["response_reused"] and repeated["budget"]["known_cost_usd"] == .024


def test_budget_limit_keeps_complete_coarse_object_instead_of_dropping_furniture(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    counts = iter([1000, 3000000])
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: next(counts))
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or reply(room_plan()))
    result = astra_room.process_astra_room(tmp_path, 1)
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    scene = json.loads((tmp_path/"results/1/scene.json").read_text())
    assert result["status"] == "succeeded" and len(calls) == 1
    assert report["objects"][0]["reason"] == "budget_limit"
    assert any(e["id"] == "chair" for e in scene["entities"])


@pytest.mark.parametrize("fault", ["incomplete", "wrong_id", "wrong_pose", "out_of_bounds", "vertical_contact", "material", "degenerate"])
def test_failed_object_does_not_discard_other_paid_work_or_repeat_it(tmp_path, monkeypatch, fault):
    room_capture(tmp_path)
    configure(monkeypatch)
    response = detailed_reply()
    batch_data = json.loads(response["output"][0]["content"][0]["text"])
    data = batch_data["objects"][0]
    if fault == "incomplete":
        response["status"] = "incomplete"
    else:
        if fault == "wrong_id": data["entity"]["id"] = "different-object"
        elif fault == "wrong_pose": data["entity"]["position"]["x"] += 1.
        elif fault == "out_of_bounds": data["entity"]["parts"][0]["size"]["x"] = 10.
        elif fault == "vertical_contact":
            for part in data["entity"]["parts"]:
                part["center"]["y"] += .03
        elif fault == "material": data["entity"]["parts"][0]["material_id"] = "missing"
        else:
            data["entity"]["parts"][0] = {
                "shape": "mesh", "material_id": "wood", "center": {"x": 0., "y": 0., "z": 0.},
                "size": {"x": 1., "y": 1., "z": 1.}, "yaw": 0.,
                "vertices": [{"x": 0., "y": 0., "z": 0.}]*3,
                "triangles": [{"a": 0, "b": 1, "c": 2}]}
        response["output"][0]["content"][0]["text"] = json.dumps(batch_data)
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or (reply(room_plan()) if len(calls) == 1 else response))
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    assert report["objects"][0]["detail"] == "coarse"
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 2


def test_invalid_inventory_contacts_stop_before_paid_detail_requests(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = room_plan()
    inventory["entities"][0]["position"]["y"] = .05
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or reply(inventory))
    with pytest.raises(ValueError, match="Floor-mounted"):
        astra_room.process_astra_room(tmp_path, 1)
    assert len(calls) == 1
    assert (tmp_path/"work/sol-v1/inventory/response.json").exists()
    assert not (tmp_path/"results/1").exists()


def test_unknown_billing_stops_room_and_survives_a_processing_retry(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    calls = []
    def generate(*args):
        calls.append(1)
        if len(calls) > 1: raise RuntimeError("network interrupted")
        return reply(room_plan())
    monkeypatch.setattr(astra, "call_astra", generate)
    with pytest.raises(RuntimeError, match="interrupted"):
        astra_room.process_astra_room(tmp_path, 1)
    with pytest.raises(RuntimeError, match="unknown billing"):
        astra_room.process_astra_room(tmp_path, 2)
    assert len(calls) == 2
    ledger = Spending(tmp_path/"work/astra-budget-v3.json")
    assert ledger.allocated > 12000
    assert not (tmp_path/"results/1").exists()


def inventory_with_objects(count):
    inventory = room_plan()
    original = inventory["entities"][0]
    inventory["entities"] = []
    for index in range(count):
        entity = copy.deepcopy(original)
        entity["id"] = f"chair-{index}"
        entity["position"]["x"] = -.9+(index % 3)*.9
        entity["position"]["z"] = -.6+(index // 3)*.9
        for part in entity["parts"]:
            for axis in ("x", "y", "z"):
                part["center"][axis] *= .45
                part["size"][axis] *= .45
        inventory["entities"].append(entity)
    return inventory


def batch_for_request(body):
    contexts = json.loads(body["input"][0]["content"][0]["text"])["objects"]
    objects = []
    for context in contexts:
        entity = copy.deepcopy(context["entity"])
        for part in entity["parts"]:
            part["material_id"] = entity["material_id"]
        objects.append({"entity": entity, "materials": [dict(context["materials"][0], metallic=0.)]})
    return reply({"objects": objects})


def test_completed_batch_checkpoint_survives_interruption_on_later_batch(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = inventory_with_objects(5)
    calls = []
    def generate(body, key):
        calls.append(body)
        if len(calls) == 1: return reply(inventory)
        if len(calls) > 2: raise RuntimeError("interrupted on second batch")
        return batch_for_request(body)
    monkeypatch.setattr(astra, "call_astra", generate)
    with pytest.raises(RuntimeError, match="interrupted"):
        astra_room.process_astra_room(tmp_path, 1)
    assert len(list((tmp_path/"work/sol-v1/batches").glob("*/response.json"))) == 1
    with pytest.raises(RuntimeError, match="unknown billing"):
        astra_room.process_astra_room(tmp_path, 2)
    assert len(calls) == 3


def body():
    return {"model": "gpt-6-astra", "service_tier": "default", "instructions": "test", "input": "test",
            "max_output_tokens": 24000}


def test_spending_reserves_highest_input_rate_and_full_output_before_call(tmp_path, monkeypatch):
    configure(monkeypatch)
    ledger = Spending(tmp_path/"budget.json")
    def generate(*args):
        saved = json.loads((tmp_path/"budget.json").read_text())
        entry = next(iter(saved["entries"].values()))
        assert entry["state"] == "reserved"
        assert entry["reserved_units"] == (1010+256)*12.5+24000*50
        return reply({}, outputs=1000)
    monkeypatch.setattr(astra, "call_astra", generate)
    ledger.request(body(), tmp_path/"call", "test")
    assert ledger.report()["known_cost_usd"] == .06
    ledger.request(body(), tmp_path/"call", "test")
    assert len(ledger.data["entries"]) == 1


def test_input_token_count_failure_and_over_budget_call_never_generate(tmp_path, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(astra, "call_astra", lambda *args: pytest.fail("Unexpected paid request"))
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 500000)
    ledger = Spending(tmp_path/"budget.json")
    with pytest.raises(BudgetExhausted): ledger.request(body(), tmp_path/"call", "test")
    assert not ledger.data["entries"]
    def failed(*args): raise RuntimeError("count unavailable")
    monkeypatch.setattr(astra_spending, "count_input_tokens", failed)
    with pytest.raises(RuntimeError, match="count unavailable"): ledger.request(body(), tmp_path/"call", "test")
    assert not ledger.data["entries"]


def test_response_saved_before_crash_can_settle_without_repayment(tmp_path, monkeypatch):
    configure(monkeypatch)
    ledger = Spending(tmp_path/"budget.json")
    monkeypatch.setattr(astra, "call_astra", lambda *args: reply({}))
    original = ledger.settle
    monkeypatch.setattr(ledger, "settle", lambda *args: (_ for _ in ()).throw(RuntimeError("crash before receipt")))
    with pytest.raises(RuntimeError): ledger.request(body(), tmp_path/"call", "test")
    monkeypatch.setattr(astra, "call_astra", lambda *args: pytest.fail("Repaid a received response"))
    recovered = Spending(tmp_path/"budget.json")
    _, reused = recovered.request(body(), tmp_path/"call", "test")
    assert reused and recovered.report()["known_cost_usd"] == .06


def test_semantic_detail_can_use_twenty_parts_without_source_photo_access(tmp_path, monkeypatch):
    inventory = astra_room.FurnishingPlan.model_validate(room_plan())
    original = inventory.entities[0]
    context = astra_detail.object_evidence(original, inventory, o3d)
    response = detailed_reply()
    data = json.loads(response["output"][0]["content"][0]["text"])["objects"][0]
    while len(data["entity"]["parts"]) < 20:
        data["entity"]["parts"].append(copy.deepcopy(data["entity"]["parts"][-1]))
    parsed = astra_detail.parse_detail(reply(data), original, context, o3d)
    assert len(parsed.entity.parts) == 20
    body = astra_detail.detail_body([context])
    assert len(body["input"][0]["content"]) == 1
    assert body["max_output_tokens"] == 28000
    data["entity"]["parts"].append(copy.deepcopy(data["entity"]["parts"][-1]))
    with pytest.raises(ValueError):
        astra_detail.parse_detail(reply(data), original, context, o3d)


@pytest.mark.parametrize("count", [4, 5, 8])
def test_multiple_objects_share_text_only_calls_and_keep_separate_identity_and_materials(tmp_path, monkeypatch, count):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = inventory_with_objects(count)
    calls = []
    def generate(body, key):
        calls.append(body)
        if len(calls) == 1:
            return reply(inventory)
        assert body["model"] == "gpt-6-sol" and body["reasoning"]["effort"] == "high"
        context = json.loads(body["input"][0]["content"][0]["text"])["objects"]
        assert 1 <= len(context) <= 4
        assert all(item["entity"]["model_description"] for item in context)
        assert all("selected_photos" not in item for item in context)
        assert all(c["type"] == "input_text" for c in body["input"][0]["content"])
        response = batch_for_request(body)
        data = json.loads(response["output"][0]["content"][0]["text"])
        data["objects"].reverse()  # IDs, rather than array order, bind results.
        response["output"][0]["content"][0]["text"] = json.dumps(data)
        return response
    monkeypatch.setattr(astra, "call_astra", generate)
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    quality = json.loads((tmp_path/"results/1/quality.json").read_text())
    saved = json.loads((tmp_path/"results/1/astra-furnishings.json").read_text())
    assert len(calls) == 1+(count+3)//4
    assert quality["batch_count"] == (count+3)//4 and quality["batch_size"] == 4
    assert all(item["detail"] == "detailed" for item in quality["objects"])
    assert {e["id"]: e["position"] for e in saved["entities"]} == {e["id"]: e["position"] for e in inventory["entities"]}
    assert len({e["material_id"] for e in saved["entities"]}) == count
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 1+(count+3)//4


@pytest.mark.parametrize("fault", ["invalid_material", "missing_item"])
def test_one_bad_batch_item_keeps_valid_siblings(tmp_path, monkeypatch, fault):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = inventory_with_objects(3)
    calls = []
    bad_id = []
    def generate(body, key):
        calls.append(body)
        if len(calls) == 1:
            return reply(inventory)
        response = batch_for_request(body)
        data = json.loads(response["output"][0]["content"][0]["text"])
        bad_id.append(data["objects"][0]["entity"]["id"])
        if fault == "missing_item":
            data["objects"].pop(0)
        else:
            data["objects"][0]["entity"]["parts"][0]["material_id"] = "missing"
        response["output"][0]["content"][0]["text"] = json.dumps(data)
        return response
    monkeypatch.setattr(astra, "call_astra", generate)
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    quality = json.loads((tmp_path/"results/1/quality.json").read_text())
    status = {o["entity_id"]: o["detail"] for o in quality["objects"]}
    assert status.pop(bad_id[0]) == "coarse" and set(status.values()) == {"detailed"}
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded" and len(calls) == 2


def test_budget_exhaustion_stops_preparing_further_batches(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = inventory_with_objects(5)
    counts = iter([1000, 3000000])
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: next(counts))
    calls, prepared = [], []
    original = astra_detail.object_evidence
    def prepare(entity, *args):
        prepared.append(entity.id)
        return original(entity, *args)
    monkeypatch.setattr(astra_detail, "object_evidence", prepare)
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or reply(inventory))
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    quality = json.loads((tmp_path/"results/1/quality.json").read_text())
    assert len(calls) == 1 and len(prepared) == 4
    assert len(quality["objects"]) == 5
    assert all(o["reason"] == "budget_limit" for o in quality["objects"])


def test_sol_spending_preserves_old_astra_receipts_and_reserves_at_sol_rates(tmp_path, monkeypatch):
    configure(monkeypatch)
    ledger = Spending(tmp_path/"budget.json")
    monkeypatch.setattr(astra, "call_astra", lambda *args: reply({}))
    ledger.request(body(), tmp_path/"old-call", "Old Astra")
    entry = next(iter(ledger.data["entries"].values()))
    entry.pop("model")  # Simulate a pre-migration receipt.
    ledger.save()
    ledger = Spending(tmp_path/"budget.json")
    ledger.request(body(), tmp_path/"old-call", "Old Astra")
    sol = dict(body(), model="gpt-6-sol")
    def generate(*args):
        retained = json.loads((tmp_path/"budget.json").read_text())
        latest = next(entry for entry in retained["entries"].values() if entry.get("model") == "gpt-6-sol")
        assert latest["reserved_units"] == (1010+256)*2.5+24000*10
        return reply({})
    monkeypatch.setattr(astra, "call_astra", generate)
    ledger.request(sol, tmp_path/"sol-call", "Sol")
    assert ledger.report()["known_cost_usd"] == .072
    assert ledger.report()["paid_call_count"] == 2


@pytest.mark.parametrize("model,expected", [("gpt-6-astra", 7532000), ("gpt-6-sol", 1506400)])
def test_model_specific_long_context_cache_and_output_rates(model, expected):
    response = reply({}, inputs=300000, outputs=20000)
    response["usage"]["input_tokens_details"] = {"cached_tokens": 1000, "cache_write_tokens": 10000}
    assert astra_spending.actual_units(response, model) == expected


def test_inventory_fits_remaining_budget_by_reducing_unused_output_allowance(tmp_path, monkeypatch):
    configure(monkeypatch)
    ledger = Spending(tmp_path/"budget.json")
    # Retained Sol receipt and input count from the failed scan.
    ledger.data["entries"]["prior-sol"] = {
        "state": "settled", "model": "gpt-6-sol", "reserved_units": 1800000,
        "cost_units": 1484582}
    ledger.save()
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 283324)
    calls = []
    def generate(request, key):
        calls.append(request)
        assert 16000 <= request["max_output_tokens"] < 24000
        assert ledger.allocated <= 10000000
        return reply({}, inputs=283324, outputs=4531)
    monkeypatch.setattr(astra, "call_astra", generate)
    ledger.request(body(), tmp_path/"inventory", "Room contents inventory")
    assert len(calls) == 1
    ledger.request(body(), tmp_path/"inventory", "Room contents inventory")
    assert len(calls) == 1


def test_unaffordable_first_request_explains_reservation_without_claiming_spend(tmp_path, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 500000)
    monkeypatch.setattr(astra, "call_astra", lambda *args: pytest.fail("Unexpected paid request"))
    ledger = Spending(tmp_path/"budget.json")
    with pytest.raises(BudgetExhausted, match="Room contents inventory was not started") as error:
        ledger.request(body(), tmp_path/"inventory", "Room contents inventory")
    assert "$0.00 already recorded" in str(error.value)
    assert "No generation charge was initiated" in str(error.value)
    assert ledger.allocated == 0 and not ledger.data["entries"]
    preflight = json.loads((tmp_path/"inventory/budget-preflight.json").read_text())
    assert preflight["remaining_usd"] == 10 and preflight["input_tokens"] == 500000


def test_fresh_run_does_not_reuse_old_responses_or_budget_and_retry_reuses_new_run(tmp_path, monkeypatch):
    import uuid
    room_capture(tmp_path)
    configure(monkeypatch)
    calls = []
    def generate(body, key):
        calls.append(body)
        return reply(room_plan()) if "INVENTORY stage" in body["instructions"] else detailed_reply()
    monkeypatch.setattr(astra, "call_astra", generate)
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    assert len(calls) == 2
    prior_response = (tmp_path/"work/sol-v1/inventory/response.json").read_bytes()
    ledger = Spending(tmp_path/"work/astra-budget-v3.json")
    ledger.data["entries"]["unknown-old-call"] = {"state":"reserved", "reserved_units":9000000}
    ledger.save()
    prior_budget = ledger.path.read_bytes()
    first = str(uuid.uuid4())
    monkeypatch.setenv("RESPACE_PIPELINE", "astra")
    from respace_reconstruction.pipeline import process
    assert process(tmp_path, 2, generation_id=first)["status"] == "succeeded"
    assert len(calls) == 4
    fresh = json.loads((tmp_path/"results/2/quality.json").read_text())
    assert fresh["budget"]["paid_call_count"] == 2 and fresh["budget"]["known_cost_usd"] == .024
    assert not fresh["response_reused"]
    assert (tmp_path/"work/runs"/first/"astra-budget-v3.json").exists()
    assert astra_room.process_astra_room(tmp_path, 3, generation_id=first)["status"] == "succeeded"
    assert len(calls) == 4
    second = str(uuid.uuid4())
    assert astra_room.process_astra_room(tmp_path, 4, generation_id=second)["status"] == "succeeded"
    assert len(calls) == 6
    assert ledger.path.read_bytes() == prior_budget
    assert (tmp_path/"work/sol-v1/inventory/response.json").read_bytes() == prior_response
    assert (tmp_path/"results/1/completion.json").exists()
