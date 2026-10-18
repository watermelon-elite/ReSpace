"""Replay authored measurements through planning, listing checks and placement without providers."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from respace.contracts import Generation
from respace.discovery import ProductService, checked_facts
from respace.operations import OperationService
from respace.planning import ModelAction, PlanningController
from respace.products import calculate_purchases, offer_eligible
from respace.solver import solve, validate_scene
from respace.spatial_planning import validate_plan


FIXTURES = sorted((Path(__file__).parent / 'fixtures' / 'agent_loop').glob('*.json'))


@pytest.fixture(params=FIXTURES, ids=lambda path: path.stem)
def scenario(request):
    return json.loads(request.param.read_text())


class FixtureCatalog:
    def __init__(self, listings):
        self.listings_by_url = {entry['candidate']['product_url']: entry for entry in listings}
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        categories = {entry['candidate']['category'] for entry in self.listings_by_url.values()}
        category = next((c for c in sorted(categories, key=len, reverse=True) if c.replace('_', ' ') in query), None)
        return {'results': [{'title': entry['candidate']['title'], 'product_id': entry['listing_id'],
                            'link': url, 'source': entry['candidate']['merchant']}
                           for url, entry in self.listings_by_url.items() if entry['candidate']['category'] == category],
                'fresh_requested': False, 'test_only': True}

    def listings(self, candidate):
        return [self.listings_by_url[candidate['raw']['link']]['candidate']]

    def verify(self, candidate):
        entry = self.listings_by_url[candidate['product_url']]
        return checked_facts(candidate, entry['facts'], entry['page'])

    def score(self, choice, request):
        return {'practical_score': 80, 'style_score': 80,
                'practical_reason': 'Controlled fixture score.', 'style_reason': 'Controlled fixture score.'}


def test_authored_measurements_evidence_and_placement(scenario):
    assert scenario['schema_version'] == 1 and scenario['provenance']['kind'] == 'synthetic'
    context, snapshot = scenario['agent_context'], scenario['room_snapshot']
    Generation.model_validate(context['request'])
    room = snapshot['room']
    floor = Polygon(room['floor']['polygon'])
    assert floor.is_valid and floor.exterior.is_ccw
    assert floor.area == pytest.approx(scenario['expected']['floor_area'])
    assert floor.area == pytest.approx(context['measured_context']['floor']['area'])
    for index, wall in enumerate(room['walls']):
        assert wall['a'] == room['floor']['polygon'][index]
        assert wall['b'] == room['floor']['polygon'][(index + 1) % len(room['walls'])]
        assert Point(wall['a']).distance(Point(wall['b'])) == pytest.approx(wall['length'])
        interior = [(a+b)/2 + n*.01 for a, b, n in zip(wall['a'], wall['b'], wall['inward_normal'])]
        assert floor.covers(Point(interior))
    baseline = solve(snapshot, {'adds': []}, {}, {'intent': 'add'})
    assert baseline['conflicts'] == [], baseline['conflicts']

    checked = {}
    at = datetime.fromisoformat(scenario['provenance']['created_at'])
    for listing in scenario['listings']:
        result = checked_facts(listing['candidate'], listing['facts'], listing['page'], now=at)
        assert result['dimension_evidence']['outcome'] == listing['expected']['dimension_outcome']
        if listing['expected']['dimensions'] is not None:
            assert result['dimension_evidence']['dimensions'] == pytest.approx(listing['expected']['dimensions'])
        assert offer_eligible(result['offers'][0], now=at) == listing['expected']['offer_available']
        checked[listing['listing_id']] = result
    selections = {}
    for addition in scenario['spatial_case']['plan']['adds']:
        listing_id = scenario['replay']['selection_listings'][addition['add_id']]
        result = checked[listing_id]
        variant, evidence, offer = result['variant'], result['dimension_evidence'], result['offers'][0]
        selections[addition['selection_id']] = {
            'selection_id': addition['selection_id'], 'category': variant['category'], 'title': variant['title'],
            'variant_id': variant['variant_id'], 'offer_id': offer['offer_id'], 'offer': offer,
            'dimensions': evidence['dimensions'], 'dimension_evidence': evidence, 'quantity': addition['quantity']}
    plan, constraints = scenario['spatial_case']['plan'], scenario['spatial_case']['constraints']
    validation = validate_plan(plan, snapshot, selections, constraints)
    assert validation['diagnostics'] == [] and validation['hard_errors'] == []
    before = deepcopy(scenario)
    result = solve(snapshot, validation['plan'], selections, constraints)
    assert scenario == before
    assert result == solve(snapshot, validation['plan'], selections, constraints)
    expected = scenario['expected']
    assert sorted({c['code'] for c in result['conflicts']}) == expected['conflict_codes']
    assert sorted(o['add_id'] for o in result['omissions']) == expected['omitted_add_ids']
    assert sum(i['origin'] == 'new' and i['status'] != 'removed' for i in result['scene']['items']) == expected['new_item_count']
    assert validate_scene(snapshot, result['scene'], constraints) == []
    offers = {record['offer_id']: record['offer'] for record in selections.values()}
    purchases = calculate_purchases(result['scene']['items'], offers, context['approved_budget'])
    assert purchases['total'] == expected['candidate_total']
    for object_id in expected.get('removed_object_ids', []):
        assert next(i for i in result['scene']['items'] if i.get('object_id') == object_id)['status'] == 'removed'
    for object_id, instruction in constraints['instructions'].items():
        if instruction == 'keep':
            item = next(i for i in result['scene']['items'] if i.get('object_id') == object_id)
            assert item['placement'] == item['original_placement'] and item['status'] == 'existing'
    if 'chair_packs' in expected:
        chairs = next(line for line in purchases['lines'] if line['variant_id'] == selections['selection_chairs']['variant_id'])
        assert chairs['purchased_pack_count'] == expected['chair_packs']
        assert chairs['supplied_unit_count'] == expected['chair_supplied']
        assert chairs['paid_surplus_count'] == expected['chair_paid_surplus']


@pytest.mark.asyncio
async def test_planning_controller_pauses_resumes_searches_and_finalizes(scenario, store):
    context = scenario['agent_context']
    request = context['request']
    room_id, capture_id, operation_id = context['planning']['room_id'], request['capture_id'], request['operation_id']
    with store.transaction():
        store.put('rooms', room_id, {'room_id': room_id, 'device_id': 'fixture_device', 'latest_capture_id': capture_id,
            'latest_snapshot_id': request['snapshot_id'], 'planning_revision': 0, 'active_revision': 0,
            'active_design_id': None, 'current_operation_id': None})
        store.put('captures', capture_id, {'capture_id': capture_id, 'room_id': room_id, 'state': 'complete',
            'measured_context': context['measured_context']})
        store.put('planning', room_id, context['planning'])
        store.put('snapshots', request['snapshot_id'], scenario['room_snapshot'])
    operations = OperationService(store)
    operations.submit('fixture_device', room_id, 'generation', request)
    catalog = FixtureCatalog(scenario['listings'])
    products = ProductService(store, catalog, catalog, catalog)
    actions = iter(scenario['replay']['actions'])
    seen = []
    selected = []

    class Model:
        async def act(self, current):
            assert current['measured_context'] == context['measured_context']
            seen.append(current)
            return ModelAction.model_validate(next(actions)).model_dump()

    async def selection_boundary(op_id, selection):
        selected.append(selection)
        operations.finish(op_id, 'succeeded', {'result_kind': 'selection', 'selection_snapshot_id': selection['selection_snapshot_id']})

    controller = PlanningController(store, operations, products, Model(), selection_boundary)
    await controller.run(operation_id)
    operation = operations.get('fixture_device', operation_id)
    assert operation['state'] == 'needs_clarification', operation.get('failure')
    calls = len(catalog.queries)
    await controller.run(operation_id)
    assert len(seen) == 1 and len(catalog.queries) == calls and selected == []
    question = operation['pending_question']
    operations.answer('fixture_device', operation_id, {
        'operation_id': operation_id, 'question_id': question['question_id'], 'reply_id': 'fixture_reply',
        'expected_decision_revision': operation['decision_revision'], 'expected_question_revision': question['question_revision'],
        **scenario['replay']['answer']})
    await controller.run(operation_id)
    operation = operations.get('fixture_device', operation_id)
    assert operation['state'] == 'succeeded', operation.get('failure')
    assert len(selected) == 1 and selected[0]['purchases']['total'] == scenario['expected']['selected_total']
    assert selected[0]['purchases']['within_budget']
    searches = [a for a in operation['controller']['actions'] if a['action'] == 'search_products']
    for action in searches:
        assert len(action['result']['displayed_choices']) == scenario['expected']['eligible_choices_by_category'][action['payload']['category']]
    await controller.run(operation_id)
    assert len(selected) == 1
