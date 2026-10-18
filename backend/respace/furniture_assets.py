"""Prepare standalone furniture models from a completed imported-room Product plan."""

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urljoin

import httpx
from PIL import Image
from pydantic import TypeAdapter

from .assets import validate_asset
from .contracts import ID
from .discovery import fetch_public_resource
from . import tracing


ROOT = Path(__file__).resolve().parents[2]


def save_json(path, value):
    temporary = path.with_suffix('.json.part')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def finalized_selection(operation):
    selection = operation.get('controller', {}).get('selection')
    if (operation.get('state') != 'succeeded' or operation.get('pending_question')
            or operation.get('outcome', {}).get('result_kind') != 'selection'
            or not selection or selection['selection_snapshot_id'] != operation['outcome'].get('selection_snapshot_id')):
        raise ValueError('Finish the questions and Product selection in the app before generating models.')
    TypeAdapter(ID).validate_python(selection['selection_snapshot_id'])
    if not selection['selected']:
        raise ValueError('This plan selected no new Products to reconstruct.')
    return selection


def selected_products(selection):
    products = {}
    for choice in selection['selected']:
        variant = choice['variant']
        evidence = choice['dimension_evidence']
        variant_id = TypeAdapter(ID).validate_python(choice['variant_id'])
        if (variant['variant_id'] != variant_id or evidence['variant_id'] != variant_id
                or variant['dimension_evidence_id'] != evidence['evidence_id']
                or evidence['dimensions'] != choice['dimensions']):
            raise ValueError('Selected Product and dimension evidence identities must agree.')
        validate_asset({'kind': 'catalog', 'category': choice['category'], 'variant_id': variant_id,
                        'dimension_evidence_id': evidence['evidence_id'], 'authored_bounds': choice['dimensions'],
                        'units': 'meters', 'pivot': 'bottom_center', 'forward_axis': '+Z', 'up_axis': '+Y',
                        'scaling_mode': 'dimensioned'})
        images = variant.get('image_references', [])
        if not images:
            raise ValueError(f'{variant_id}: selected Product has no photograph.')
        # shortcut: use the first stored photograph; inspect it before accepting a reconstruction.
        product = {'variant_id': variant_id, 'category': choice['category'], 'title': choice['title'],
                   'dimensions': choice['dimensions'], 'dimension_evidence_id': evidence['evidence_id'],
                   'image_url': images[0], 'file': variant_id + '.png'}
        if variant_id in products and products[variant_id] != product:
            raise ValueError('Repeated Product has conflicting dimensions or image evidence.')
        products[variant_id] = product
    return list(products.values())


def download_image(url, destination):
    for _ in range(6):
        response = fetch_public_resource(url)
        headers = {key.lower(): value for key, value in response['headers'].items()}
        if response['status'] in (301, 302, 303, 307, 308) and headers.get('location'):
            url = urljoin(url, headers['location'])
            continue
        if response['status'] != 200:
            raise ValueError(f'Product photograph returned HTTP {response["status"]}.')
        with Image.open(BytesIO(response['body'])) as source:
            if source.width * source.height > 20_000_000:
                raise ValueError('Product photograph exceeds 20 megapixels.')
            source.convert('RGBA').save(destination, format='PNG')
        return hashlib.sha256(destination.read_bytes()).hexdigest()
    raise ValueError('Product photograph exceeded the redirect limit.')


