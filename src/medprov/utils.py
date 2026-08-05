"""Small deterministic and privacy-safe utility functions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RESTRICTED_LOCAL_FIELDS


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: str | Path, value: Any) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def restricted_key_paths(value: Any, prefix: str = "") -> list[str]:
    """Return nested key paths that are unsafe for a public aggregate result."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in RESTRICTED_LOCAL_FIELDS:
                hits.append(path)
            hits.extend(restricted_key_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(restricted_key_paths(child, f"{prefix}[{index}]"))
    return hits


def assert_public_aggregate(value: Any) -> None:
    hits = restricted_key_paths(value)
    if hits:
        raise ValueError(
            "Public aggregate output contains restricted key fields: " + ", ".join(hits[:20])
        )
