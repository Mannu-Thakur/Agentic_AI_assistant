"""Resolve app data directories to a writable location at startup."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger("app.core.storage_paths")


def resolve_storage_path(configured_path: str, storage_name: str) -> str:
    """Keep a configured storage path when writable; otherwise use temp storage.

    Native cloud runtimes and Docker images can have different writable roots.
    A stale Docker path such as ``/app`` should not prevent the service from
    starting its vector store or accepting document uploads.
    """
    path = Path(configured_path).expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        if path.is_dir() and os.access(path, os.W_OK | os.X_OK):
            # Check actual filesystem writes too: ACLs and read-only mounts can
            # disagree with a permission-bit-only os.access check.
            with tempfile.NamedTemporaryFile(prefix=".write-check-", dir=path):
                pass
            return str(path)
    except OSError:
        pass

    fallback = Path(tempfile.gettempdir()) / "agentic-ai-assistant" / storage_name
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".write-check-", dir=fallback):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"No writable location is available for {storage_name} storage"
        ) from exc

    logger.warning(
        "Configured %s storage path %s is not writable; using temporary path %s. "
        "Data there may be lost when the service restarts.",
        storage_name,
        path,
        fallback,
    )
    return str(fallback)
