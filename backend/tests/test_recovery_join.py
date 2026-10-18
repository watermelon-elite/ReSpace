"""Local cloud-protocol joins; deployed provider/storage acceptance stays separate."""
import asyncio

import httpx
import pytest

from respace.api import create_app
from respace.workers import GoogleCloudTasksDispatcher
from test_api import MemoryStorage, QuestionModel
from test_edits import Products, base_request, move, setup_edit
from test_removal import setup_supported_api
from test_workers import Queue


def queued_app(store, storage, queue, monkeypatch, edit_model=None):
    monkeypatch.setenv('CLOUD_TASKS_QUEUE', 'test-only-queue')
    monkeypatch.setattr(GoogleCloudTasksDispatcher, 'from_env', classmethod(lambda cls: queue))
    return create_app(store, storage, Products(), QuestionModel(), lambda *args: None, edit_model=edit_model)


@pytest.mark.asyncio
@pytest.mark.parametrize('stop', ['cancel', 'delete'])
async def test_inflight_worker_cannot_publish_after_http_cancel_or_delete(store, monkeypatch, stop):
    _, _, parent = setup_edit(store, {})
    with store.transaction():
        room = store.get('rooms', 'room')
        room.update(name='Captured room', created_at='2026-10-18T00:00:00Z', metadata_revision=0)
        store.put('rooms', 'room', room)
    entered, release = asyncio.Event(), asyncio.Event()
    class SlowModel:
        async def act(self, context):
            entered.set()
            await release.wait()
            return {'action': 'execute_plan', 'payload': {'plan': {'summary': 'Move desk', 'moves': [move()]}}}
    storage, queue = MemoryStorage(), Queue()
    storage.put('rooms/room/capture/photo', b'private photo', 'image/jpeg')
    app = queued_app(store, storage, queue, monkeypatch, SlowModel())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'X-Device-Id': 'device'}) as api:
        response = await api.post('/v1/designs/parent/chat', json={**base_request(), 'text': 'Move the desk'})
        assert response.status_code == 202
        delivery = asyncio.create_task(app.state.workers.deliver('edit', 1))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert (await api.post('/v1/designs/parent/remove', json={**base_request('competing'), 'item_id': 'i_a_0'})).status_code == 409
            assert (await api.post('/v1/rooms', json={'operation_id': 'other-room'})).status_code == 200
            if stop == 'cancel':
                response = await api.post('/v1/operations/edit/cancel', json={'operation_id': 'edit', 'cancellation_id': 'cancel'})
            else:
                response = await api.delete('/v1/rooms/room?operation_id=delete')
            assert response.status_code == 200
        finally:
            release.set()
            await asyncio.wait_for(delivery, 2)
        assert app.state.workers.recover()['dispatched'] == 0
        if stop == 'cancel':
            assert (await api.get('/v1/operations/edit')).json()['operation']['state'] == 'cancelled'
            assert (await api.get('/v1/designs/parent')).json()['design'] == parent
            assert storage.blobs['rooms/room/capture/photo'] == b'private photo'
        else:
            assert (await api.get('/v1/designs/parent')).status_code == 404
            assert (await api.get('/v1/operations/edit')).status_code == 404
            assert storage.blobs == {}
        assert len(store.list('designs', 'room')) == (1 if stop == 'cancel' else 0)


@pytest.mark.asyncio
async def test_saved_answer_survives_failed_dispatch_restart_and_lost_edit_undo_responses(store, monkeypatch):
    setup_supported_api(store, must_have=True)
    queue, storage = Queue(), MemoryStorage()
    app = queued_app(store, storage, queue, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'X-Device-Id': 'device'}) as api:
        request = {**base_request('remove'), 'item_id': 'i_a_0'}
        assert (await api.post('/v1/designs/parent/remove', json=request)).status_code == 202
        await app.state.workers.deliver('remove', 1)
        waiting = (await api.get('/v1/operations/remove')).json()['operation']
        assert waiting['worker_lease'] is None and waiting['state'] == 'needs_clarification'
        question = waiting['pending_question']
        answer = {'operation_id': 'remove', 'reply_id': 'approve', 'question_id': question['question_id'],
                  'expected_decision_revision': 0, 'expected_question_revision': 1, 'choice_ids': ['allow_consequences']}
        queue.fail_once = True
        assert (await api.post('/v1/operations/remove/answers', json=answer)).status_code == 200
        restarted = queued_app(store, storage, queue, monkeypatch)
        assert restarted.state.workers.recover()['dispatched'] == 1
        await restarted.state.workers.deliver('remove', 2)
        completed = (await api.get('/v1/operations/remove')).json()['operation']
        assert completed['state'] == 'succeeded'
        assert (await api.post('/v1/operations/remove/answers', json=answer)).json()['operation']['outcome'] == completed['outcome']
        assert (await api.post('/v1/designs/parent/remove', json=request)).json()['operation']['outcome'] == completed['outcome']
        child = completed['outcome']['design_id']
        undo = {'operation_id': 'undo', 'expected_active_design_id': child, 'expected_active_revision': 2}
        first = (await api.post('/v1/rooms/room/undo', json=undo)).json()
        assert first['operation']['outcome']['design_id'] == 'parent'
        assert (await api.post('/v1/rooms/room/undo', json=undo)).json() == first
        entries = (await api.get('/v1/rooms/room/conversation')).json()['entries']
        assert len([e for e in entries if e.get('event_kind') == 'undo']) == 1
        assert len(store.list('designs', 'room')) == 2
