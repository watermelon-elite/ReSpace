"""Opt-in JSONL traces of model actions and tools; never records credentials."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4


logger = logging.getLogger('respace.agent')
logger.setLevel(logging.INFO)
logger.propagate = False
context: ContextVar[dict] = ContextVar('agent_trace', default={})


def configure(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600))
    path.chmod(0o600)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.addHandler(logging.FileHandler(path))


def _redact(value, secrets):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if re.search(r'api.?key|authorization|password|secret|credential', str(key), re.I)
                else _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, '[REDACTED]')
        return re.sub(r'([?&](?:key|api_key|token)=)[^&\s]+', r'\1[REDACTED]', value, flags=re.I)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def emit(event, **fields):
    if logger.handlers:
        secrets = [value for name, value in os.environ.items()
                   if len(value) >= 8 and re.search(r'KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL', name)]
        logger.info(json.dumps(_redact({'at': datetime.now(timezone.utc).isoformat(),
                                      **context.get(), 'event': event, **fields}, secrets), default=str))


@contextmanager
def span(event, **fields):
    parent = context.get()
    token = context.set({**parent, **{key: fields[key] for key in ('operation_id', 'search_id', 'candidate_id') if key in fields},
                         'span_id': str(uuid4()), 'parent_span_id': parent.get('span_id')})
    started = perf_counter()
    emit(event + '.started', **fields)
    result = {}
    try:
        yield result
    except BaseException as error:
        emit(event + '.failed', elapsed_ms=round((perf_counter() - started) * 1000, 2),
             error_type=type(error).__name__, error=str(error), code=getattr(error, 'code', None), **result)
        raise
    else:
        emit(event + '.completed', elapsed_ms=round((perf_counter() - started) * 1000, 2), **result)
    finally:
        context.reset(token)


def usage(response):
    metadata = getattr(response, 'usage_metadata', None)
    return metadata.model_dump(mode='json') if metadata is not None else None
