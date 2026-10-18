from concurrent.futures import ThreadPoolExecutor
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient


def test_sqlite_store_commits_rolls_back_and_reopens_immutable_records(tmp_path):
    from respace.store import SQLiteStore

    path = tmp_path / 'records.sqlite3'
    store = SQLiteStore(path)
    with pytest.raises(RuntimeError, match='transaction'):
        store.put('rooms', 'room', {'room_id': 'room'})
    with store.transaction():
        store.put('rooms', 'room', {'room_id': 'room', 'count': 0})
        with store.transaction():
            store.put('designs', 'design', {'room_id': 'room', 'scene': {'items': []}})
    with pytest.raises(ValueError, match='Immutable'):
        with store.transaction():
            store.put('rooms', 'room', {'room_id': 'room', 'count': 9})
            store.put('designs', 'design', {'room_id': 'room', 'scene': {'items': [1]}})
    reopened = SQLiteStore(path)
    assert reopened.get('rooms', 'room') == {'room_id': 'room', 'count': 0}
    assert reopened.list('designs', 'room') == [{'room_id': 'room', 'scene': {'items': []}}]

    def increment(_):
        with reopened.transaction():
            room = reopened.get('rooms', 'room')
            room['count'] += 1
            reopened.put('rooms', 'room', room)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(20)))
    assert store.get('rooms', 'room')['count'] == 20
    with pytest.raises(ValueError):
        with store.transaction():
            store.put('rooms', 'bad', {'value': float('nan')})
    with store.transaction():
        store.delete_room_records('room')
    assert reopened.get('rooms', 'room') is None
    assert reopened.get('designs', 'design') is None


def test_private_capture_files_are_immutable_safe_and_deleted_by_prefix(tmp_path):
    from respace.storage import LocalCaptureStorage

    root = tmp_path / 'captures'
    storage = LocalCaptureStorage(root)
    storage.put('rooms/one/capture/artifact', b'original', 'application/octet-stream')
    storage.put('rooms/one/capture/artifact', b'original', 'application/octet-stream')
    with pytest.raises(ValueError, match='different bytes'):
        storage.put('rooms/one/capture/artifact', b'replacement', 'application/octet-stream')
    assert LocalCaptureStorage(root).get('rooms/one/capture/artifact') == b'original'
    assert (root / 'rooms/one/capture/artifact').stat().st_mode & 0o777 == 0o600
    for key in ('', '../escape', '/absolute', 'rooms//one', 'rooms/./one', 'rooms/../one', 'rooms\\one'):
        with pytest.raises(ValueError):
            storage.put(key, b'bad', 'application/octet-stream')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret').write_bytes(b'private')
    (root / 'symlink').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        storage.get('symlink/secret')
    with pytest.raises(ValueError):
        storage.delete_prefix('symlink/')
    storage.put('rooms/one-more/capture/artifact', b'neighbor', 'application/octet-stream')
    storage.delete_prefix('rooms/one/')
    storage.delete_prefix('rooms/one/')
    with pytest.raises(FileNotFoundError):
        storage.get('rooms/one/capture/artifact')
    assert storage.get('rooms/one-more/capture/artifact') == b'neighbor'
    assert (outside / 'secret').read_bytes() == b'private'


def generation(capture_id):
    return {'operation_id': 'generate', 'capture_id': capture_id, 'planning_revision': 0,
            'expected_active_design_id': None, 'expected_active_revision': 0,
            'budget': '200.00', 'currency': 'USD', 'text': ''}


@pytest.fixture
def live_config(monkeypatch):
    for name in ('GEMINI_API_KEY', 'SERPAPI_API_KEY', 'GEMINI_PLANNING_MODEL',
                 'GEMINI_EXTRACTION_MODEL', 'GEMINI_SPATIAL_MODEL'):
        monkeypatch.setenv(name, 'configured-no-network-calls')
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)


