import json
from pathlib import Path

from respace.contracts import Edit, Remove
from respace.products import calculate_purchases
from respace.solver import validate_scene


def test_shared_remove_restore_transport_has_valid_scenes_exact_purchases_and_replay_identity():
    transport = json.loads((Path(__file__).parent / 'fixtures/api/removal-v1.json').read_text())
    Remove.model_validate(transport['remove_request'])
    Edit.model_validate(transport['restore_request'])
    assert transport['remove_operation']['operation']['outcome'] == transport['remove_replay']['operation']['outcome']
    for key in ('parent', 'removed', 'restored'):
        scene = transport[key]['design']['scene']
        assert validate_scene(scene['room'], scene) == []
        assert scene['purchase_summary'] == calculate_purchases(scene['items'], {s['offer_id']: s['offer'] for s in scene['selections'].values()}, '200.00')


def test_shared_color_transport_preserves_snapshot_geometry_and_observed_evidence():
    transport = json.loads((Path(__file__).parent / 'fixtures/api/observed-color-v1.json').read_text())
    room = transport['snapshot']['snapshot']['room']
    scene = transport['design']['design']['scene']
    assert scene['room'] == room and validate_scene(room, scene) == []
    sampled = next(o for o in room['objects'] if 'color' in o['attrs'])
    assert sampled['attrs']['color'] == '#408141'
    assert sampled['color_evidence']['usable_pixels'] >= 200
    assert sampled['color_evidence']['kind'] == 'observed_camera_rgb'
    assert room['processing']['failed'] == 1
