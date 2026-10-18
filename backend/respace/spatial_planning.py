"""Gemini proposes relationships; independent validation controls every accepted action."""

import asyncio
from copy import deepcopy
from decimal import InvalidOperation
import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .categories import CATEGORIES, SUPPORT_CATEGORIES
from .solver import _room, _target_id, _anchor_target_ids, solve


class PlanningFailure(Exception):
    def __init__(self, code, message, diagnostics=None):
        super().__init__(message)
        self.code, self.diagnostics = code, diagnostics or []


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class EntityRef(Record):
    kind: Literal["object", "item", "addition_unit"]
    id: str
    add_id: str | None = None
    unit_index: int | None = Field(default=None, ge=0)


class Anchor(Record):
    type: Literal["against_wall", "corner", "under", "next_to", "facing", "in_front_of_window", "room_center", "on_wall", "on_top_of"]
    wall_id: str | None = None
    alignment: Literal["left", "center", "right"] | None = None
    offset: float | None = Field(default=None, ge=0)
    corner_id: str | None = None
    target: EntityRef | None = None
    side: Literal["left", "right", "front"] | None = None
    distance: float | None = Field(default=None, gt=0)
    opening_id: str | None = None
    height: float | None = Field(default=None, gt=0)
    alternatives: list["Anchor"] = Field(default_factory=list)


class PlanMove(Record):
    action_id: str
    target: EntityRef
    anchor: Anchor
    reason: str


class PlanRemove(Record):
    action_id: str
    target: EntityRef
    reason: str


class PlanReplace(Record):
    action_id: str
    target_item_id: str
    selection_id: str
    reason: str


class PlanRestore(Record):
    action_id: str
    removed_item_id: str
    reason: str


class PlanUnlock(Record):
    action_id: str
    target: EntityRef
    explicit_user_unlock_context: str
    reason: str


class Addition(Record):
    add_id: str
    action_id: str
    category: str
    priority: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0, le=100)
    anchor: Anchor
    selection_id: str
    reason: str


class DesignPlan(Record):
    summary: str
    decision_revision: int | None = Field(default=None, ge=0)
    base: dict | None = None
    moves: list[PlanMove] = Field(default_factory=list)
    removes: list[PlanRemove] = Field(default_factory=list)
    adds: list[Addition] = Field(default_factory=list)
    replaces: list[PlanReplace] = Field(default_factory=list)
    restores: list[PlanRestore] = Field(default_factory=list)
    unlocks: list[PlanUnlock] = Field(default_factory=list)


_ACTIONS: dict[str, type[Record]] = {"moves": PlanMove, "removes": PlanRemove, "adds": Addition,
            "replaces": PlanReplace, "restores": PlanRestore, "unlocks": PlanUnlock}


def _anchor_valid(anchor, category, room, targets):
    kind = anchor["type"]
    allowed = {"type", "alternatives"}
    for alternative in anchor.get("alternatives", []):
        if alternative.get("alternatives"):
            raise ValueError("Alternative Anchors cannot contain more alternatives.")
        _anchor_valid(alternative, category, room, targets)
    if kind in ("against_wall", "on_wall"):
        allowed |= {"wall_id", "alignment", "offset"}
        wall = next((w for w in room["walls"] if w["id"] == anchor.get("wall_id")), None)
        if not wall or wall["virtual"] or not anchor.get("alignment"):
            raise ValueError("Anchor needs a real wall and alignment.")
        if kind == "on_wall":
            allowed.add("height")
            if CATEGORIES[category]["mount"] != "wall":
                raise ValueError("Category does not support a wall Mount.")
        elif CATEGORIES[category]["mount"] in ("wall", "ceiling"):
            raise ValueError("Category needs its explicit non-floor Mount.")
    elif kind == "corner":
        allowed.add("corner_id")
        if not any(c["id"] == anchor.get("corner_id") for c in room["corners"]):
            raise ValueError("Unknown real corner.")
    elif kind == "in_front_of_window":
        allowed.add("opening_id")
        if not any(o["id"] == anchor.get("opening_id") and o["type"] == "window" for o in room["openings"]):
            raise ValueError("Unknown window identity.")
    elif kind in ("under", "next_to", "facing", "on_top_of"):
        allowed.add("target")
        target = anchor.get("target")
        key = _target_id(target)
        if not key or key not in targets:
            raise ValueError("Anchor references an unknown or inactive target.")
        if kind == "under" and category != "rug":
            raise ValueError("Only rugs may use under.")
        if kind == "next_to":
            allowed.add("side")
            if not anchor.get("side"):
                raise ValueError("next_to requires a side.")
        if kind == "facing":
            allowed.add("distance")
        if kind == "on_top_of" and targets[key]["category"] not in SUPPORT_CATEGORIES:
            raise ValueError("Target is not a valid support category.")
    if any(key not in allowed and value is not None for key, value in anchor.items()):
        raise ValueError("Anchor contains fields incompatible with its type.")
    if kind not in ("on_wall", "on_top_of") and CATEGORIES[category]["mount"] in ("wall", "ceiling"):
        raise ValueError("Non-floor category requires a supported explicit Mount Anchor.")


