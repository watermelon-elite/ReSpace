"""Private capture storage; keys never grant public bucket access."""
from google.cloud import storage
from google.api_core.exceptions import PreconditionFailed


class CaptureStorage:
    def __init__(self, bucket):
        self.bucket=storage.Client().bucket(bucket)

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
