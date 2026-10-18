from datetime import datetime, timedelta, timezone

import pytest

from respace.operations import OperationService
from respace.workers import WorkerService
from test_operations import room


class Queue:
    def __init__(self):
        self.tasks = {}
        self.fail_once = False

    def dispatch(self, record):
        self.tasks[record["task_name"]] = record.copy()
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Lost create-task response")


def operation(store):
    room(store)
    return OperationService(store).submit("device", "room", "generation", {
        "operation_id": "op", "capture_id": "capture", "planning_revision": 0,
        "expected_active_revision": 0, "budget": "100.00"})


def test_outbox_is_durable_before_dispatch_and_recovers_lost_dispatch_response(store):
    operation(store)
    queue = Queue()
    queue.fail_once = True
    worker = WorkerService(store, queue, None)
    pending = worker.enqueue("op")
    assert pending["state"] == "pending"
    assert store.get("worker_outbox", pending["outbox_id"])["failure"]["code"] == "dispatch_failed"
    recovered = WorkerService(store, queue, None).recover()
    assert recovered["dispatched"] == 1
    assert len(queue.tasks) == 1
    assert store.get("worker_outbox", pending["outbox_id"])["state"] == "dispatched"
    assert worker.enqueue("op")["generation"] == pending["generation"]


def test_recovery_can_replace_a_lost_old_task_without_an_operation_time_cutoff(store):
    operation(store)
    clock_value = datetime.now(timezone.utc)
    worker = WorkerService(store, Queue(), None, clock=lambda: clock_value.isoformat())
    queued = worker.enqueue("op")
    clock_value += timedelta(days=40)
    result = worker.recover()
    assert result["dispatched"] == 1
    assert store.get("operations", "op")["state"] == "queued"
    assert store.get("operations", "op")["worker_generation"] == queued["generation"] + 1


@pytest.mark.asyncio
async def test_cancelled_or_deleted_room_cannot_schedule_or_resume_late_delivery(store):
    operation(store)
    calls = []
    async def step(kind, operation_id):
        calls.append(operation_id)
    worker = WorkerService(store, Queue(), step)
    queued = worker.enqueue("op")
    OperationService(store).cancel("device", "op", "cancel")
    assert worker.enqueue("op") is None
    assert await worker.deliver("op", queued["generation"]) == {"state": "stale"}
    assert calls == [] and worker.recover()["dispatched"] == 0
    with store.transaction():
        current = store.get("operations", "op")
        current["state"] = "queued"
        store.put("operations", "op", current)
        store.put("deletions", "room", {"room_id": "room", "state": "pending"})
    assert worker.enqueue("op") is None


@pytest.mark.asyncio
async def test_completed_stage_dispatches_one_continuation_and_duplicate_delivery_is_harmless(store):
    operation(store)
    queue = Queue()
    calls = []
    async def step(kind, operation_id):
        with store.transaction():
            current = store.get("operations", operation_id)
            current.setdefault("steps", []).append({"phase": "saved_output", "value": "provider-result"})
            store.put("operations", operation_id, current)
        calls.append((kind, operation_id))
    worker = WorkerService(store, queue, step)
    queued = worker.enqueue("op")
    first = await worker.deliver("op", queued["generation"])
    assert first["continuation_generation"] == queued["generation"] + 1
    assert len(store.get("operations", "op")["steps"]) == 1
    assert await worker.deliver("op", queued["generation"]) == {"state": "stale"}
    assert len(calls) == 1 and len(queue.tasks) == 2
    assert store.get("operations", "op")["worker_lease"] is None


