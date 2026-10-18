"""Private capture storage; keys never grant public bucket access."""
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

import google.cloud.storage as cloud_storage
from google.api_core.exceptions import PreconditionFailed


class LocalCaptureStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key):
        if not isinstance(key, str) or '\\' in key or '\x00' in key or any(part in {'', '.', '..'} for part in key.split('/')):
            raise ValueError('Capture keys must be relative paths without traversal')
        path = self.root
        for part in key.split('/'):
            path = path / part
            if path.is_symlink():
                raise ValueError('Capture keys cannot follow symbolic links')
        return path

    def put(self, key, data, content_type):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with NamedTemporaryFile(dir=path.parent, prefix='.upload-', delete=False) as pending:
            temporary = Path(pending.name)
            try:
                pending.write(data)
                pending.flush()
                os.fsync(pending.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != data:
                        raise ValueError('Artifact identity already stores different bytes') from None
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink()

    def get(self, key):
        return self._path(key).read_bytes()

    def delete_prefix(self, prefix):
        directory_prefix = prefix.endswith('/')
        path = self._path(prefix[:-1] if directory_prefix else prefix)
        if directory_prefix:
            if path.is_dir():
                shutil.rmtree(path)
        elif path.parent.exists():
            for candidate in path.parent.iterdir():
                if candidate.name.startswith(path.name):
                    if candidate.is_dir() and not candidate.is_symlink():
                        shutil.rmtree(candidate)
                    else:
                        candidate.unlink()


class CaptureStorage:
    def __init__(self, bucket):
        self.bucket=cloud_storage.Client().bucket(bucket)

    def put(self, key, data, content_type):
        blob=self.bucket.blob(key)
        try:
            blob.upload_from_string(data,content_type=content_type,if_generation_match=0,timeout=30)
        except PreconditionFailed:
            if blob.download_as_bytes(timeout=30)!=data:
                raise ValueError('Artifact identity already stores different bytes') from None

    def get(self, key):
        return self.bucket.blob(key).download_as_bytes(timeout=30)

    def delete_prefix(self, prefix):
        for blob in self.bucket.list_blobs(prefix=prefix):
            blob.delete(timeout=30)
