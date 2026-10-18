"""Run the existing API on one local process with private durable storage."""
import argparse
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


def create_local_app(data_dir, *, products=None, model=None, spatial=None, edit_model=None):
    directory = Path(data_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = SQLiteStore(directory / 'records.sqlite3')
    storage = LocalCaptureStorage(directory / 'captures')
    return create_app(store, storage, products if products is not None else LocalProducts(store),
                      model if model is not None else LocalModel(),
                      spatial if spatial is not None else unavailable_spatial,
                      edit_model=edit_model if edit_model is not None else LocalModel(), local=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('.local/respace'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--test-model', action='append', default=[], metavar='PATH',
                        help='Import a GLB into an explicitly controlled offline test scenario (repeatable).')
    args = parser.parse_args()
    if args.test_model:
        from .local_testing import create_test_app
        app = create_test_app(args.data_dir, args.test_model)
    else:
        app = create_local_app(args.data_dir)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
