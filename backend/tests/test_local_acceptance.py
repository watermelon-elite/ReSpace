"""Local joins use real persistence/calculations; only external providers are controlled."""
from copy import deepcopy
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from respace.api import create_app
from respace.categories import CATEGORIES
from respace.discovery import ProductService, checked_facts
from respace.local_testing import TestCatalog as OfflineCatalog, TestSpatialPlanner as OfflinePlanner
from respace.operations import OperationService
from respace.solver import validate_scene
from respace.spatial import SpatialPipeline
from respace.storage import LocalCaptureStorage
from respace.store import SQLiteStore
from test_api import complete_room
from test_edits import Editor


class Catalog(OfflineCatalog):
    def __init__(self, oversized=False):
        self.oversized = oversized
        self.calls = 0

    def score(self, choice, request):
        scores = super().score(choice, request)
        if choice['dimensions'][0] > 5:
            scores.update(practical_score=100, style_score=100)
        return scores

    def verify(self, candidate):
        self.calls += 1
        category, index = urlsplit(candidate['product_url']).path.strip('/').split('/')
        size = [10, 10, 1] if self.oversized and index == '0' else CATEGORIES[category]['default_size']
        measurements = [{'axis': axis, 'label': axis.title(), 'value': str(value), 'unit': 'm',
                         'quote': f'{axis.title()} {value} m'} for axis, value in zip(('width', 'depth', 'height'), size)]
        facts = {'exact_variant': True, 'variant_quote': candidate['title'], 'options': {'test_option': str(int(index)+1)},
                 'gtin': None, 'manufacturer': None, 'mpn': None, 'identity_quote': None,
                 'classification': 'item', 'measurements': measurements, 'price': '40.00', 'currency': 'USD',
                 'price_quote': 'USD 40.00', 'availability': 'in_stock', 'availability_quote': 'Test in stock',
                 'units_per_pack': 1, 'pack_quote': 'Test pack contains one unit', 'features': {}, 'feature_quotes': {}}
        page = {'source_url': candidate['product_url'], 'visible_text': '\n'.join([
            candidate['title'], *(m['quote'] for m in measurements), facts['price_quote'],
            facts['availability_quote'], facts['pack_quote']])}
        return checked_facts(candidate, facts, page)


class Selections:
    def __init__(self, categories=('desk',), choose=False):
        self.categories, self.choose = categories, choose
        self.calls = 0

    async def act(self, context):
        self.calls += 1
        searches = [a for a in context['actions'] if a['action'] == 'search_products']
        if len(searches) < len(self.categories):
            return {'action': 'search_products', 'payload': {'category': self.categories[len(searches)], 'function': 'Local acceptance test'}}
        choices = [search['result']['displayed_choices'][0] for search in searches]
        if self.choose and not context['answers']:
            return {'action': 'ask_user', 'payload': {'kind': 'listing_choice', 'text': 'Test: choose this Product explicitly.',
                'choices': [{'choice_id': c['variant_id'], 'variant_id': c['variant_id'], 'label': c['title']} for c in choices]}}
        return {'action': 'finalize_selection', 'payload': {'selected': [
            {'selection_id': c['category'], 'variant_id': c['variant_id'], 'offer_id': c['offer_id'], 'quantity': 1}
            for c in choices]}}


class Planner(OfflinePlanner):
    calls = 0

    def __init__(self, omit=False):
        self.omit = omit

    async def plan(self, *args):
        self.calls += 1
        result = await super().plan(*args)
        if self.omit:
            result['plan']['adds'] = []
        return result


def local_app(directory, *, catalog=None, model=None, editor=None, planner=None):
    store = SQLiteStore(directory / 'records.sqlite3')
    storage = LocalCaptureStorage(directory / 'captures')
    operations = OperationService(store)
    def guard(record):
        context = record.get('intended_context') or record.get('context') or {}
        operations.guard(context.get('operation_id', record.get('operation_id')))
    catalog = catalog or Catalog()
    products = ProductService(store, catalog, catalog, catalog, guard=guard)
    spatial = SpatialPipeline(store, operations, storage, planner=planner or Planner(), products=products)
    return create_app(store, storage, products, model or Selections(), spatial, edit_model=editor or Editor({}), local=True)


def operation(api, operation_id):
    return api.get('/v1/operations/' + operation_id).json()['operation']


