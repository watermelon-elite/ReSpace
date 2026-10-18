from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from respace.discovery import ProductService
from respace.shopping_testing import ScopedShopping, create_shopping_test_app
from respace.store import SQLiteStore
from test_agent_loop_fixtures import FixtureCatalog


SCENARIO = Path(__file__).parent / 'fixtures/agent_loop/01_small_living_room.json'


def test_smoke_scope_filters_real_adapter_results_without_inventing_evidence():
    from unittest.mock import Mock
    shopping = Mock()
    shopping.search.return_value = {'results': [{'source': 'SONGMICS', 'product_id': 'one'},
        {'source': 'SONGMICS', 'product_id': 'two'}, {'source': 'Other', 'product_id': 'three'}], 'source_exhausted': False}
    shopping.listings.return_value = [{'product_url': 'https://www.songmics.com/one'}, {'product_url': 'https://example.com/one'}]
    scoped = ScopedShopping(shopping, {'merchant_names': ['songmics'], 'merchant_domains': ['www.songmics.com'], 'candidates_per_query': 1})
    for query in ('first', 'second', 'third'):
        batch = scoped.search(query)
        assert batch['results'] == [{'source': 'SONGMICS', 'product_id': 'one'}]
        assert batch['source_exhausted'] is False
    assert shopping.search.call_count == 3
    assert scoped.listings({'candidate_id': 'one'}) == [{'product_url': 'https://www.songmics.com/one'}]
    shopping.listings.assert_called_once_with({'candidate_id': 'one'})


def test_synthetic_room_import_and_selection_boundary_use_public_api(tmp_path, monkeypatch):
    for key in ('GEMINI_API_KEY', 'SERPAPI_API_KEY', 'GEMINI_PLANNING_MODEL', 'GEMINI_EXTRACTION_MODEL'):
        monkeypatch.setenv(key, 'test-only')
    monkeypatch.delenv('GEMINI_SPATIAL_MODEL', raising=False)
    fixture = json.loads(SCENARIO.read_text())
    catalog = FixtureCatalog(fixture['listings'])
    store = SQLiteStore(tmp_path / 'records.sqlite3')
    products = ProductService(store, catalog, catalog, catalog)
    actions = iter(fixture['replay']['actions'])
    seen = []
    class Model:
        async def act(self, context):
            seen.append(context)
            return next(actions)
    app = create_shopping_test_app(tmp_path, SCENARIO, products=products, model=Model())
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room = api.get('/v1/rooms').json()['rooms'][0]
        detail = api.get('/v1/rooms/' + room['room_id']).json()
        assert detail['raw_export'] is None and store.list('artifacts') == []
        assert detail['measured_context']['source'] == 'synthetic_json'
        assert detail['measured_context']['floor']['area'] == 15.12
        assert store.list('candidates') == [], 'Fictional listings must not be imported with room context'
        request = deepcopy(fixture['agent_context']['request'])
        request.pop('snapshot_id')
        request['capture_id'] = room['latest_capture_id']
        response = api.post('/v1/rooms/' + room['room_id'] + '/designs', json=request)
        assert response.status_code == 202, response.text
        operation = api.get('/v1/operations/' + request['operation_id']).json()['operation']
        assert operation['state'] == 'needs_clarification'
        question = operation['pending_question']
        answer = {'operation_id': request['operation_id'], 'question_id': question['question_id'], 'reply_id': 'reply',
                  'expected_decision_revision': operation['decision_revision'],
                  'expected_question_revision': question['question_revision'], **fixture['replay']['answer']}
        response = api.post('/v1/operations/' + request['operation_id'] + '/answers', json=answer)
        assert response.status_code == 200, response.text
        operation = api.get('/v1/operations/' + request['operation_id']).json()['operation']
        assert operation['state'] == 'succeeded', operation.get('failure')
        assert operation['outcome']['result_kind'] == 'selection'
        assert operation['controller']['selection']['purchases']['total'] == fixture['expected']['selected_total']
        assert store.list('designs') == [] and store.list('snapshots') == [] and store.list('keyframes') == []
        assert seen[0]['measured_context']['capture_id'] == room['latest_capture_id']
        assert seen[0]['planning']['instructions'][0]['target']['capture_id'] == room['latest_capture_id']
        assert len(api.get('/v1/rooms').json()['rooms']) == 1
        deleted = api.delete('/v1/rooms/' + room['room_id'], params={'operation_id': 'delete'})
        assert deleted.status_code == 200, deleted.text
        assert api.get('/v1/rooms').json()['rooms'] == []
