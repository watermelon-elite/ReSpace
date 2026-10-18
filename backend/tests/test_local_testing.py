from fastapi.testclient import TestClient
import pytest

from respace.local_testing import TestEditModel as OfflineEditModel, create_test_app
from respace.operations import DomainError
from test_geometry import native_room


def test_local_model_runs_questions_products_geometry_edit_and_undo_without_network(tmp_path):
    def load_model(path):
        return native_room(), {'sha256': 'test-room', 'filename': 'fixture.glb', 'kind': 'glb_local_test', 'native_scan': False}
    with TestClient(create_test_app(tmp_path, ['fixture.glb'], load_model=load_model), headers={'X-Device-Id': 'local-device'}) as api:
        rooms = api.get('/v1/rooms').json()['rooms']
        assert len(rooms) == 1 and rooms[0]['capture_state'] == 'complete'
        room = rooms[0]
        request = {'operation_id': 'generate', 'capture_id': room['latest_capture_id'], 'planning_revision': 0,
                   'expected_active_revision': 0, 'intent': 'add', 'budget': '200.00'}
        assert api.post(f"/v1/rooms/{room['room_id']}/designs", json=request).status_code == 202
        for index in range(4):
            operation = api.get('/v1/operations/generate').json()['operation']
            if operation['state'] != 'needs_clarification':
                break
            question = operation['pending_question']
            answer = {'operation_id': 'generate', 'reply_id': f'answer-{index}', 'question_id': question['question_id'],
                      'expected_decision_revision': operation['decision_revision'], 'expected_question_revision': question['question_revision']}
            if question['kind'] == 'numeric':
                answer['number'] = 2
            else:
                answer['choice_ids'] = [question['choices'][0]['choice_id']]
            assert api.post('/v1/operations/generate/answers', json=answer).status_code == 200
        operation = api.get('/v1/operations/generate').json()['operation']
        assert operation['state'] == 'succeeded', operation.get('failure')
        design_id = operation['outcome']['design_id']
        design = api.get('/v1/designs/' + design_id).json()['design']
        assert design['scene']['items']
        assert 'Offline test' in design['scene']['summary']
        item = design['scene']['items'][0]
        remove = {'operation_id': 'remove', 'expected_active_design_id': design_id, 'expected_active_revision': 1, 'item_id': item['id']}
        api.post(f'/v1/designs/{design_id}/remove', json=remove)
        removed = api.get('/v1/operations/remove').json()['operation']
        assert removed['state'] == 'succeeded'
        undo = {'operation_id': 'undo', 'expected_active_design_id': removed['outcome']['design_id'], 'expected_active_revision': 2}
        assert api.post(f"/v1/rooms/{room['room_id']}/undo", json=undo).json()['operation']['outcome']['design_id'] == design_id
        assert api.get('/v1/designs/' + design_id).json()['design'] == design
        assert len(api.get('/v1/rooms').json()['rooms']) == 1
        more = {'operation_id': 'more', 'item_id': item['id'], 'expected_active_design_id': design_id,
                'expected_active_revision': 3}
        assert api.post(f'/v1/designs/{design_id}/find-more', json=more).status_code == 202
        found = api.get('/v1/operations/more').json()['operation']
        assert found['state'] == 'succeeded', found.get('failure')
        search_id = found['outcome']['search_id']
        choices = api.get('/v1/searches/' + search_id).json()['search']['displayed_choices']
        choice = next(c for c in choices if c['variant_id'] != item['variant_id'])
        swap = {**more, 'operation_id': 'swap', 'search_id': search_id,
                'variant_id': choice['variant_id'], 'offer_id': choice['offer_id']}
        assert api.post(f'/v1/designs/{design_id}/swap', json=swap).status_code == 202
        swapped = api.get('/v1/operations/swap').json()['operation']
        assert swapped['state'] == 'succeeded', swapped.get('failure')
        child = api.get('/v1/designs/' + swapped['outcome']['design_id']).json()['design']
        for key in ('position', 'yaw'):
            assert child['scene']['items'][0]['placement'][key] == item['placement'][key]
        assert child['scene']['items'][0]['variant_id'] == choice['variant_id']
        assert api.get('/v1/designs/' + design_id).json()['design'] == design


def test_deleted_import_is_not_resurrected_after_reopening_local_server(tmp_path):
    def load_model(path):
        return native_room(), {'sha256': 'test-room', 'filename': 'fixture.glb', 'native_scan': False}
    for iteration in range(2):
        with TestClient(create_test_app(tmp_path, ['fixture.glb'], load_model=load_model), headers={'X-Device-Id': 'local-device'}) as api:
            rooms = api.get('/v1/rooms').json()['rooms']
            if iteration == 0:
                assert len(rooms) == 1
                assert api.delete(f"/v1/rooms/{rooms[0]['room_id']}?operation_id=delete").status_code == 200
                assert api.get('/v1/rooms').json()['rooms'] == []
            else:
                assert rooms == []


@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['Move the chair and remove it', 'Do not remove this', 'Remove this if it fits'])
async def test_offline_language_boundary_rejects_unsupported_commands_explicitly(command):
    with pytest.raises(DomainError, match='one Move, Remove or Restore'):
        await OfflineEditModel().act({'command': command, 'selected_item_id': 'chair',
                                     'scene': {'items': [{'id': 'chair', 'category': 'chair'}]}})
