from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class BlobRef:
    name: str
    etag: Optional[str]


class AzureBlobExampleStore:
    def __init__(self, connection_string: str, container: str) -> None:
        self.connection_string = connection_string
        self.container = container

        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency for Azure Blob. Install `azure-storage-blob`."
            ) from e

        self._svc = BlobServiceClient.from_connection_string(connection_string)
        self._container_client = self._svc.get_container_client(container)

    def list_json_blobs(self, prefix: str = "") -> list[BlobRef]:
        blobs = []
        for b in self._container_client.list_blobs(name_starts_with=prefix):
            if str(b.name).lower().endswith(".json"):
                blobs.append(BlobRef(name=str(b.name), etag=getattr(b, "etag", None)))
        blobs.sort(key=lambda r: r.name)
        return blobs

    def download_blob(self, name: str) -> tuple[bytes, Optional[str]]:
        blob_client = self._container_client.get_blob_client(name)
        props = blob_client.get_blob_properties()
        etag = getattr(props, "etag", None)
        data = blob_client.download_blob().readall()
        return data, etag

    def load_json(self, name: str) -> dict[str, Any]:
        data, _ = self.download_blob(name)
        return json.loads(data.decode("utf-8"))