def test_live_local_providers_fail_fast_before_creating_data_without_configuration(tmp_path, monkeypatch):
    from respace.local import create_local_app

    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'SERPAPI_API_KEY', 'GEMINI_PLANNING_MODEL',
                 'GEMINI_EXTRACTION_MODEL', 'GEMINI_SPATIAL_MODEL'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match='SERPAPI_API_KEY.*GEMINI_PLANNING_MODEL'):
        create_local_app(tmp_path / 'missing', live_providers=True)
    assert not (tmp_path / 'missing').exists()


def test_live_local_runtime_uses_real_adapters_without_cloud_dispatch(tmp_path, live_config, monkeypatch):
    from respace.local import create_local_app
    from test_api import QuestionModel, complete_room

    monkeypatch.setenv('RESPACE_SERVICE_ROLE', 'worker')
    monkeypatch.setenv('CLOUD_TASKS_QUEUE', 'must-not-use-cloud')
    app = create_local_app(tmp_path, live_providers=True)
    assert app.state.workers is None
    contexts = []
    async def act(self, context):
        contexts.append(context)
        return await QuestionModel().act(context)
    monkeypatch.setattr('respace.planning.GeminiPlanningModel.act', act)
    allowed = []
    async def review(store, operations, operation_id, *, allow_model):
        allowed.append(allow_model)
        operations.finish(operation_id, 'succeeded', {'result_kind': 'test', 'message_ids': []})
    monkeypatch.setattr('respace.review.review_command', review)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        response = api.post(f'/v1/rooms/{room_id}/planning-commands', json={
            'operation_id': 'review', 'capture_id': capture_id, 'planning_revision': 0,
            'text': 'Please preserve this.'})
        assert response.status_code == 200, response.json()
        assert api.post(f'/v1/rooms/{room_id}/designs', json=generation(capture_id)).status_code == 202
        pending = api.get('/v1/operations/generate').json()['operation']
        assert pending['state'] == 'needs_clarification', pending
        assert pending['pending_question']['text'] == 'What matters most?'
        assert contexts[0]['measured_context']
    assert allowed == [True]


def test_live_import_uses_geometry_only_planner_and_cannot_mix_simulated_data(tmp_path, live_config):
    from respace.local_testing import create_test_app
    from test_geometry import native_room

    def load_model(path):
        return native_room(), {'sha256': 'room-model', 'filename': 'fixture.glb', 'native_scan': False}
    app = create_test_app(tmp_path, ['fixture.glb'], load_model=load_model, live_providers=True)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room = api.get('/v1/rooms').json()['rooms'][0]
        warning = app.state.store.get('rooms', room['room_id'])['warnings'][0]
        assert warning['code'] == 'local_test' and 'live providers enabled' in warning['message']
    with pytest.raises(ValueError, match='separate data directory'):
        create_test_app(tmp_path, ['fixture.glb'], load_model=load_model)
    offline_dir = tmp_path / 'offline'
    with TestClient(create_test_app(offline_dir, ['fixture.glb'], load_model=load_model), headers={'X-Device-Id': 'device'}) as api:
        assert api.get('/v1/rooms').status_code == 200
    with pytest.raises(ValueError, match='separate data directory'):
        create_test_app(offline_dir, ['fixture.glb'], load_model=load_model, live_providers=True)


def test_provider_mode_survives_room_deletion_and_rejects_legacy_simulated_offers(tmp_path):
    from respace.local import bind_provider_mode
    from respace.store import SQLiteStore

    store = SQLiteStore(tmp_path / 'records.sqlite3')
    bind_provider_mode(store, False)
    with store.transaction():
        store.delete_room_records('deleted-room')
    with pytest.raises(ValueError, match='separate data directory'):
        bind_provider_mode(SQLiteStore(store.path), True)
    legacy = SQLiteStore(tmp_path / 'legacy.sqlite3')
    with legacy.transaction():
        legacy.put('offers', 'test-offer', {'product_url': 'https://offline.invalid/chair/0'})
    with pytest.raises(ValueError, match='separate data directory'):
        bind_provider_mode(legacy, True)


