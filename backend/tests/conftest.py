import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy

import pytest


class SQLiteStore:
    """Test-only transactional substitute for the production JSONB store."""

    def __init__(self, path):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(kind,id))')
        self.depth = 0

    @contextmanager
    def transaction(self):
        outer = self.depth == 0
        if outer:
            self.connection.execute('BEGIN IMMEDIATE')
        self.depth += 1
        try:
            yield self
            if outer:
                self.connection.commit()
        except BaseException:
            if outer:
                self.connection.rollback()
            raise
        finally:
            self.depth -= 1

    def get(self, kind, record_id):
        row = self.connection.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, kind, record_id, payload):
        self.connection.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind, record_id, json.dumps(payload, allow_nan=False)))
        return deepcopy(payload)

    def list(self, kind, room_id=None):
        records = [json.loads(row[0]) for row in self.connection.execute('SELECT payload FROM records WHERE kind=? ORDER BY id', (kind,))]
        return [record for record in records if room_id is None or record.get('room_id') == room_id]

    def delete(self, kind, record_id):
        self.connection.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, record_id))

    def delete_room_records(self, room_id):
        self.connection.execute("DELETE FROM records WHERE json_extract(payload,'$.room_id')=?", (room_id,))


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(tmp_path / 'records.sqlite')