def build_assets(selection, output, lab):
    TypeAdapter(ID).validate_python(selection['selection_snapshot_id'])
    products = selected_products(selection)
    output = Path(output) / selection['selection_snapshot_id']
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    selection_path = output / 'selection.json'
    if selection_path.exists() and json.loads(selection_path.read_text()) != selection:
        raise ValueError('The saved selection differs; do not overwrite an existing run.')
    save_json(selection_path, selection)
    tracing.configure(output / 'bridge.jsonl')
    images = output / 'images'
    images.mkdir(exist_ok=True)
    manifest_path = output / 'images.json'
    previous = {p['variant_id']: p for p in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
    ready, results = [], []
    for product in products:
        try:
            with tracing.span('asset.image', variant_id=product['variant_id']):
                path = images / product['file']
                cached = previous.get(product['variant_id'], {})
                if (path.is_file() and all(cached.get(k) == v for k, v in product.items())
                        and hashlib.sha256(path.read_bytes()).hexdigest() == cached.get('sha256')):
                    digest = cached['sha256']
                else:
                    digest = download_image(product['image_url'], path)
                ready.append({**product, 'sha256': digest})
                save_json(manifest_path, ready)
        except Exception as error:
            results.append({**product, 'status': 'failed', 'error': str(error)})
    reconstruction_error = None
    if ready:
        with (output / 'reconstruction.log').open('a') as log:
            try:
                subprocess.run([str(lab / '.venv/bin/python'), str(ROOT / 'assets/spar3d/run_spar3d.py'),
                                '--lab', str(lab), '--images', str(images), '--manifest', str(manifest_path),
                                '--out', str(output / 'meshes'), '--device', 'cpu'],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            except (subprocess.CalledProcessError, OSError):
                reconstruction_error = 'Reconstruction process failed; inspect reconstruction.log.'
    for product in ready:
        try:
            with tracing.span('asset.convert', variant_id=product['variant_id']):
                folder = output / 'meshes' / product['variant_id']
                marker = folder / 'done.json'
                if (not marker.is_file() or json.loads(marker.read_text()).get('sha256') != product['sha256']
                        or not (folder / 'mesh.glb').is_file()):
                    raise ValueError(reconstruction_error or 'Reconstruction incomplete; inspect reconstruction.log.')
                destination = folder / 'model.usdz'
                converted = subprocess.run([str(lab / '.venv-prepare/bin/python'), str(ROOT / 'assets/prepare.py'),
                    str(folder / 'mesh.glb'), str(destination), '--auto-orient', '--category', product['category'],
                    '--variant-id', product['variant_id'], '--evidence-id', product['dimension_evidence_id'],
                    '--dimensions', *map(str, product['dimensions'])], capture_output=True, text=True, check=True)
                asset = validate_asset(json.loads(converted.stdout))
                save_json(folder / 'asset.json', asset)
                results.append({**product, 'status': 'prepared', 'asset': asset, 'path': str(destination),
                                'visual_review': 'pending'})
        except Exception as error:
            message = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            results.append({**product, 'status': 'failed', 'error': message})
        save_json(output / 'report.json', {'selection_snapshot_id': selection['selection_snapshot_id'],
                                         'scene_modified': False, 'products': results})
    report = {'selection_snapshot_id': selection['selection_snapshot_id'], 'scene_modified': False, 'products': results}
    save_json(output / 'report.json', report)
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8081')
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--operation-id', required=True)
    parser.add_argument('--output', type=Path, default=Path('.local/kitchenette-run/furniture'))
    parser.add_argument('--lab', type=Path, default=Path(os.environ.get('SPAR3D_LAB', Path.home() / 'spar3d-lab')))
    args = parser.parse_args()
    os.umask(0o077)
    lab = args.lab.expanduser().resolve()
    for name in ('.venv', '.venv-prepare'):
        if not (lab / name / 'bin/python').is_file():
            parser.error(f'Missing {name} runtime under {lab}; run assets/spar3d/setup.sh first.')
    operation_id = TypeAdapter(ID).validate_python(args.operation_id)
    with httpx.Client(base_url=args.backend, headers={'X-Device-Id': args.device_id}, timeout=30) as client:
        response = client.get(f'/v1/operations/{operation_id}')
        response.raise_for_status()
        selection = finalized_selection(response.json()['operation'])
    output, report = build_assets(selection, args.output.resolve(), lab)
    print(f'Furniture report: {output / "report.json"}')
    print('Scene unchanged. Prepared models need visual review before use.')
    if any(product['status'] != 'prepared' for product in report['products']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
