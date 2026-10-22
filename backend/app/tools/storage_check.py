"""Operator probe for the configured object store: writes, reads back, compares and deletes one small object.

    python -m app.tools.storage_check

Run it once after provisioning a bucket (and after rotating credentials), with the environment variables the API will
use. It only touches a throwaway key under `healthcheck/`, never evidence, and it prints which step failed without ever
printing credentials. Exit codes: 0 all steps passed, 1 a step failed, 2 the configured provider is not an S3 store.
"""

from __future__ import annotations

import sys
import uuid

from app.core.config import Settings, get_settings
from app.modules.evidence.storage import StorageError, build_store


def run(settings: Settings) -> int:
    if settings.storage_provider != "s3":
        print(f"STORAGE_PROVIDER is {settings.storage_provider!r}; this probe is for STORAGE_PROVIDER=s3.")
        return 2
    key = f"healthcheck/probe-{uuid.uuid4().hex}.txt"
    payload = b"greenguardian storage probe"
    target = f"bucket {settings.storage_s3_bucket!r}" + (
        f" at {settings.storage_s3_endpoint_url}" if settings.storage_s3_endpoint_url else " (AWS)"
    )
    store = None
    step = "connect"
    try:
        store = build_store(settings)
        for step, action in (
            ("put", lambda: store.put(key, payload, "text/plain")),
            ("get", lambda: _same(store.get(key), payload)),
            ("delete", lambda: store.delete(key)),
        ):
            action()
            print(f"  {step}: ok")
        if store.exists(key):
            step = "delete"
            raise StorageError("object still present after delete")
    except StorageError as exc:
        print(f"FAILED at step '{step}' on {target}: {exc}")
        if store is not None and step in ("get", "delete"):
            try:
                store.delete(key)  # do not leave the probe object behind
            except StorageError:
                pass
        return 1
    print(f"OK: put, get and delete worked on {target}")
    return 0


def _same(got: bytes, expected: bytes) -> None:
    if got != expected:
        raise StorageError("the object read back differs from what was written")


def main() -> int:
    return run(get_settings())


if __name__ == "__main__":
    sys.exit(main())