@pytest.mark.asyncio
async def test_pending_question_releases_lease_and_reopen_preserves_exact_question(store):
    operation(store)
    queue = Queue()
    operations = OperationService(store)
    async def step(kind, operation_id):
        operations.ask(operation_id, {"kind": "single_choice", "context": "interview", "topic": "activity",
            "text": "What happens here?", "choices": [{"choice_id": "read", "label": "Read"}],
            "allow_skip": True, "allow_delegate": True})
    worker = WorkerService(store, queue, step)
    queued = worker.enqueue("op")
    await worker.deliver("op", queued["generation"])
    saved = operations.get("device", "op")
    question = saved["pending_question"]
    assert saved["worker_lease"] is None and len(queue.tasks) == 1
    assert WorkerService(store, queue, step).recover() == {"dispatched": 0, "pending": 0}
    assert operations.get("device", "op")["pending_question"] == question
    operations.answer("device", "op", {"operation_id": "op", "question_id": question["question_id"],
        "reply_id": "reply", "expected_question_revision": question["question_revision"],
        "expected_decision_revision": 0, "choice_ids": ["read"], "action": "answer"})
    resumed = worker.enqueue("op")
    assert resumed["generation"] == queued["generation"] + 1
    assert len(operations.get("device", "op")["answer_history"]) == 1


@pytest.mark.asyncio
async def test_expired_claim_recovers_with_new_generation_and_fences_late_worker_output(store):
    from respace.operations import DomainError
    from respace.workers import assert_worker_lease, worker_context

    operation(store)
    clock_value = datetime.now(timezone.utc)
    clock = lambda: clock_value.isoformat()
    queue = Queue()
    async def step(kind, operation_id):
        OperationService(store).finish(operation_id, "succeeded")
    worker = WorkerService(store, queue, step, clock=clock)
    original = worker.enqueue("op")
    with store.transaction():
        current = store.get("operations", "op")
        current["worker_lease"] = {"generation": original["generation"], "token": "dead-worker",
                                   "expires_at": (clock_value - timedelta(seconds=1)).isoformat()}
        store.put("operations", "op", current)
    assert worker.recover()["dispatched"] == 1
    generation = store.get("operations", "op")["worker_generation"]
    assert generation == original["generation"] + 1
    old_context = worker_context.set({"operation_id": "op", "generation": original["generation"],
                                      "token": "dead-worker", "clock": clock})
    try:
        with pytest.raises(DomainError, match="no longer owns"):
            assert_worker_lease(store, "op")
    finally:
        worker_context.reset(old_context)
    assert await worker.deliver("op", original["generation"]) == {"state": "stale"}
    await worker.deliver("op", generation)
    assert store.get("operations", "op")["state"] == "succeeded"
    assert len(store.list("messages", "room")) == 2


@pytest.mark.asyncio
async def test_live_claim_refuses_concurrent_delivery_without_releasing_ownership(store):
    import asyncio

    operation(store)
    started, release = asyncio.Event(), asyncio.Event()
    async def step(kind, operation_id):
        started.set()
        await release.wait()
    worker = WorkerService(store, Queue(), step)
    queued = worker.enqueue("op")
    first = asyncio.create_task(worker.deliver("op", queued["generation"]))
    await started.wait()
    assert await worker.deliver("op", queued["generation"]) == {"state": "busy"}
    assert store.get("operations", "op")["worker_lease"] is not None
    release.set()
    await first


@pytest.mark.asyncio
async def test_step_exception_releases_claim_for_cloud_redelivery(store):
    operation(store)
    async def step(kind, operation_id):
        raise RuntimeError("worker process stopped")
    worker = WorkerService(store, Queue(), step)
    queued = worker.enqueue("op")
    with pytest.raises(RuntimeError):
        await worker.deliver("op", queued["generation"])
    assert store.get("operations", "op")["worker_lease"] is None
    assert store.get("worker_outbox", queued["outbox_id"])["state"] == "dispatched"


