import asyncio
import json

import pytest

from respace import tracing


def test_trace_links_threaded_tools_and_redacts_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'private-test-credential')
    path = tmp_path / 'agent.jsonl'
    tracing.configure(path)
    try:
        async def run():
            with tracing.span('agent', operation_id='operation'):
                def tool():
                    with tracing.span('tool', candidate_id='candidate') as result:
                        result['output'] = {'api_key': 'another-secret', 'url': 'https://example.com?key=unlisted-secret',
                                            'text': 'private-test-credential'}
                await asyncio.to_thread(tool)
                with pytest.raises(ValueError), tracing.span('provider'):
                    raise ValueError('private-test-credential')
        asyncio.run(run())
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert all(record['operation_id'] == 'operation' for record in records)
        assert records[1]['parent_span_id'] == records[0]['span_id']
        assert records[2]['output'] == {'api_key': '[REDACTED]', 'url': 'https://example.com?key=[REDACTED]', 'text': '[REDACTED]'}
        assert records[4]['event'] == 'provider.failed' and records[4]['error'] == '[REDACTED]'
        assert all(record['elapsed_ms'] >= 0 for record in records if 'elapsed_ms' in record)
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        for handler in tracing.logger.handlers[:]:
            tracing.logger.removeHandler(handler)
            handler.close()
