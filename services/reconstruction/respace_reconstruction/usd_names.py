"""Stable, unique USD prim identifiers shared by room.json and USDZ."""
import hashlib

from pxr import Tf


def node_names(identities):
    identities = sorted(identities)
    bases = {identity: Tf.MakeValidIdentifier(identity if identity[0].isalpha() else "node_"+identity)
             for identity in identities}
    counts = {}
    for name in bases.values():
        counts[name] = counts.get(name, 0)+1
    result, used = {}, set()
    for identity, base in bases.items():
        name = base
        if counts[base] > 1 or base == "Materials" or len(base) > 128:
            name = base[:60]+"_"+hashlib.sha256(identity.encode()).hexdigest()
        while name in used or name != base and name in counts:
            name += "_"
        used.add(name)
        result[identity] = name
    return result
