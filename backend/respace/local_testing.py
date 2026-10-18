"""Opt-in offline test inputs for the real local application workflow."""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import re
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from .api import create_app
from .capture import CaptureService
from .categories import CATEGORIES
from .contracts import ID
from .discovery import ProductService, checked_facts
from .glb_room import raw_room_from_glb
from .operations import DomainError, OperationService, now
from .products import ProductError, stable_id
from .spatial import SpatialPipeline
from .spatial_planning import validate_plan
from .storage import LocalCaptureStorage
from .store import SQLiteStore


ROOM_GLB_SHA256 = 'c32b3eb4cdbee212baa130524d0846ebfa1d71a402af57a462b3cb9491b47d75'
TEST_NOTICE = 'Offline test: model-derived room, simulated Product offers and planning responses. No live provider calls.'


def load_test_model(path):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != ROOM_GLB_SHA256:
        raise ValueError('No single-room import profile for this model; use the supplied room.glb. Apartment partitioning is skipped.')
    return raw_room_from_glb(path)


class TestCatalog:
    """Controlled shopping, page evidence and scoring boundaries; calculations stay real."""
    def search(self, query):
        category = next((c for c in sorted(CATEGORIES, key=len, reverse=True)
                         if re.search(r'\b' + re.escape(c.replace('_', ' ')) + r'\b', query)), 'chair')
        return {'results': [{'title': f'TEST {category.replace("_", " ")} {index+1} · simulated',
                             'product_id': f'test-{category}-{index}', 'link': f'https://offline.invalid/{category}/{index}',
                             'source': 'Offline test data'} for index in range(6)],
                'fresh_requested': False, 'source_exhausted': False, 'test_only': True}

    def listings(self, candidate):
        return [{'product_url': candidate['raw']['link'], 'merchant': 'Offline test data', 'title': candidate['title']}]

    def verify(self, candidate):
        parsed = urlsplit(candidate['product_url'])
        if parsed.hostname != 'offline.invalid':
            raise ProductError('unavailable_capability', 'Offline test mode does not verify real merchant pages.')
        category, index = parsed.path.strip('/').split('/')
        index = int(index)
        size = [round(v * (1 - index * .025), 4) for v in CATEGORIES[category]['default_size']]
        measurements = [{'axis': axis, 'label': axis.title(), 'value': str(value), 'unit': 'm',
                         'quote': f'{axis.title()} {value} m'} for axis, value in zip(('width', 'depth', 'height'), size)]
        price = f'{40 + index*10}.00'
        facts = {'exact_variant': True, 'variant_quote': candidate['title'], 'options': {'test_option': str(index+1)},
                 'gtin': None, 'manufacturer': None, 'mpn': None, 'identity_quote': None,
                 'classification': 'item', 'measurements': measurements, 'price': price, 'currency': 'USD',
                 'price_quote': f'USD {price}', 'availability': 'in_stock', 'availability_quote': 'Test in stock',
                 'units_per_pack': 1, 'pack_quote': 'Test pack contains one unit', 'features': {}, 'feature_quotes': {}}
        text = '\n'.join([TEST_NOTICE, candidate['title'], *(m['quote'] for m in measurements),
                          facts['price_quote'], facts['availability_quote'], facts['pack_quote']])
        return checked_facts(candidate, facts, {'source_url': candidate['product_url'], 'visible_text': text})

    def score(self, choice, request):
        return {'practical_score': 80, 'style_score': 80,
                'practical_reason': 'Controlled offline test score.', 'style_reason': 'Controlled offline test score.'}