def generate(api, room_id, capture_id, *, operation_id='generate', intent='add', parent=None, revision=0):
    request = {'operation_id': operation_id, 'capture_id': capture_id, 'planning_revision': 0,
               'expected_active_revision': revision, 'expected_active_design_id': parent, 'intent': intent, 'budget': '500.00'}
    assert api.post(f'/v1/rooms/{room_id}/designs', json=request).status_code == 202
    return operation(api, operation_id)


def answer(api, current, choice_id, reply_id):
    question = current['pending_question']
    request = {'operation_id': current['operation_id'], 'reply_id': reply_id, 'question_id': question['question_id'],
               'expected_decision_revision': current['decision_revision'], 'expected_question_revision': question['question_revision'],
               'choice_ids': [choice_id]}
    assert api.post(f"/v1/operations/{current['operation_id']}/answers", json=request).status_code == 200
    return request


def test_full_redesign_fit_answer_survives_sqlite_reopen_without_repeating_interview_or_processing(tmp_path):
    catalog, model, planner = Catalog(oversized=True), Selections(choose=True), Planner()
    app = local_app(tmp_path, catalog=catalog, model=model, planner=planner)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        interview = generate(api, room_id, capture_id, intent='redesign')
        answer(api, interview, interview['pending_question']['choices'][0]['choice_id'], 'pick')
        waiting = operation(api, 'generate')
        assert waiting['state'] == 'needs_clarification', waiting
        assert waiting['pending_question']['context'] == 'repair'
        assert api.get(f'/v1/rooms/{room_id}').json()['room']['active_design_id'] is None
        assert app.state.store.list('designs', room_id) == []
        snapshot = app.state.store.list('snapshots', room_id)
        assert len(snapshot) == 1 and planner.calls == 1
        original_answers = deepcopy(waiting['answer_history'])
    restarted_catalog, restarted_model, restarted_planner = Catalog(oversized=True), Selections(choose=True), Planner()
    app = local_app(tmp_path, catalog=restarted_catalog, model=restarted_model, planner=restarted_planner)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        assert operation(api, 'generate')['pending_question'] == waiting['pending_question']
        choice = next(c for c in waiting['pending_question']['choices'] if c['choice_id'] != 'cancel_generation')
        request = answer(api, waiting, choice['choice_id'], 'repair')
        completed = operation(api, 'generate')
        assert completed['state'] == 'succeeded', completed
        child = api.get('/v1/designs/' + completed['outcome']['design_id']).json()['design']
        assert child['generation_inputs']['intent'] == 'redesign'
        assert child['scene']['items'][0]['placement']['size'][0] < 10
        assert validate_scene(child['scene']['room'], child['scene']) == []
        assert child['scene']['purchase_summary']['total'] == '40.00'
        assert completed['answer_history'][:1] == original_answers
        assert restarted_model.calls == restarted_planner.calls == restarted_catalog.calls == 0
        assert app.state.store.list('snapshots', room_id) == snapshot
        assert api.post('/v1/operations/generate/answers', json=request).json()['operation']['outcome'] == completed['outcome']
        assert len(app.state.store.list('designs', room_id)) == 1


def test_spatial_planner_cannot_silently_omit_an_explicit_listing_choice(tmp_path):
    app = local_app(tmp_path, model=Selections(choose=True), planner=Planner(omit=True))
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        waiting = generate(api, room_id, capture_id, intent='redesign')
        answer(api, waiting, waiting['pending_question']['choices'][0]['choice_id'], 'pick')
        rejected = operation(api, 'generate')
        assert rejected['state'] == 'rejected', rejected
        assert rejected['failure']['code'] == 'invalid_spatial_plan'
        assert api.get(f'/v1/rooms/{room_id}').json()['room']['active_design_id'] is None
        assert app.state.store.list('designs', room_id) == []
        assert rejected['controller']['selection']['selected']
        assert rejected['answer_history']


