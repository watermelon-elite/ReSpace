"""Cloud Tasks delivery of bounded existing-controller stages through a durable outbox."""

import asyncio
from contextvars import ContextVar
from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from typing import Any
from urllib.parse import urlsplit

from .operations import DomainError, TERMINAL, identity, now


worker_context: ContextVar[Any] = ContextVar("respace_worker_delivery", default=None)


def assert_worker_lease(store, operation_id):
    context = worker_context.get()
    if context is None:
        return
    operation = store.get("operations", operation_id) or {}
    lease = operation.get("worker_lease") or {}
    if (context["operation_id"] != operation_id or lease.get("token") != context["token"]
            or lease.get("generation") != context["generation"]
            or lease.get("expires_at", "") <= context["clock"]()):
        raise DomainError("stale_delivery", "This worker delivery no longer owns the operation.")


class GoogleCloudTasksDispatcher:
    def __init__(self, project, location, queue, worker_url, service_account, *, client=None):
        parsed = urlsplit(worker_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Worker URL must be a private Cloud Run HTTPS service origin.")
        if not all((project, location, queue, service_account)):
            raise ValueError("Cloud Tasks project, location, queue and invoker identity are required.")
        if client is None:
            from google.cloud import tasks_v2
            client = tasks_v2.CloudTasksClient()
        self.client = client
        self.parent = f"projects/{project}/locations/{location}/queues/{queue}"
        self.worker_url, self.service_account = worker_url.rstrip("/"), service_account

    @classmethod
    def from_env(cls):
        return cls(os.environ["GOOGLE_CLOUD_PROJECT"], os.environ["CLOUD_TASKS_LOCATION"],
                   os.environ["CLOUD_TASKS_QUEUE"], os.environ["WORKER_URL"],
                   os.environ["TASKS_SERVICE_ACCOUNT"])

    def dispatch(self, record):
        from google.api_core.exceptions import AlreadyExists

        task = {"name": f'{self.parent}/tasks/{record["task_name"]}', "dispatch_deadline": {"seconds": 240},
                "http_request": {"http_method": "POST", "url": self.worker_url + "/internal/work",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"operation_id": record["operation_id"], "generation": record["generation"]}).encode(),
                    "oidc_token": {"service_account_email": self.service_account, "audience": self.worker_url}}}
        try:
            self.client.create_task(request={"parent": self.parent, "task": task}, timeout=20)
        except AlreadyExists:
            pass