class TestPlanningModel:
    async def act(self, context):
        answers = {a['question'].get('topic'): a['request'] for a in context['answers']}
        if 'test_activity' not in answers:
            return {'action': 'ask_user', 'payload': {'kind': 'single_choice', 'topic': 'test_activity',
                'text': 'Offline test: what should this room support?', 'allow_skip': True, 'allow_delegate': True,
                'choices': [{'choice_id': 'relax', 'label': 'Relaxing'}, {'choice_id': 'work', 'label': 'Working'}]}}
        if 'test_occupants' not in answers:
            return {'action': 'ask_user', 'payload': {'kind': 'numeric', 'topic': 'test_occupants',
                'text': 'How many people usually use the room?', 'numeric_min': 1, 'numeric_max': 8, 'numeric_step': 1,
                'allow_skip': True, 'allow_delegate': True, 'choices': []}}
        searches = [a for a in context['actions'] if a.get('action') == 'search_products']
        if not searches:
            category = 'desk' if answers['test_activity'].get('choice_ids') == ['work'] else 'chair'
            return {'action': 'search_products', 'payload': {'category': category, 'function': 'offline workflow test'}}
        choices = searches[-1]['result']['displayed_choices']
        if not choices:
            raise DomainError('no_verified_match', 'No simulated choice fits the test budget. Try a budget of USD 200.')
        if 'test_product' not in answers:
            return {'action': 'ask_user', 'payload': {'kind': 'listing_choice', 'topic': 'test_product',
                'text': 'Choose a simulated Product to exercise placement.', 'allow_skip': False, 'allow_delegate': True,
                'choices': [{'choice_id': c['variant_id'], 'label': c['title'], 'variant_id': c['variant_id']} for c in choices]}}
        chosen_ids = answers['test_product'].get('choice_ids', [])
        chosen = next((c for c in choices if c['variant_id'] in chosen_ids), choices[0])
        return {'action': 'finalize_selection', 'payload': {'selected': [{'variant_id': chosen['variant_id'],
            'offer_id': chosen['offer_id'], 'selection_id': 'test_selection', 'quantity': 1}], 'assumptions': [TEST_NOTICE]}}


class TestSpatialPlanner:
    async def plan(self, snapshot, selections, instructions, photos, constraints):
        walls = sorted((w for w in snapshot['room']['walls'] if not w['virtual']), key=lambda w: -w['length'])
        plan = {'summary': TEST_NOTICE, 'decision_revision': constraints['decision_revision'], 'base': constraints['base'], 'adds': []}
        for index, (selection_id, choice) in enumerate(selections.items()):
            anchor = {'type': 'against_wall', 'wall_id': walls[index % len(walls)]['id'], 'alignment': 'center'}
            plan['adds'].append({'action_id': f'test-add-{index}', 'add_id': f'test-add-{index}', 'category': choice['category'],
                'selection_id': selection_id, 'priority': index, 'quantity': choice.get('quantity', 1),
                'anchor': anchor, 'reason': 'Offline test placement; actual solver validates the geometry.'})
        return validate_plan(plan, snapshot, selections, constraints)


class TestEditModel:
    async def act(self, context):
        text = context['command'].lower()
        targets = context.get('explicit_target_ids') or ([context['selected_item_id']] if context.get('selected_item_id') else [])
        target = next((i for i in context['scene']['items'] if i['id'] in targets), None)
        command = re.fullmatch(r'\s*(move|remove|restore|bring back)\s+(.+?)\s*[.!]?\s*', text)
        names = {'this', 'it', 'this item', 'the item', 'selected item', 'the selected item'}
        if target:
            names.update({target['category'].replace('_', ' '), 'the ' + target['category'].replace('_', ' '), target['id'].lower()})
        if not command or command[2].rstrip('.!') not in names or not target or len(targets) != 1:
            raise DomainError('unavailable_capability', 'Offline test commands support one Move, Remove or Restore of this Item or its category. Live language interpretation is skipped.')
        action = command[1]
        plan: dict = {'summary': TEST_NOTICE}
        if action in {'restore', 'bring back'}:
            plan['restores'] = [{'action_id': 'test-restore', 'removed_item_id': target['id'], 'reason': 'Explicit test restore'}]
        elif action == 'remove':
            plan['removes'] = [{'action_id': 'test-remove', 'target': {'kind': 'item', 'id': target['id']}, 'reason': 'Explicit test removal'}]
        elif action == 'move':
            walls = sorted((w for w in context['scene']['room']['walls'] if not w['virtual']), key=lambda w: -w['length'])
            wall = next((w for w in walls if w['id'] != target['placement'].get('wall_id')), walls[0])
            plan['moves'] = [{'action_id': 'test-move', 'target': {'kind': 'item', 'id': target['id']},
                'anchor': {'type': 'against_wall', 'wall_id': wall['id'], 'alignment': 'center'}, 'reason': 'Explicit test move'}]
        return {'action': 'execute_plan', 'payload': {'plan': plan}}


