from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from respace import furniture_assets as bridge


@pytest.fixture
def selection():
    return {'selection_snapshot_id': 'selection-1', 'selected': [{
        'variant_id': 'chair-1', 'title': 'Selected chair', 'category': 'chair', 'quantity': 2,
        'dimensions': [.4, .5, .9],
        'variant': {'variant_id': 'chair-1', 'dimension_evidence_id': 'dimensions-1',
                    'image_references': ['https://merchant.example/chair.png']},
        'dimension_evidence': {'evidence_id': 'dimensions-1', 'variant_id': 'chair-1',
                               'dimensions': [.4, .5, .9]}}]}


def test_questions_and_unfinalized_selection_block_reconstruction(selection):
    operation = {'state': 'needs_clarification', 'pending_question': {'text': 'Which chair?'},
                 'controller': {'selection': selection},
                 'outcome': {'result_kind': 'selection', 'selection_snapshot_id': 'selection-1'}}
    with pytest.raises(ValueError, match='Finish the questions'):
        bridge.finalized_selection(operation)
    operation.update(state='succeeded', pending_question=None)
    assert bridge.finalized_selection(operation) == selection
    operation['outcome']['selection_snapshot_id'] = 'another-selection'
    with pytest.raises(ValueError, match='Finish the questions'):
        bridge.finalized_selection(operation)


def test_exact_variant_dimensions_and_image_are_required(selection):
    selection['selected'][0]['dimension_evidence']['variant_id'] = 'different-chair'
    with pytest.raises(ValueError, match='identities'):
        bridge.selected_products(selection)
    selection['selected'][0]['dimension_evidence']['variant_id'] = 'chair-1'
    selection['selected'][0]['variant']['image_references'] = []
    with pytest.raises(ValueError, match='no photograph'):
        bridge.selected_products(selection)


def test_selected_units_share_one_mesh_and_retry_reuses_photo(tmp_path, monkeypatch, selection):
    original = deepcopy(selection)
    selection['selected'].append(deepcopy(selection['selected'][0]))
    downloads, conversions = [], []

    def download(url, path):
        downloads.append(url)
        path.write_bytes(b'photo')
        return hashlib.sha256(b'photo').hexdigest()

    def run(command, **kwargs):
        if 'run_spar3d.py' in command[1]:
            output = Path(command[command.index('--out') + 1]) / 'chair-1'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'mesh.glb').write_bytes(b'mesh')
            (output / 'done.json').write_text(json.dumps({'sha256': hashlib.sha256(b'photo').hexdigest()}))
        else:
            conversions.append(command)
            assert command[command.index('--dimensions') + 1:] == ['0.4', '0.5', '0.9']
            assert command[command.index('--variant-id') + 1] == 'chair-1'
            assert command[command.index('--evidence-id') + 1] == 'dimensions-1'
            Path(command[3]).write_bytes(b'usdz')
            return SimpleNamespace(stdout=json.dumps({'kind': 'catalog', 'category': 'chair',
                'variant_id': 'chair-1', 'dimension_evidence_id': 'dimensions-1', 'authored_bounds': [.4, .5, .9],
                'units': 'meters', 'pivot': 'bottom_center', 'forward_axis': '+Z', 'up_axis': '+Y',
                'scaling_mode': 'dimensioned'}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bridge, 'download_image', download)
    monkeypatch.setattr(bridge.subprocess, 'run', run)
    output, report = bridge.build_assets(selection, tmp_path, tmp_path / 'lab')
    assert len(report['products']) == 1
    assert report['scene_modified'] is False
    assert report['products'][0]['status'] == 'prepared'
    assert report['products'][0]['visual_review'] == 'pending'
    assert json.loads((output / 'selection.json').read_text()) == selection
    bridge.build_assets(selection, tmp_path, tmp_path / 'lab')
    assert len(downloads) == 1
    assert selection['selected'][0] == original['selected'][0]
    for choice in selection['selected']:
        choice['dimensions'] = [.4, .5, 1.0]
        choice['dimension_evidence']['dimensions'] = [.4, .5, 1.0]
    with pytest.raises(ValueError, match='overwrite'):
        bridge.build_assets(selection, tmp_path, tmp_path / 'lab')


def test_incomplete_reconstruction_is_a_failed_product(tmp_path, monkeypatch, selection):
    def download(url, path):
        path.write_bytes(b'photo')
        return hashlib.sha256(b'photo').hexdigest()
    monkeypatch.setattr(bridge, 'download_image', download)
    monkeypatch.setattr(bridge.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    _, report = bridge.build_assets(selection, tmp_path, tmp_path / 'lab')
    assert report['products'][0]['status'] == 'failed'
    assert 'incomplete' in report['products'][0]['error']


def test_redirected_images_use_the_same_public_network_guard(tmp_path, monkeypatch):
    visited = []
    def fetch(url):
        visited.append(url)
        if len(visited) == 1:
            return {'status': 302, 'headers': {'Location': 'https://127.0.0.1/private'}, 'body': b''}
        raise ValueError('Product evidence cannot address private or reserved networks')
    monkeypatch.setattr(bridge, 'fetch_public_resource', fetch)
    with pytest.raises(ValueError, match='private'):
        bridge.download_image('https://merchant.example/chair.png', tmp_path / 'image.png')
    assert visited == ['https://merchant.example/chair.png', 'https://127.0.0.1/private']
    assert not (tmp_path / 'image.png').exists()