def validate_plan(raw, room_snapshot, selections, constraints, base_scene=None):
    room = _room(room_snapshot)
    diagnostics: list[dict[str, Any]] = []
    accepted: dict[str, list[dict[str, Any]]] = {key: [] for key in _ACTIONS}
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), str):
        raise PlanningFailure("malformed_plan", "Spatial plan must be a structured object with a summary.")
    if raw.get("schema_version", 1) != 1 or set(raw) - {"schema_version", "summary", "decision_revision", "base", *_ACTIONS}:
        raise PlanningFailure("malformed_plan", "Spatial plan contains unsupported top-level fields.")
    objects = {obj["id"]: obj for obj in room["objects"]}
    base_items = {i["id"]: i for i in (base_scene or {}).get("items", [])}
    targets = {f"i_{key}": obj for key, obj in objects.items()} if base_scene is None else {}
    targets.update({key: value for key,value in base_items.items() if value.get("status") != "removed"})
    parsed: dict[str, list[dict[str, Any]]] = {}
    total = 0
    action_ids, add_ids = set(), set()
    for group, model in _ACTIONS.items():
        entries = raw.get(group, [])
        if not isinstance(entries, list):
            raise PlanningFailure("malformed_plan", f"{group} must be an array.")
        total += len(entries)
        parsed[group] = []
        for entry in entries:
            try:
                value = model.model_validate(entry).model_dump(exclude_none=True)
                action_id = value["action_id"]
                if not action_id or action_id in action_ids:
                    raise ValueError("Action identity is empty or repeated.")
                action_ids.add(action_id)
                if group == "adds":
                    if not value["add_id"] or value["add_id"] in add_ids:
                        raise ValueError("Addition identity is empty or repeated.")
                    add_ids.add(value["add_id"])
                    if value["category"] not in CATEGORIES:
                        raise ValueError("Unknown category.")
                    for unit in range(value["quantity"]):
                        key = f"i_{value['add_id']}_{unit}"
                        if key in targets:
                            raise ValueError("Addition identity already exists in the candidate.")
                        targets[key] = value
                parsed[group].append(value)
            except (ValidationError, TypeError, ValueError) as exc:
                diagnostics.append({"code": "invalid_plan_entry", "group": group,
                    "action_id": entry.get("action_id") if isinstance(entry, dict) else None,
                    "reason": str(exc) if not isinstance(exc, ValidationError) else "Entry does not match its typed action contract."})
    targets.update({e["removed_item_id"]: base_items[e["removed_item_id"]] for e in parsed["restores"]
                    if e["removed_item_id"] in base_items and base_items[e["removed_item_id"]].get("status") == "removed"})
    explicit_unlock_targets = {_target_id(e["target"]) for e in parsed["unlocks"]
        if e["explicit_user_unlock_context"] and (e["target"]["id"] in constraints.get("explicit_unlock_ids", []) or _target_id(e["target"]) in constraints.get("explicit_unlock_ids", []))}
    for group, entries in parsed.items():
        for entry in entries:
            try:
                if group != "adds" and constraints.get("intent", "add") == "add":
                    raise ValueError("Add intent preserves all existing Objects.")
                selection_id = entry.get("selection_id")
                if selection_id:
                    selection = selections.get(selection_id)
                    if not selection or selection.get("dimension_evidence", {}).get("outcome") != "verified":
                        raise ValueError("Unknown or unverified selection_id.")
                    if group == "adds" and selection["category"] != entry["category"]:
                        raise ValueError("Addition category differs from the verified selection.")
                    if group == "adds" and selection.get("quantity") is not None and selection["quantity"] != entry["quantity"]:
                        raise ValueError("Addition quantity differs from finalized physical quantity.")
                if group == "adds":
                    category = entry["category"]
                elif group == "replaces":
                    target = base_items.get(entry["target_item_id"])
                    if not target or target.get("status") == "removed":
                        raise ValueError("Replacement target is not active.")
                    category = target["category"]
                    if selections[selection_id]["category"] != category:
                        raise ValueError("Replacement category is incompatible with its target.")
                    if target.get("fixed_in_place") or ((target.get("instruction") == "keep" or constraints.get("instructions", {}).get(target.get("object_id") or target["id"]) == "keep") and target["id"] not in explicit_unlock_targets):
                        raise ValueError("Protected target cannot be replaced.")
                elif group == "restores":
                    target = base_items.get(entry["removed_item_id"])
                    if not target or target.get("status") != "removed":
                        raise ValueError("Restore requires a retained removed Item.")
                    category = target["category"]
                else:
                    ref = entry["target"]
                    target = targets.get(_target_id(ref))
                    if not target:
                        raise ValueError("Unknown target identity.")
                    category = target["category"]
                    instruction = constraints.get("instructions", {}).get(target.get("object_id") or ref["id"], target.get("instruction", "decide"))
                    if target.get("fixed_in_place"):
                        raise ValueError("Permanent fixture cannot be changed or unlocked.")
                    if group == "unlocks":
                        if _target_id(ref) not in explicit_unlock_targets:
                            raise ValueError("Unlock requires the explicit user context.")
                    elif instruction == "keep" and _target_id(ref) not in explicit_unlock_targets:
                        raise ValueError("Kept target requires an explicit unlock.")
                if "anchor" in entry:
                    _anchor_valid(entry["anchor"], category, room, targets)
                accepted[group].append(entry)
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append({"code": "invalid_plan_entry", "group": group,
                                    "action_id": entry["action_id"], "reason": str(exc)})
    # Drop dependents of failed/removed targets, and reject cycles before solver dispatch.
    rejected = set()
    removed = {_target_id(e["target"]) for e in accepted["removes"]}
    addition_targets = {f"i_{e['add_id']}_{unit}": e["action_id"] for e in accepted["adds"] for unit in range(e["quantity"])}
    anchor_entries = accepted["adds"] + accepted["moves"]
    changed_targets = {**addition_targets, **{_target_id(e["target"]): e["action_id"] for e in accepted["moves"]}, **{e["removed_item_id"]: e["action_id"] for e in accepted["restores"]}}
    graph = {e["action_id"]: {changed_targets[target] for target in _anchor_target_ids(e["anchor"]) if target in changed_targets} for e in anchor_entries}
    for move in accepted["moves"]:
        creation = addition_targets.get(_target_id(move["target"]))
        if creation:
            graph[move["action_id"]].add(creation)
    remaining = set(graph)
    while remaining:
        ready = {key for key in remaining if not (graph[key] & remaining)}
        if not ready:
            rejected.update(remaining)
            break
        remaining -= ready
    for _ in range(len(anchor_entries) + 1):
        for entry in anchor_entries:
            references = _anchor_target_ids(entry["anchor"])
            if references & removed or graph[entry["action_id"]] & rejected or any(target not in targets and target not in changed_targets for target in references):
                rejected.add(entry["action_id"])
    for group in ("adds", "moves"):
        for entry in list(accepted[group]):
            if entry["action_id"] in rejected:
                accepted[group].remove(entry)
                diagnostics.append({"code": "invalid_dependency", "group": group, "action_id": entry["action_id"], "reason": "Anchor target is missing, rejected, removed or cyclic."})
    hard_errors = []
    for key, field in (("must_have_add_ids", "add_id"), ("must_have_selection_ids", "selection_id"), ("explicit_selection_ids", "selection_id"), ("must_have_categories", "category")):
        actual = {e[field] for e in accepted["adds"]}
        actual.update(item[field] for item in base_items.values() if item.get('status')!='removed' and item.get(field))
        for missing in set(constraints.get(key, [])) - actual:
            hard_errors.append({"code": "missing_explicit_selection" if key == "explicit_selection_ids" else "missing_must_have", "field": key, "id": missing, "reason": "A protected requirement cannot be filtered from the plan."})
    plan = {"schema_version": 1, "summary": raw["summary"], **accepted,
            "decision_revision": raw.get("decision_revision"), "base": deepcopy(raw.get("base"))}
    if constraints.get("decision_revision") is not None and plan["decision_revision"] != constraints["decision_revision"]:
        hard_errors.append({"code": "stale_decision", "reason": "Plan does not reference the current decision revision."})
    if constraints.get("base") is not None and plan["base"] != constraints["base"]:
        hard_errors.append({"code": "stale_base", "reason": "Plan does not reference the current candidate base."})
    invalid = len(diagnostics)
    return {"plan": plan, "diagnostics": diagnostics, "invalid_count": invalid, "entry_count": total,
            "retry_malformed": invalid > total / 2, "hard_errors": hard_errors}


