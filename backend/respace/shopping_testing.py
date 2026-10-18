"""Local-only interview/shopping test using authored room context and real providers."""

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from .capture import CaptureService
from .contracts import ID
from .local import create_local_app
from .operations import now
from .products import stable_id
from . import tracing


class ScopedShopping:
    """Restrict an explicit smoke-test case after the real provider responds."""
    def __init__(self, shopping, scope):
        self.shopping, self.scope = shopping, scope
        if (not scope.get('merchant_names') or not scope.get('merchant_domains')
                or type(scope.get('candidates_per_query')) is not int or not 1 <= scope['candidates_per_query'] <= 10):
            raise ValueError('Shopping scope needs merchant names/domains and 1–10 candidates per query.')

    def search(self, query):
        batch = self.shopping.search(query)
        matched = [hit for hit in batch['results'] if any(name.casefold() in hit.get('source', '').casefold()
                   for name in self.scope['merchant_names'])]
        results = matched[:self.scope['candidates_per_query']]
        tracing.emit('test.shopping_scope', unscoped_count=len(batch['results']), retained_count=len(results), scope=self.scope)
        return {**batch, 'results': results}

    def listings(self, candidate):
        listings = self.shopping.listings(candidate)
        retained = [listing for listing in listings if urlsplit(listing['product_url']).hostname in self.scope['merchant_domains']]
        tracing.emit('test.merchant_scope', unscoped_count=len(listings), retained_count=len(retained))
        return retained


def create_shopping_test_app(data_dir, scenario_path, *, products=None, model=None):
    path = Path(scenario_path)
    data = path.read_bytes()
    scenario = json.loads(data)
    context = scenario['agent_context']
    scope = scenario.get('shopping_scope')
    if scenario.get('provenance', {}).get('kind') != 'synthetic' or context['measured_context'].get('source') != 'synthetic_json':
        raise ValueError('Shopping scenarios require explicitly synthetic JSON room measurements.')
    digest = hashlib.sha256(data).hexdigest()

    async def selection_complete(operation_id, selection, **kwargs):
        app.state.operations.finish(operation_id, 'succeeded', {
            'result_kind': 'selection', 'selection_snapshot_id': selection['selection_snapshot_id'],
            'message': 'Shopping test complete. Products are verified; spatial fit has not been tested.', 'test_scope': scope})

    app = create_local_app(data_dir, products=products, model=model, spatial=selection_complete, live_providers=True)
    store = app.state.store
    if scope:
        shopping = app.state.controller.products.shopping
        app.state.controller.products.shopping = ScopedShopping(shopping, scope)

    def seed(device_id):
        key = stable_id('shopping_test_import', [device_id, digest])
        with store.transaction():
            if store.get('local_test_imports', key):
                return
            captures = CaptureService(store, app.state.operations, app.state.storage)
            created = captures.create(device_id, {'operation_id': key, 'name': 'TEST SHOPPING · ' + scenario['title']})
            room_id, capture_id = created['room']['room_id'], created['capture_id']
            measured = deepcopy(context['measured_context'])
            measured['capture_id'] = capture_id
            capture = store.get('captures', capture_id)
            capture.update(state='complete', measured_context=measured,
                           test_source={'kind': 'synthetic_json', 'filename': path.name, 'sha256': digest})
            store.put('captures', capture_id, capture)
            room = store.get('rooms', room_id)
            room.update(capture_state='complete', scan_at=now(), warnings=[{'code': 'local_test',
                'message': 'Authored synthetic measurements; no scan, photos or LiDAR. Real providers enabled. This test stops at Product selection.'
                    + (f" Scoped smoke test: {', '.join(scope['merchant_names'])}, at most {scope['candidates_per_query']} candidate(s) per query; full discovery breadth untested." if scope else '')}])
            store.put('rooms', room_id, room)
            planning = deepcopy(context['planning'])
            planning.update(room_id=room_id, capture_id=capture_id, planning_revision=0)
            for instruction in planning.get('instructions', []):
                instruction['target']['capture_id'] = capture_id
            store.put('planning', room_id, planning)
            store.put('local_test_imports', key, {'device_id': device_id, 'sha256': digest})

    @app.middleware('http')
    async def import_scenario(request, call_next):
        if request.method == 'GET' and request.url.path == '/v1/rooms':
            try:
                device_id = TypeAdapter(ID).validate_python(request.headers.get('x-device-id'))
            except ValueError:
                return await call_next(request)
            await asyncio.to_thread(seed, device_id)
        return await call_next(request)

    return app