class WorkerService:
    def __init__(self, store, dispatcher, step_callback, *, lease_seconds=240, clock=now):
        if lease_seconds <= 30:
            raise ValueError("Worker lease must exceed the bounded-stage timeout margin.")
        self.store, self.dispatcher, self.step = store, dispatcher, step_callback
        self.lease_seconds, self.clock = lease_seconds, clock

    def _runnable(self, operation):
        room = self.store.get("rooms", operation["room_id"]) if operation else None
        return bool(operation and room and room.get("current_operation_id") == operation["operation_id"]
                    and operation["state"] not in TERMINAL
                    and operation["state"] != "needs_clarification" and not operation.get("pending_question")
                    and self.store.get("deletions", operation["room_id"]) is None)

    def _new_outbox(self, operation):
        generation = operation.get("worker_generation", 0) + 1
        operation["worker_generation"] = generation
        outbox_id = f'{operation["operation_id"]}:{generation}'
        record = {"schema_version": 1, "outbox_id": outbox_id, "operation_id": operation["operation_id"],
                  "room_id": operation["room_id"], "generation": generation, "state": "pending",
                  "task_name": f'respace-{sha256(operation["operation_id"].encode()).hexdigest()[:32]}-{generation}',
                  "created_at": self.clock(), "dispatch_attempts": 0, "failure": None}
        self.store.put("operations", operation["operation_id"], operation)
        self.store.put("worker_outbox", outbox_id, record)
        return record

    def _dispatch(self, record):
        try:
            self.dispatcher.dispatch(record)
            failure = None
        except Exception:
            failure = {"code": "dispatch_failed", "message": "Continuation dispatch will retry.", "retryable": True}
        with self.store.transaction():
            current = self.store.get("worker_outbox", record["outbox_id"])
            if current is None or current["state"] in ("completed", "superseded"):
                return current or record
            current.update(state="pending" if failure else "dispatched", failure=failure,
                           dispatch_attempts=current["dispatch_attempts"] + 1, dispatched_at=self.clock())
            self.store.put("worker_outbox", record["outbox_id"], current)
            return current

    def enqueue(self, operation_id):
        with self.store.transaction():
            operation = self.store.get("operations", operation_id)
            if not self._runnable(operation):
                return None
            record = self.store.get("worker_outbox", f'{operation_id}:{operation.get("worker_generation", 0)}')
            if record is None or record["state"] in ("completed", "superseded"):
                record = self._new_outbox(operation)
        return self._dispatch(record) if record["state"] == "pending" else record

    async def deliver(self, operation_id, generation):
        with self.store.transaction():
            operation = self.store.get("operations", operation_id)
            record = self.store.get("worker_outbox", f"{operation_id}:{generation}")
            if (operation is None or record is None or operation.get("worker_generation") != generation
                    or record["state"] in ("completed", "superseded")):
                return {"state": "stale"}
            if not self._runnable(operation):
                record.update(state="completed", completed_at=self.clock())
                operation["worker_lease"] = None
                self.store.put("worker_outbox", record["outbox_id"], record)
                self.store.put("operations", operation_id, operation)
                return {"state": "waiting" if operation.get("pending_question") else "stale"}
            lease = operation.get("worker_lease") or {}
            if lease.get("expires_at", "") > self.clock():
                return {"state": "busy"}
            token = identity()
            operation["worker_lease"] = {"token": token, "generation": generation,
                "expires_at": (datetime.fromisoformat(self.clock()) + timedelta(seconds=self.lease_seconds)).isoformat()}
            self.store.put("operations", operation_id, operation)
        context_token = worker_context.set({"operation_id": operation_id, "generation": generation,
                                            "token": token, "clock": self.clock})
        try:
            await asyncio.wait_for(self.step(operation["kind"], operation_id), timeout=self.lease_seconds - 30)
        except BaseException:
            with self.store.transaction():
                current = self.store.get("operations", operation_id)
                if current and (current.get("worker_lease") or {}).get("token") == token:
                    current["worker_lease"] = None
                    self.store.put("operations", operation_id, current)
            raise
        finally:
            worker_context.reset(context_token)
        continuation = None
        with self.store.transaction():
            current = self.store.get("operations", operation_id)
            if not current or (current.get("worker_lease") or {}).get("token") != token:
                return {"state": "stale"}
            record = self.store.get("worker_outbox", record["outbox_id"])
            record.update(state="completed", completed_at=self.clock())
            self.store.put("worker_outbox", record["outbox_id"], record)
            current["worker_lease"] = None
            self.store.put("operations", operation_id, current)
            if self._runnable(current):
                continuation = self._new_outbox(current)
        if continuation:
            self._dispatch(continuation)
        return {"state": "completed", "generation": generation,
                "continuation_generation": continuation["generation"] if continuation else None}

    def recover(self):
        """Called by authenticated Scheduler: recover dispatch gaps and expired claims."""
        records = []
        with self.store.transaction():
            for operation in self.store.list("operations"):
                if not self._runnable(operation):
                    continue
                lease = operation.get("worker_lease") or {}
                record = self.store.get("worker_outbox", f'{operation["operation_id"]}:{operation.get("worker_generation", 0)}')
                if lease:
                    if lease.get("expires_at", "") > self.clock():
                        continue
                    if record:
                        record["state"] = "superseded"
                        self.store.put("worker_outbox", record["outbox_id"], record)
                    operation["worker_lease"] = None
                    record = self._new_outbox(operation)
                elif record is None or record["state"] in ("completed", "superseded"):
                    record = self._new_outbox(operation)
                elif (record["state"] == "dispatched" and datetime.fromisoformat(record["dispatched_at"])
                      + timedelta(seconds=self.lease_seconds * 2) <= datetime.fromisoformat(self.clock())):
                    record["state"] = "superseded"
                    self.store.put("worker_outbox", record["outbox_id"], record)
                    record = self._new_outbox(operation)
                if record["state"] == "pending":
                    records.append(record)
        outcomes = [self._dispatch(record) for record in records]
        return {"dispatched": sum(record["state"] == "dispatched" for record in outcomes),
                "pending": sum(record["state"] == "pending" for record in outcomes)}