class GeminiSpatialPlanner:
    def __init__(self, *, client=None, model=None, timeout=60):
        self.client = client
        self.model = model or os.getenv("GEMINI_SPATIAL_MODEL") or os.getenv("GEMINI_MODEL")
        self.timeout = timeout

    async def plan(self, room_snapshot, selections, instructions, photos, constraints, base_scene=None):
        if not 2 <= len(photos) <= 3:
            raise PlanningFailure("missing_planning_photos", "Spatial planning requires 2–3 relevant stored capture photos.")
        if not self.model:
            raise PlanningFailure("provider_not_configured", "Configure GEMINI_SPATIAL_MODEL for spatial planning.")
        from google import genai
        from google.genai import types

        client = self.client
        if client is None:
            key = os.getenv("GEMINI_API_KEY")
            if not key:
                raise PlanningFailure("provider_not_configured", "Gemini credentials are not configured.")
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(self.timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1)))
        context = {"room": _room(room_snapshot), "selections": selections, "instructions": instructions,
                   "constraints": constraints, "base_scene": base_scene,
                   "category_ids": list(CATEGORIES)}
        prompt = ("Return an Anchor-based DesignPlan for this exact room and approved choices. "
                  "Use only supplied identities and selection_id; never invent metric placement coordinates. "
                  "Preserve Keep, permanent fixtures, hard requirements, intent and approved budget. "
                  "Use photos only for style/context, never Product measurements. " + json.dumps(context, allow_nan=False))
        contents = [types.Part.from_text(text=prompt)]
        for photo in photos:
            data = photo if isinstance(photo, bytes) else photo["bytes"]
            mime_type = "image/jpeg" if isinstance(photo, bytes) else photo.get("mime_type", "image/jpeg")
            contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))
        provider_failures, malformed_retries, attempts = 0, 0, []
        try:
            while True:
                try:
                    response = await asyncio.wait_for(client.aio.models.generate_content(
                        model=self.model, contents=contents,
                        config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=DesignPlan.model_json_schema())), timeout=self.timeout)
                    attempts.append({"outcome": "received", "usage": response.usage_metadata.model_dump(mode="json") if getattr(response, "usage_metadata", None) else {}})
                except Exception as exc:
                    # SDK API/network failures are bounded independently of malformed model output.
                    attempts.append({"outcome": "provider_failure", "failure_kind": "timeout" if isinstance(exc, asyncio.TimeoutError) else "provider_error"})
                    if provider_failures >= 1:
                        raise PlanningFailure("provider_error", "Spatial planning failed after its allowed provider retry.", attempts) from exc
                    provider_failures += 1
                    continue
                try:
                    raw = json.loads(response.text)
                    result = validate_plan(raw, room_snapshot, selections, constraints, base_scene)
                except (ValueError, TypeError, PlanningFailure):
                    result = {"retry_malformed": True, "hard_errors": [], "diagnostics": [{"code": "malformed_plan", "reason": "Model response did not match the spatial plan contract."}]}
                if result["retry_malformed"] and malformed_retries == 0:
                    malformed_retries += 1
                    attempts[-1]["outcome"] = "malformed_retry"
                    contents.append(types.Part.from_text(text="The response has too many invalid entries. Correct these diagnostics while preserving every hard requirement: " + json.dumps(result["diagnostics"])))
                    continue
                if result["retry_malformed"] or result["hard_errors"]:
                    raise PlanningFailure("invalid_spatial_plan", "Spatial plan could not preserve a valid approved candidate.", result["diagnostics"] + result["hard_errors"])
                result["attempts"] = attempts
                return result
        finally:
            if self.client is None:
                await client.aio.aclose()