def seed_test_room(store, storage, device_id, raw, metadata, *, live_providers=False):
    key = stable_id('local_test_import', [device_id, metadata['sha256']])
    with store.transaction():
        if store.get('local_test_imports', key):
            return
        captures = CaptureService(store, OperationService(store), storage)
        created = captures.create(device_id, {'schema_version': 1, 'operation_id': key,
                                              'name': 'TEST MODEL · ' + metadata['filename']})
        room_id, capture_id = created['room']['room_id'], created['capture_id']
        data = json.dumps(raw, allow_nan=False).encode()
        export = {'artifact_id': key + '-export', 'capture_id': capture_id, 'kind': 'roomplan', 'format': 'application/json',
                  'byte_length': len(data), 'checksum': hashlib.sha256(data).hexdigest()}
        completion = key + '-finalize'
        captures.finalize(device_id, room_id, {'schema_version': 1, 'operation_id': completion, 'capture_id': capture_id,
            'raw_export_base64': base64.b64encode(data).decode(), 'export_descriptor': export,
            'manifest': {'room_id': room_id, 'capture_id': capture_id, 'final_export_artifact_id': export['artifact_id'],
                         'frames': [], 'artifacts': [export], 'completion_id': completion, 'started_at': now(), 'completed_at': now()}})
        capture = store.get('captures', capture_id)
        capture['test_source'] = deepcopy(metadata)
        store.put('captures', capture_id, capture)
        room = store.get('rooms', room_id)
        notice = ('Local test: model-derived room with uncalibrated dimensions; live providers enabled. No room photos or native scan evidence.'
                  if live_providers else TEST_NOTICE)
        room['warnings'] = [{'code': 'local_test' if live_providers else 'offline_test', 'message': notice}]
        store.put('rooms', room_id, room)
        store.put('local_test_imports', key, {'device_id': device_id, 'sha256': metadata['sha256']})


def create_test_app(data_dir, model_paths, *, load_model=load_test_model, live_providers=False):
    models = []
    for path in model_paths:
        try:
            models.append(load_model(path))
        except ValueError as error:
            logging.warning('Skipping test model %s: %s', Path(path).name, error)
    if not models:
        raise ValueError('No supported single-room test models were loaded.')
    if live_providers:
        from .local import create_local_app
        from .spatial_planning import GeminiSpatialPlanner
        app = create_local_app(data_dir, live_providers=True)
        app.state.controller.spatial.planner = GeminiSpatialPlanner(allow_geometry_only=True)
        store, storage = app.state.store, app.state.storage
    else:
        from .local import bind_provider_mode
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        store, storage = SQLiteStore(root / 'records.sqlite3'), LocalCaptureStorage(root / 'captures')
        bind_provider_mode(store, False)
        operations, catalog = OperationService(store), TestCatalog()
        def guard(record):
            context = record.get('intended_context') or record.get('context') or {}
            operations.guard(context.get('operation_id', record.get('operation_id')))
        products = ProductService(store, catalog, catalog, catalog, guard=guard)
        spatial = SpatialPipeline(store, operations, storage, planner=TestSpatialPlanner(), products=products)
        app = create_app(store, storage, products, TestPlanningModel(), spatial, edit_model=TestEditModel(), local=True)

    @app.middleware('http')
    async def import_models(request, call_next):
        if request.method == 'GET' and request.url.path == '/v1/rooms':
            device_id = request.headers.get('x-device-id')
            try:
                device_id = TypeAdapter(ID).validate_python(device_id)
            except ValueError:
                return await call_next(request)
            for raw, metadata in models:
                await asyncio.to_thread(seed_test_room, store, storage, device_id, raw, metadata, live_providers=live_providers)
        return await call_next(request)

    return app
