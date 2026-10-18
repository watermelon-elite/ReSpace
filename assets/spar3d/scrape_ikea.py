"""Fetch isolated IKEA product shots as SPAR3D reconstruction test inputs.

This is a test harness for the reconstruction pipeline, not a catalog source:
these Products carry no verified dimension evidence and must not be promoted to
catalog assets. It exists so reconstruction quality can be judged on real
furniture photography rather than the upstream demo files.

Uses the public search endpoint ikea.com's own search UI calls, and prefers the
cut-out-on-white renditions, since SPAR3D reconstructs a single foreground
object. Idempotent: an image whose recorded sha256 still matches on disk is left
alone, so re-running tops up the set instead of refetching it. The seed makes
the selection reproducible.

Usage: python assets/spar3d/scrape_ikea.py --per-query 3
"""

import argparse
import hashlib
import json
import os
import random
import urllib.parse
import urllib.request
from pathlib import Path

LAB = Path(os.environ.get("SPAR3D_LAB", Path.home() / "spar3d-lab"))

# Chosen to span the failure mode the first round found: reconstruction tracks
# whether the silhouette explains the shape. Thin frames photographed whole
# succeeded, horizontal planes seen edge-on detached, repeated interior cavities
# filled in solid. So this covers thin legs (chair, desk), bulky upholstery
# (armchair, sofa) and foliage with no clean outline (plant).
#
# No rug, art or mirror query: SPEC 11 lets those render as textured panels, so
# a mesh buys nothing and the reconstruction time is better spent elsewhere.
QUERIES = [
    ("table", "coffee table"),
    ("table", "side table"),
    ("shelf", "bookcase shelf unit"),
    ("lamp", "table lamp"),
    ("lamp", "floor lamp"),
    ("chair", "dining chair"),
    ("armchair", "armchair"),
    ("sofa", "2 seat sofa"),
    ("desk", "desk"),
    ("plant", "artificial potted plant"),
]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
# Isolated-on-white shots first; room scenes are poor single-object inputs.
PREFERRED = ["MAIN_PRODUCT_IMAGE", "FUNCTIONAL_PRODUCT_IMAGE", "QUALITY_PRODUCT_IMAGE"]


def get(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def write_atomic(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def search(query, size=24):
    qs = urllib.parse.urlencode({"q": query, "size": size})
    payload = json.loads(
        get(f"https://sik.search.blue.cdtapps.com/us/en/search-result-page?{qs}")
    )
    items = payload["searchResultPage"]["products"]["main"]["items"]
    return [i["product"] for i in items if i.get("product", {}).get("mainImageUrl")]


def pick_image(product):
    by_type = {}
    for image in product.get("allProductImage") or []:
        by_type.setdefault(image["type"], image["url"])
    for kind in PREFERRED:
        if kind in by_type:
            return by_type[kind], kind
    return product["mainImageUrl"], "mainImageUrl"


def verified_existing(manifest: Path, images: Path) -> dict:
    if not manifest.exists():
        return {}
    keep = {}
    for entry in json.loads(manifest.read_text()):
        path = images / entry["file"]
        if path.exists() and sha(path.read_bytes()) == entry.get("sha256"):
            keep[entry["id"]] = entry
    return keep


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", type=Path, default=LAB)
    ap.add_argument("--images", type=Path, help="default: <lab>/images")
    ap.add_argument("--manifest", type=Path, help="default: <lab>/manifest.json")
    ap.add_argument("--per-query", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    images = args.images or args.lab / "images"
    manifest_path = args.manifest or args.lab / "manifest.json"

    images.mkdir(parents=True, exist_ok=True)
    existing = verified_existing(manifest_path, images)
    if existing:
        print(f"{len(existing)} image(s) already verified on disk")

    rng = random.Random(args.seed)
    manifest = list(existing.values())
    seen = set(existing)

    for category, query in QUERIES:
        try:
            products = search(query)
        except Exception as error:
            print(f"  search failed for {query!r}: {error}")
            continue
        rng.shuffle(products)
        taken = sum(1 for entry in manifest if entry["query"] == query)
        for product in products:
            if taken >= args.per_query or product["id"] in seen:
                continue
            url, image_type = pick_image(product)
            full = url + "?f=xl"  # IKEA's large rendition
            slug = f"{category}_{product['name'].lower()}_{product['id']}"
            destination = images / f"{slug.replace(' ', '-')}.jpg"
            try:
                data = get(full)
            except Exception as error:
                print(f"  skip {slug}: {error}")
                continue
            write_atomic(destination, data)
            seen.add(product["id"])
            taken += 1
            manifest.append(
                {
                    "file": destination.name,
                    "sha256": sha(data),
                    "bytes": len(data),
                    "category": category,
                    "query": query,
                    "name": product["name"],
                    "type_name": product.get("typeName"),
                    "id": product["id"],
                    "measure": product.get("itemMeasureReferenceText"),
                    "image_type": image_type,
                    "image_url": full,
                    "product_url": product.get("pipUrl"),
                }
            )
            print(f"  + {destination.name} ({image_type}, {len(data) // 1024} KB)")

    manifest.sort(key=lambda entry: entry["file"])
    write_atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    print(f"\n{len(manifest)} images in {images}")


if __name__ == "__main__":
    main()