def repair_candidate(room_snapshot, plan, selections, constraints, solve_result, equivalents, *, approved_repair=None):
    """One sequential repair pass. The controller persists returned candidate/question state."""
    private_plan, private_selections, private_constraints = deepcopy(plan), deepcopy(selections), deepcopy(constraints)
    conflicts = solve_result.get("conflicts", [])
    failed_add_ids = {target for c in conflicts if c["code"] == "must_have_unplaced" for target in c["target_ids"]}
    if not failed_add_ids:
        return {"state": "complete" if not conflicts else "unresolved", "plan": private_plan,
                "selections": private_selections, "constraints": private_constraints, "solve_result": solve_result, "diagnostics": []}
    diagnostics = []
    explicit = set(constraints.get("explicit_selection_ids", []))
    for addition in private_plan["adds"]:
        if addition["add_id"] not in failed_add_ids:
            continue
        original_id = addition["selection_id"]
        for alternative in equivalents.get(original_id, []):
            alternative_id = alternative.get("selection_id")
            if not alternative_id or alternative_id == original_id or alternative.get("category") != addition["category"] or alternative.get("dimension_evidence", {}).get("outcome") != "verified":
                continue
            if any(alternative.get(field) != value for field,value in constraints.get("required_product_attributes", {}).get(original_id, {}).items()):
                continue
            try:
                from .products import calculate_purchases

                candidate_plan = deepcopy(private_plan)
                next(a for a in candidate_plan["adds"] if a["add_id"] == addition["add_id"])["selection_id"] = alternative_id
                candidate_selections = {**private_selections, alternative_id: alternative}
                candidate_constraints = deepcopy(private_constraints)
                for field in ("must_have_selection_ids", "explicit_selection_ids"):
                    candidate_constraints[field] = [alternative_id if key == original_id else key for key in candidate_constraints.get(field, [])]
                candidate = solve(room_snapshot, candidate_plan, candidate_selections, candidate_constraints)
                if any(addition["add_id"] in c.get("target_ids", []) for c in candidate["conflicts"]):
                    diagnostics.append({"selection_id": alternative_id, "code": "equivalent_does_not_fit"})
                    continue
                offers = {s["offer_id"]: s["offer"] for s in candidate_selections.values()}
                purchases = calculate_purchases(candidate["scene"]["items"], offers, constraints.get("approved_ceiling", constraints.get("approved_budget")))
                if not purchases.get("within_budget", True):
                    continue
                protected = original_id in explicit
                approved = approved_repair and approved_repair.get("add_id") == addition["add_id"] and approved_repair.get("selection_id") == alternative_id
                if protected and not approved:
                    return {"state": "awaiting_question", "plan": private_plan, "selections": private_selections, "constraints": private_constraints,
                            "solve_result": solve_result, "diagnostics": diagnostics,
                            "question": {"kind": "spatial_tradeoff", "text": "Your selected Product cannot fit. Use this verified equivalent?",
                                         "add_id": addition["add_id"], "original_selection_id": original_id,
                                         "choices": [{"id": alternative_id, "label": alternative.get("title", "Verified equivalent"), "selection": alternative}],
                                         "required": True, "skip_allowed": False}}
                validation = validate_plan(candidate_plan, room_snapshot, candidate_selections, candidate_constraints)
                if validation["hard_errors"] or validation["invalid_count"]:
                    diagnostics.append({"selection_id": alternative_id, "code": "equivalent_violates_requirements"})
                    continue
                candidate["scene"]["purchase_summary"] = purchases
                diagnostics.append({"selection_id": alternative_id, "code": "verified_equivalent_placed"})
                private_plan, private_selections, private_constraints, solve_result = candidate_plan, candidate_selections, candidate_constraints, candidate
                break
            except (KeyError, ValueError, InvalidOperation):
                continue
        else:
            return {"state": "awaiting_question", "plan": private_plan, "selections": private_selections, "constraints": private_constraints,
                    "solve_result": solve_result, "diagnostics": diagnostics,
                    "question": {"kind": "spatial_constraint", "text": "The required Addition cannot fit within the approved constraints. Which requirement may change?",
                                 "add_id": addition["add_id"], "required": True, "skip_allowed": False,
                                 "choices": [{"id": "omit_requirement", "label": "Continue without this Addition"}]}}
    return {"state": "complete" if not solve_result["conflicts"] else "unresolved", "plan": private_plan,
            "selections": private_selections, "constraints": private_constraints, "solve_result": solve_result, "diagnostics": diagnostics}