@pytest.mark.asyncio
async def test_bounded_controller_persists_model_output_before_next_delivery_and_releases_at_question(store):
    from respace.planning import PlanningController

    operation(store)
    with store.transaction():
        store.put("captures", "capture", {"capture_id": "capture", "room_id": "room", "state": "complete",
                                            "measured_context": {}})
    class Model:
        calls = 0
        async def act(self, context):
            self.calls += 1
            return {"action": "ask_user", "payload": {"kind": "single_choice", "topic": "activity",
                "text": "What happens here?", "choices": [{"choice_id": "read", "label": "Read"}],
                "allow_skip": True, "allow_delegate": True}}
    model = Model()
    controller = PlanningController(store, OperationService(store), None, model, None)
    async def step(kind, operation_id):
        await controller.run(operation_id, bounded=True)
    queue = Queue()
    worker = WorkerService(store, queue, step)
    task = worker.enqueue("op")
    await worker.deliver("op", task["generation"])
    assert model.calls == 0
    assert store.get("operations", "op")["controller"]["initial_products"]["state"] == "empty"
    await worker.deliver("op", 2)
    assert model.calls == 1
    assert store.get("operations", "op")["controller"]["pending_action"]["action"] == "ask_user"
    restarted_controller = PlanningController(store, OperationService(store), None, model, None)
    async def resume(kind, operation_id):
        await restarted_controller.run(operation_id, bounded=True)
    await WorkerService(store, queue, resume).deliver("op", 3)
    current = store.get("operations", "op")
    assert current["pending_question"]["text"] == "What happens here?"
    assert current["worker_lease"] is None and model.calls == 1


def test_google_tasks_adapter_uses_deterministic_identity_https_and_oidc_without_room_media(store):
    import json
    from google.api_core.exceptions import AlreadyExists
    from respace.workers import GoogleCloudTasksDispatcher

    operation(store)
    class Client:
        requests = []
        def create_task(self, *, request, timeout):
            self.requests.append(request)
            if len(self.requests) > 1:
                raise AlreadyExists("Existing task")
    client = Client()
    adapter = GoogleCloudTasksDispatcher("project", "region", "queue", "https://worker.run.app",
                                         "tasks@project.iam.gserviceaccount.com", client=client)
    record = WorkerService(store, Queue(), None).enqueue("op")
    adapter.dispatch(record)
    adapter.dispatch(record)
    assert client.requests[0] == client.requests[1]
    task = client.requests[0]["task"]
    assert task["name"].endswith("/" + record["task_name"])
    assert task["http_request"]["url"] == "https://worker.run.app/internal/work"
    assert task["http_request"]["oidc_token"] == {"service_account_email": "tasks@project.iam.gserviceaccount.com",
                                                  "audience": "https://worker.run.app"}
    assert json.loads(task["http_request"]["body"]) == {"operation_id": "op", "generation": 1}
    with pytest.raises(ValueError, match="HTTPS"):
        GoogleCloudTasksDispatcher("p", "r", "q", "http://worker.run.app", "sa", client=client)


def test_worker_routes_are_mounted_only_on_the_private_service_role(store, monkeypatch):
    from fastapi.testclient import TestClient
    from respace.api import create_app
    from respace.workers import GoogleCloudTasksDispatcher
    from test_api import MemoryStorage, EmptyProducts, QuestionModel

    monkeypatch.delenv("CLOUD_TASKS_QUEUE", raising=False)
    monkeypatch.setenv("RESPACE_SERVICE_ROLE", "api")
    public = TestClient(create_app(store, MemoryStorage(), EmptyProducts(), QuestionModel(), spatial=lambda *a: None))
    assert public.post("/internal/work", json={"operation_id": "op", "generation": 1}).status_code == 404
    assert public.post("/internal/recover").status_code == 404
    monkeypatch.setenv("RESPACE_SERVICE_ROLE", "worker")
    monkeypatch.setattr(GoogleCloudTasksDispatcher, "from_env", classmethod(lambda cls: Queue()))
    app = create_app(store, MemoryStorage(), EmptyProducts(), QuestionModel(), spatial=lambda *a: None)
    private = TestClient(app)
    assert private.get("/v1/rooms", headers={"X-Device-Id": "device"}).status_code == 404
    assert private.post("/internal/work", json={"operation_id": "missing", "generation": 1}).json() == {"state": "stale"}
    assert private.post("/internal/work", json={"operation_id": "op", "generation": 0}).status_code == 422
    assert private.post("/internal/recover").json() == {"dispatched": 0, "pending": 0}
