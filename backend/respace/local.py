"""Run the existing API on one local process with private durable storage."""
import argparse
import os
from pathlib import Path

from .api import create_app
from .operations import DomainError
from .products import ProductError
from .storage import LocalCaptureStorage
from .store import SQLiteStore


def unavailable():
    raise DomainError('unavailable_capability', 'Live providers are disabled in the local runtime. Use an explicit controlled test scenario.', 503)


class LocalProducts:
    def __init__(self, store):
        self.store = store

    def search(self, *args, **kwargs):
        unavailable()

    find_more = search
    verify_selection = search

    def get_search(self, search_id):
        search = self.store.get('searches', search_id)
        if search is None:
            raise ProductError('unknown_search', 'Product search was not found')
        return search


class LocalModel:
    async def act(self, context):
        unavailable()


async def unavailable_spatial(*args, **kwargs):
    unavailable()


def bind_provider_mode(store, live_providers):
    mode = 'live' if live_providers else 'offline'
    with store.transaction():
        saved = store.get('local_runtime', 'providers')
        legacy_offline = (any(w.get('code') == 'offline_test' for room in store.list('rooms') for w in room.get('warnings', []))
                          or any(o.get('product_url', '').startswith('https://offline.invalid/') for o in store.list('offers')))
        current = saved['mode'] if saved else 'offline' if legacy_offline else mode
        if current != mode:
            raise ValueError('Use a separate data directory for live and simulated providers; this directory is bound to ' + current + ' providers.')
        store.put('local_runtime', 'providers', {'mode': mode})


def create_local_app(data_dir, *, products=None, model=None, spatial=None, edit_model=None, live_providers=False):
    if live_providers:
        required = ['SERPAPI_API_KEY', 'GEMINI_PLANNING_MODEL', 'GEMINI_EXTRACTION_MODEL']
        if spatial is None:
            required.append('GEMINI_SPATIAL_MODEL')
        missing = [key for key in required if not os.environ.get(key)]
        if not (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')):
            missing.append('GEMINI_API_KEY or GOOGLE_API_KEY')
        if missing:
            raise ValueError('Live providers require: ' + ', '.join(missing))
    directory = Path(data_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = SQLiteStore(directory / 'records.sqlite3')
    bind_provider_mode(store, live_providers)
    storage = LocalCaptureStorage(directory / 'captures')
    if live_providers:
        return create_app(store, storage, products, model, spatial, edit_model=edit_model,
                          local=True, allow_review_model=True)
    return create_app(store, storage, products if products is not None else LocalProducts(store),
                      model if model is not None else LocalModel(),
                      spatial if spatial is not None else unavailable_spatial,
                      edit_model=edit_model if edit_model is not None else LocalModel(), local=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, help='Defaults to .local/respace, or .local/respace-live with live providers.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--test-model', action='append', default=[], metavar='PATH',
                        help='Import a GLB test room; providers are simulated unless --live-providers is set (repeatable).')
    parser.add_argument('--test-shopping', type=Path, metavar='SCENARIO_JSON',
                        help='Use synthetic room context with live interview/shopping; stop at verified selection.')
    parser.add_argument('--live-providers', action='store_true',
                        help='Explicitly enable configured Gemini, merchant browser and SerpAPI calls; usage may incur charges.')
    parser.add_argument('--trace-file', type=Path, help='Write private agent/model/tool JSONL traces (includes interview and product evidence).')
    args = parser.parse_args()
    if args.test_shopping and (not args.live_providers or args.test_model):
        parser.error('--test-shopping requires --live-providers and cannot be combined with --test-model.')
    data_dir = args.data_dir or Path('.local/respace-live' if args.live_providers else '.local/respace')
    if args.trace_file:
        from .tracing import configure
        configure(args.trace_file)
    try:
        if args.test_shopping:
            from .shopping_testing import create_shopping_test_app
            app = create_shopping_test_app(data_dir, args.test_shopping)
        elif args.test_model:
            from .local_testing import create_test_app
            app = create_test_app(data_dir, args.test_model, live_providers=args.live_providers)
        else:
            app = create_local_app(data_dir, live_providers=args.live_providers)
    except ValueError as error:
        parser.error(str(error))
    import uvicorn
    from .tracing import emit
    emit('runtime.ready', live_providers=args.live_providers, test_shopping=bool(args.test_shopping),
         planning_model=os.environ.get('GEMINI_PLANNING_MODEL'), extraction_model=os.environ.get('GEMINI_EXTRACTION_MODEL'),
         data_dir=str(data_dir), port=args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
