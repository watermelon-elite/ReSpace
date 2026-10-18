"""Durable per-capture completion reservations, including retries/unknown outcomes."""
import json
import math

from .instances import ProviderUnavailable
from .store import atomic_json


class CompletionBudget:
    def __init__(self,path,ceiling=5.):
        self.path=path
        self.data=json.loads(path.read_text()) if path.exists() else {"ceiling_usd":ceiling,"entries":{}}
        if self.data["ceiling_usd"]!=ceiling:
            raise ProviderUnavailable("Completion budget policy changed; review the retained ledger")

    def reserve(self,fingerprint):
        entry=self.data["entries"].get(fingerprint)
        if entry:
            if entry["state"]=="succeeded":return None
            raise ProviderUnavailable("A previous completion request has an unknown billing outcome; review its receipt before retrying")
        allocated=sum(e.get("cost_usd",e["reserved_usd"]) for e in self.data["entries"].values())
        remaining=self.data["ceiling_usd"]-allocated
        if remaining<=.000001:raise ProviderUnavailable("The per-room completion budget is exhausted")
        self.data["entries"][fingerprint]={"state":"reserved","reserved_usd":remaining}
        atomic_json(self.path,self.data)
        return remaining

    def settle(self,fingerprint,receipt):
        cost=receipt.get("cost_usd")
        entry=self.data["entries"][fingerprint]
        if (receipt.get("request_fingerprint")!=fingerprint or isinstance(cost,bool)
            or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0 or cost>entry["reserved_usd"]):
            raise ProviderUnavailable("The completion worker returned an invalid or over-budget cost receipt")
        entry.update(state="succeeded",cost_usd=cost)
        atomic_json(self.path,self.data)