def test_local_api_reopens_capture_without_cloud_or_provider_calls(tmp_path, monkeypatch):
    from respace.local import create_local_app
    from test_api import complete_room

    monkeypatch.setenv('RESPACE_SERVICE_ROLE', 'worker')
    monkeypatch.setenv('CLOUD_TASKS_QUEUE', 'must-not-use-cloud')
    monkeypatch.setenv('GOOGLE_API_KEY', 'must-not-use-provider')
    monkeypatch.setenv('GEMINI_PLANNING_MODEL', 'must-not-use-provider')
    app = create_local_app(tmp_path)
    assert app.state.workers is None
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        assert api.get('/v1/health').status_code == 200
        room_id, capture_id = complete_room(api)
        artifact = api.get(f'/v1/rooms/{room_id}/artifacts/export').content
        assert api.post(f'/v1/rooms/{room_id}/designs', json=generation(capture_id)).status_code == 202
        operation = api.get('/v1/operations/generate').json()['operation']
        assert operation['state'] == 'rejected'
        assert operation['failure']['code'] == 'unavailable_capability'
    with TestClient(create_local_app(tmp_path), headers={'X-Device-Id': 'device'}) as reopened:
        detail = reopened.get(f'/v1/rooms/{room_id}').json()
        assert detail['capture_status']['state'] == 'complete'
        assert reopened.get(f'/v1/rooms/{room_id}/artifacts/export').content == artifact
        assert reopened.get('/v1/operations/generate').json()['operation'] == operation
        assert reopened.get(f'/v1/rooms/{room_id}', headers={'X-Device-Id': 'other'}).status_code == 404
        assert reopened.delete(f'/v1/rooms/{room_id}', params={'operation_id': 'delete'}).json()['deletion']['state'] == 'deleted'
    with TestClient(create_local_app(tmp_path), headers={'X-Device-Id': 'device'}) as reopened:
        assert reopened.get('/v1/rooms').json()['rooms'] == []
        assert reopened.get(f'/v1/rooms/{room_id}').status_code == 410
    assert list((tmp_path / 'captures' / 'rooms').rglob('export')) == []


@pytest.mark.parametrize('state', ['queued', 'running'])
def test_local_restart_resumes_work_and_leaves_pending_question_idle(tmp_path, state):
    from respace.local import create_local_app
    from test_api import EmptyProducts, QuestionModel, complete_room

    class CountingModel(QuestionModel):
        def __init__(self):
            self.calls = 0
            self.started = Event()

        async def act(self, context):
            self.calls += 1
            self.started.set()
            return await super().act(context)

    first = create_local_app(tmp_path, products=EmptyProducts(), model=CountingModel())
    with TestClient(first, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        first.state.operations.submit('device', room_id, 'generation', generation(capture_id))
        if state == 'running':
            first.state.operations.checkpoint('generate', 'preparing_context')
    model = CountingModel()
    with TestClient(create_local_app(tmp_path, products=EmptyProducts(), model=model), headers={'X-Device-Id': 'device'}) as api:
        assert model.started.wait(2), 'Startup must resume work without a client poll'
        for _ in range(100):
            operation = api.get('/v1/operations/generate').json()['operation']
            if operation['state'] == 'needs_clarification':
                break
            time.sleep(0.01)
        assert operation['state'] == 'needs_clarification'
        assert model.calls == 1
        question_id = operation['pending_question']['question_id']
    idle_model = CountingModel()
    with TestClient(create_local_app(tmp_path, products=EmptyProducts(), model=idle_model), headers={'X-Device-Id': 'device'}) as api:
        operation = api.get('/v1/operations/generate').json()['operation']
        assert operation['pending_question']['question_id'] == question_id
        assert idle_model.calls == 0
