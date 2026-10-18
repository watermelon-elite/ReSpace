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
    entity["parts"][0]["material_id"] = "wood"
    entity["parts"][1]["material_id"] = "cloth"
    # Exercise the >12-part detail path, beyond the old coarse-scene schema.
    for i in range(14):
        part = copy.deepcopy(entity["parts"][0])
        part["center"] = {"x": -.3+i*.04, "y": .2, "z": -.5}
        part["size"] = {"x": .02, "y": .2, "z": .02}
        entity["parts"].append(part)
    return reply({"entity": entity, "photo_exclusions": [], "materials": [
        {"id": "wood", "color": {"r": .4, "g": .3, "b": .2}, "roughness": .45, "metallic": 0.},
        {"id": "cloth", "color": {"r": .8, "g": .15, "b": .1}, "roughness": .9, "metallic": 0.}]})


def configure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 1000)


def test_staged_default_generates_objects_independently_with_photos_materials_and_receipts(tmp_path, monkeypatch):
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
    assert calls[1]["text"]["format"]["name"] == "respace_detailed_object"
    context = json.loads(calls[1]["input"][0]["content"][0]["text"])
    assert "observed_mesh_region" in context and "crop_pixels_left_top_right_bottom" in context["selected_photos"][0]
    assert quality["budget"]["ceiling_usd"] == 10.
    assert quality["budget"]["known_cost_usd"] == .12
    assert quality["objects"][0]["detail"] == "detailed"
    saved = json.loads((output/"astra-furnishings.json").read_text())
    assert len(saved["entities"][0]["parts"]) == 16
    assert "material_id" in saved["entities"][0]["parts"][0]
    assert any("metallic" in material for material in saved["materials"])
    chair = next(e for e in bundle.entities if e.id == "chair")
    assert len(chair.material_ids) >= 2
    assert len({m.roughness for m in bundle.materials if m.owner_id == "chair"}) == 2
    assert quality["photo_textures"][0]["photo_surface_fraction"] > 0
    assert "map_Kd photo-" in (output/"entity_chair.mtl").read_text()
    assert "vt " in (output/"entity_chair.obj").read_text()
    for asset in result["assets"]:
        assert digest(output/asset["filename"]) == asset["sha256"]
    assert (tmp_path/"work/astra-v3/inventory/response.json").exists()
    assert (tmp_path/"work/astra-v3/chair/response.json").exists()
    # A new result revision reuses paid checkpoints and the durable ledger.
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 2
    repeated = json.loads((tmp_path/"results/2/quality.json").read_text())
    assert repeated["response_reused"] and repeated["budget"]["known_cost_usd"] == .12


def test_budget_limit_keeps_complete_coarse_object_instead_of_dropping_furniture(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    counts = iter([1000, 1000000])
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: next(counts))
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or reply(room_plan()))
    result = astra_room.process_astra_room(tmp_path, 1)
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    scene = json.loads((tmp_path/"results/1/scene.json").read_text())
    assert result["status"] == "succeeded" and len(calls) == 1
    assert report["objects"][0]["reason"] == "budget_limit"
    assert any(e["id"] == "chair" for e in scene["entities"])


@pytest.mark.parametrize("fault", ["incomplete", "wrong_id", "wrong_pose", "out_of_bounds", "material", "degenerate"])
def test_failed_object_does_not_discard_other_paid_work_or_repeat_it(tmp_path, monkeypatch, fault):
    room_capture(tmp_path)
    configure(monkeypatch)
    response = detailed_reply()
    data = json.loads(response["output"][0]["content"][0]["text"])
    if fault == "incomplete":
        response["status"] = "incomplete"
    else:
        if fault == "wrong_id": data["entity"]["id"] = "different-object"
        elif fault == "wrong_pose": data["entity"]["position"]["x"] += 1.
        elif fault == "out_of_bounds": data["entity"]["parts"][0]["size"]["x"] = 10.
        elif fault == "material": data["entity"]["parts"][0]["material_id"] = "missing"
        else:
            data["entity"]["parts"][0] = {
                "shape": "mesh", "material_id": "wood", "center": {"x": 0., "y": 0., "z": 0.},
                "size": {"x": 1., "y": 1., "z": 1.}, "yaw": 0.,
                "vertices": [{"x": 0., "y": 0., "z": 0.}]*3,
                "triangles": [{"a": 0, "b": 1, "c": 2}]}
        response["output"][0]["content"][0]["text"] = json.dumps(data)
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or (reply(room_plan()) if len(calls) == 1 else response))
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    assert report["objects"][0]["detail"] == "coarse"
    assert astra_room.process_astra_room(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 2


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
    assert ledger.allocated > 60000
    assert not (tmp_path/"results/1").exists()


def test_completed_object_checkpoint_survives_an_interruption_on_another_item(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    inventory = room_plan()
    first = inventory["entities"][0]
    first["position"]["x"] = -.6
    second = copy.deepcopy(first)
    second["id"] = "chair-second"; second["position"]["x"] = .8
    inventory["entities"].append(second)
    calls = []
    def generate(body, key):
        calls.append(body)
        if len(calls) == 1: return reply(inventory)
        if len(calls) > 2: raise RuntimeError("interrupted on second object")
        context = json.loads(body["input"][0]["content"][0]["text"])
        response = detailed_reply()
        data = json.loads(response["output"][0]["content"][0]["text"])
        for field in ("id", "position", "yaw", "kind", "category", "support_id"):
            data["entity"][field] = context["entity"][field]
        response["output"][0]["content"][0]["text"] = json.dumps(data)
        return response
    monkeypatch.setattr(astra, "call_astra", generate)
    with pytest.raises(RuntimeError, match="interrupted"):
        astra_room.process_astra_room(tmp_path, 1)
    assert len(list((tmp_path/"work/astra-v3").glob('chair*/response.json'))) == 1
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


def test_photo_exclusions_prevent_clutter_baking_without_removing_geometry(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configure(monkeypatch)
    response = detailed_reply()
    data = json.loads(response["output"][0]["content"][0]["text"])
    data["photo_exclusions"] = [{"frame_id": "frame-"+str(i), "polygons": [[
        {"u": 0., "v": 0.}, {"u": 1., "v": 0.}, {"u": 1., "v": 1.}, {"u": 0., "v": 1.}]]} for i in range(5)]
    response["output"][0]["content"][0]["text"] = json.dumps(data)
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(1) or (reply(room_plan()) if len(calls) == 1 else response))
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    assert report["objects"][0]["detail"] == "detailed"
    assert report["photo_textures"][0]["photo_surface_fraction"] == 0
    assert "map_Kd" not in (tmp_path/"results/1/entity_chair.mtl").read_text()
