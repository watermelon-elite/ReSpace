"""Plain JSON persistence; transactions serialize state changes across workers."""
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from contextlib import contextmanager
from contextvars import ContextVar

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


class SQLiteStore:
    """Local durable records using the same atomic boundaries as Postgres."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.close(os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600))
        self.path.chmod(0o600)
        self._connection: ContextVar[Any] = ContextVar('respace_sqlite_connection', default=None)
        with self._read() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('''CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(kind,id))''')
            connection.execute("CREATE INDEX IF NOT EXISTS records_room ON records(kind,json_extract(payload,'$.room_id'))")
            connection.execute("CREATE INDEX IF NOT EXISTS records_device ON records(kind,json_extract(payload,'$.device_id'))")

    @contextmanager
    def transaction(self):
        if self._connection.get() is not None:
            yield self
            return
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        token = self._connection.set(connection)
        try:
            connection.execute('BEGIN IMMEDIATE')
            yield self
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            self._connection.reset(token)
            connection.close()

    @contextmanager
    def _read(self):
        current = self._connection.get()
        if current is not None:
            yield current
        else:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            try:
                yield connection
            finally:
                connection.close()

    def get(self, kind, record_id):
        with self._read() as connection:
            row = connection.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, kind, record_id, payload):
        connection = self._writer()
        encoded = json.dumps(payload, allow_nan=False)
        if kind in {'designs', 'snapshots', 'selections'}:
            existing = self.get(kind, record_id)
            if existing is not None and existing != payload:
                raise ValueError('Immutable record cannot be replaced')
        connection.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind, record_id, encoded))
        return payload

    def list(self, kind, room_id=None):
        query = 'SELECT payload FROM records WHERE kind=?'
        params = [kind]
        if room_id is not None:
            query += " AND json_extract(payload,'$.room_id')=?"
            params.append(room_id)
        with self._read() as connection:
            return [json.loads(row[0]) for row in connection.execute(query + ' ORDER BY id', params)]

    def _writer(self):
        connection = self._connection.get()
        if connection is None:
            raise RuntimeError('Writes require a transaction')
        return connection

    def delete(self, kind, record_id):
        self._writer().execute('DELETE FROM records WHERE kind=? AND id=?', (kind, record_id))

    def delete_room_records(self, room_id):
        self._writer().execute("DELETE FROM records WHERE json_extract(payload,'$.room_id')=?", (room_id,))


class PostgresStore:
    def __init__(self, dsn):
        self.pool = ConnectionPool(dsn, min_size=1, max_size=5, kwargs={'sslmode':'require'})
        self._connection: ContextVar[Any] = ContextVar('respace_connection', default=None)
        with self.pool.connection() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, payload JSONB NOT NULL,
                PRIMARY KEY(kind,id))''')
            connection.execute("CREATE INDEX IF NOT EXISTS records_room ON records(kind,(payload->>'room_id'))")
            connection.execute("CREATE INDEX IF NOT EXISTS records_device ON records(kind,(payload->>'device_id'))")

    @contextmanager
    def transaction(self):
        if self._connection.get() is not None:
            yield self
            return
        with self.pool.connection() as connection, connection.transaction():
            # State writes are short; external I/O always happens outside this lock.
            connection.execute('SELECT pg_advisory_xact_lock(728309451)')
            token = self._connection.set(connection)
            try:
                yield self
            finally:
                self._connection.reset(token)

    @contextmanager
    def _read(self):
        current = self._connection.get()
        if current is not None:
            yield current
        else:
            with self.pool.connection() as connection:
                yield connection

    def get(self, kind, record_id):
        with self._read() as connection:
            row = connection.execute('SELECT payload FROM records WHERE kind=%s AND id=%s', (kind,record_id)).fetchone()
        return row[0] if row else None

    def put(self, kind, record_id, payload):
        connection = self._connection.get()
        if connection is None:
            raise RuntimeError('Writes require a transaction')
        json.dumps(payload, allow_nan=False)
        if kind in {'designs','snapshots','selections'}:
            existing = self.get(kind,record_id)
            if existing is not None and existing != payload:
                raise ValueError('Immutable record cannot be replaced')
        connection.execute('INSERT INTO records VALUES(%s,%s,%s) ON CONFLICT(kind,id) DO UPDATE SET payload=EXCLUDED.payload', (kind,record_id,Jsonb(payload)))
        return payload

    def list(self, kind, room_id=None):
        query='SELECT payload FROM records WHERE kind=%s'
        params=[kind]
        if room_id is not None:
            query+=" AND payload->>'room_id'=%s"
            params.append(room_id)
        with self._read() as connection:
            return [row[0] for row in connection.execute(query+' ORDER BY id',params)]

    def delete(self, kind, record_id):
        self._connection.get().execute('DELETE FROM records WHERE kind=%s AND id=%s',(kind,record_id))

    def delete_room_records(self, room_id):
        self._connection.get().execute("DELETE FROM records WHERE payload->>'room_id'=%s",(room_id,))
