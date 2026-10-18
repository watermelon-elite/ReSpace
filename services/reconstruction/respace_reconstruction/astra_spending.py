"""Durable, serial Astra reservations using exact API input-token counts.

The ceiling applies to this multi-call pipeline's model-token charges, including
known failed calls and retries, at the recorded Standard rates; excludes tax.
Unknown outcomes retain their entire reservation and stop further paid calls.
"""
import hashlib
import json
import math
import os
import urllib.error
import urllib.request

from . import astra
from .store import atomic_json

CEILING_UNITS = 10_000_000  # USD millionths; $10 per explicitly started generation.
# Standard USD per million tokens: ordinary input, cache hit, cache write, output.
# Keep historical Astra rates for receipts/reservations created before migration.
RATES = {"gpt-6-astra": (10., 1., 12.5, 50.), "gpt-6-sol": (2., .2, 2.5, 10.)}


def rates(model):
    if model not in RATES:
        raise RuntimeError("No verified billing rates for the requested model; no generation was started")
    return RATES[model]


class BudgetExhausted(RuntimeError):
    pass


def count_input_tokens(body, key):
    payload = {k: body[k] for k in ("model", "input", "instructions", "text") if k in body}
    request = urllib.request.Request("https://api.openai.com/v1/responses/input_tokens",
        data=json.dumps(payload, allow_nan=False, separators=(",", ":")).encode(),
        headers={"Authorization": "Bearer "+key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read(4096))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("Could not count Astra input tokens; no generation was started") from None
    value = data.get("input_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError("Invalid Astra input-token count; no generation was started")
    return value


def actual_units(response, model="gpt-6-astra"):
    usage = response.get("usage") or {}
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    details = usage.get("input_tokens_details") or {}
    cached, writes = details.get("cached_tokens", 0), details.get("cache_write_tokens", 0)
    values = (inputs, outputs, cached, writes)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values) or cached+writes > inputs:
        raise RuntimeError("Missing or invalid Astra billing usage; reservation retained")
    if response.get("service_tier", "default") not in (None, "default"):
        raise RuntimeError("Unexpected Astra processing tier; reservation retained")
    ordinary, cache, write, output = rates(model)
    multiplier = 2 if inputs > 272000 else 1
    return math.ceil(((inputs-cached-writes)*ordinary+cached*cache+writes*write)*multiplier
                     + outputs*output*(1.5 if multiplier == 2 else 1))


class Spending:
    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {
            "ceiling_units": CEILING_UNITS, "currency": "USD", "units_per_dollar": 1000000,
            "rate_basis": "2026-10-18 Standard USD per million: Sol input 2/cache .2/write 2.5/output 10; historical Astra 10/1/12.5/50; long-context uplift",
            "entries": {}}
        if self.data["ceiling_units"] != CEILING_UNITS:
            raise RuntimeError("The retained Astra budget policy differs; review it before continuing")

    @property
    def allocated(self):
        return sum(e.get("cost_units", e["reserved_units"]) for e in self.data["entries"].values())

    def save(self):
        atomic_json(self.path, self.data)

    def request(self, body, directory, label):
        model = body["model"]
        _, _, write_rate, output_rate = rates(model)
        directory.mkdir(parents=True, exist_ok=True)
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        checkpoint = directory/"response.json"
        entry = self.data["entries"].get(fingerprint)
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text())
            if saved.get("fingerprint") == fingerprint:
                if entry is None:
                    raise RuntimeError("Paid checkpoint is missing its budget receipt; restore the ledger")
                self.settle(fingerprint, saved["response"])
                return saved["response"], True
        if any(e["state"] == "reserved" for e in self.data["entries"].values()):
            raise RuntimeError("An Astra call has an unknown billing outcome; retained reservations block further paid calls")
        if entry:
            raise RuntimeError("The billed response checkpoint is missing; refusing to pay for it again")
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY on the local reconstruction service")
        inputs = count_input_tokens(body, key)
        # All input is reserved at the most expensive cache-write rate, with
        # headroom for counting discrepancies. Long-context threshold uses this
        # ceiling too. Reasoning is already part of max_output_tokens.
        input_ceiling = math.ceil(inputs*1.01)+256
        long = input_ceiling > 272000
        input_reservation = input_ceiling*write_rate*(2 if long else 1)
        output_unit_rate = output_rate*(1.5 if long else 1)
        remaining = CEILING_UNITS-self.allocated
        requested_output = body["max_output_tokens"]
        affordable_output = max(0, math.floor((remaining-input_reservation)/output_unit_rate))
        output_limit = min(requested_output, affordable_output)
        minimum_output = min(requested_output, 16000)
        reserved = math.ceil(input_reservation+output_limit*output_unit_rate)
        atomic_json(directory/"budget-preflight.json", {
            "model": model, "stage": label, "input_tokens": inputs,
            "allocated_usd": self.allocated/1e6, "remaining_usd": remaining/1e6,
            "full_request_reservation_usd": math.ceil(input_reservation+requested_output*output_unit_rate)/1e6,
            "requested_output_tokens": requested_output, "affordable_output_tokens": affordable_output,
            "minimum_output_tokens": minimum_output})
        if output_limit < minimum_output or self.allocated+reserved > CEILING_UNITS:
            required = math.ceil(input_reservation+minimum_output*output_unit_rate)/1e6
            raise BudgetExhausted(
                f"{label} was not started: ${remaining/1e6:.2f} remains in this capture's $10 API budget "
                f"(${self.allocated/1e6:.2f} already recorded). This request needs at least a "
                f"${required:.2f} reservation for input and output. No generation charge was initiated for this request.")
        # Cache identity uses the original requested profile. Retrying must reuse
        # this response even though the affordable allowance changes after billing.
        body = dict(body, max_output_tokens=output_limit)
        self.data["entries"][fingerprint] = {"label": label, "model": model, "state": "reserved", "reserved_units": reserved,
                                            "input_token_ceiling": input_ceiling, "max_output_tokens": output_limit,
                                            "requested_max_output_tokens": requested_output}
        self.save()  # Must commit before the potentially billable network action.
        response = astra.call_astra(body, key)
        atomic_json(checkpoint, {"fingerprint": fingerprint, "response": response})
        self.settle(fingerprint, response)
        return response, False

    def settle(self, fingerprint, response):
        entry = self.data["entries"][fingerprint]
        # Entries from the old version have no model and were all Astra calls.
        units = actual_units(response, entry.get("model", "gpt-6-astra"))
        usage = response["usage"]
        if usage["input_tokens"] > entry["input_token_ceiling"] or usage["output_tokens"] > entry["max_output_tokens"]:
            raise RuntimeError("Astra usage exceeded its counted token bounds; stop and review provider usage")
        if units > entry["reserved_units"]:
            raise RuntimeError("Astra usage exceeded its reservation; stop and review provider usage")
        entry.update(state="settled", cost_units=units, status=response.get("status"))
        self.save()

    def report(self):
        return {"ceiling_usd": 10., "allocated_usd": self.allocated/1000000,
                "known_cost_usd": sum(e.get("cost_units", 0) for e in self.data["entries"].values())/1000000,
                "paid_call_count": len(self.data["entries"]), "entries": self.data["entries"]}