def test_partial_failed_restore_exact_undo_and_branch_survive_sqlite_reopen(tmp_path):
    editor = Editor({})
    app = local_app(tmp_path, model=Selections(('desk', 'chair')), editor=editor)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        completed = generate(api, room_id, capture_id)
        assert completed['state'] == 'succeeded', completed
        parent = api.get('/v1/designs/' + completed['outcome']['design_id']).json()['design']
        desk, chair = parent['scene']['items']
        remove = {'operation_id': 'remove', 'expected_active_design_id': parent['design_id'], 'expected_active_revision': 1, 'item_id': desk['id']}
        api.post(f"/v1/designs/{parent['design_id']}/remove", json=remove)
        removed = operation(api, 'remove')
        assert removed['state'] == 'succeeded', removed
        removed_id = removed['outcome']['design_id']
        selection_id = desk['selection_id']
        editor.result = {'action': 'execute_plan', 'payload': {'plan': {'summary': 'Occupy the removed desk pose', 'adds': [
            {'action_id': 'blocker', 'add_id': 'blocker', 'category': 'desk', 'selection_id': selection_id, 'quantity': 1,
             'priority': 0, 'anchor': desk['anchor'], 'reason': 'Test addition'}]}}}
        api.post(f'/v1/designs/{removed_id}/chat', json={'operation_id': 'block', 'expected_active_design_id': removed_id,
                 'expected_active_revision': 2, 'text': 'Add another workspace.'})
        blocked = operation(api, 'block')
        assert blocked['state'] == 'succeeded', blocked
        base = api.get('/v1/designs/' + blocked['outcome']['design_id']).json()['design']
        editor.result = {'action': 'execute_plan', 'payload': {'plan': {'summary': 'Restore desk and move chair',
            'restores': [{'action_id': 'restore', 'removed_item_id': desk['id'], 'reason': 'Test restore'}],
            'moves': [{'action_id': 'move', 'target': {'kind': 'item', 'id': chair['id']},
                       'anchor': {'type': 'against_wall', 'wall_id': 'w_4', 'alignment': 'center'}, 'reason': 'Test independent move'}]}}}
        request = {'operation_id': 'partial', 'expected_active_design_id': base['design_id'], 'expected_active_revision': 3,
                   'text': 'Restore the removed workspace and adjust the seat.'}
        api.post(f"/v1/designs/{base['design_id']}/chat", json=request)
        partial = operation(api, 'partial')
        assert partial['state'] == 'succeeded', partial
        outcomes = {o['action_id']: o for o in partial['outcome']['action_outcomes']}
        assert outcomes['restore']['code'] == 'collision' and outcomes['restore']['outcome'] == 'failed'
        assert outcomes['move']['outcome'] == 'applied'
        child_id = partial['outcome']['design_id']
        child = api.get('/v1/designs/' + child_id).json()['design']
        assert next(i for i in child['scene']['items'] if i['id'] == desk['id'])['status'] == 'removed'
        assert child['scene']['purchase_summary'] == base['scene']['purchase_summary']
        assert validate_scene(child['scene']['room'], child['scene']) == []
    app = local_app(tmp_path, model=Selections(('desk', 'chair')), editor=editor)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        assert api.post(f"/v1/designs/{base['design_id']}/chat", json=request).json()['operation']['outcome'] == partial['outcome']
        undo = {'operation_id': 'undo', 'expected_active_design_id': child_id, 'expected_active_revision': 4}
        response = api.post(f'/v1/rooms/{room_id}/undo', json=undo).json()
        assert response['operation']['outcome']['design_id'] == base['design_id']
        assert api.post(f'/v1/rooms/{room_id}/undo', json=undo).json() == response
        assert api.get('/v1/designs/' + base['design_id']).json()['design'] == base
        editor.result = {'action': 'execute_plan', 'payload': {'plan': {'summary': 'Remove chair after Undo', 'removes': [
            {'action_id': 'remove-chair', 'target': {'kind': 'item', 'id': chair['id']}, 'reason': 'Test branch'}]}}}
        api.post(f"/v1/designs/{base['design_id']}/chat", json={'operation_id': 'branch', 'expected_active_design_id': base['design_id'],
                 'expected_active_revision': 5, 'text': 'Remove the chair.'})
        branch = operation(api, 'branch')
        assert branch['state'] == 'succeeded', branch
        saved = api.get('/v1/designs/' + branch['outcome']['design_id']).json()['design']
        assert saved['parent_id'] == base['design_id']
        assert api.get('/v1/designs/' + child_id).json()['design'] == child
        assert api.get('/v1/designs/' + parent['design_id']).json()['design'] == parent
        entries = api.get(f'/v1/rooms/{room_id}/conversation').json()['entries']
        undo_entry = next(e for e in entries if e.get('event_kind') == 'undo')
        assert undo_entry['from_version_id'] == child_id and undo_entry['to_version_id'] == base['design_id']
        assert len(app.state.store.list('designs', room_id)) == 5
