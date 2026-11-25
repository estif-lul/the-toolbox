"""Content-addressed caching: what makes "change one shot, regenerate only that shot" true.

cache_key = sha256(canonical_json({stage, stage_version, provider, model, params, seed,
                                   inputs, upstream_hashes}))

- `inputs` holds only the storyboard fields the stage actually uses (narration uses text, voice
  and style, not the image prompt), so editing an unrelated field keeps the key.
- `upstream_hashes` holds sha256 of the files consumed (a Wan job consumes its keyframe).
- Artifacts live at outputs/<stage>/<shot_id>/<key[:16]>.<ext>; old versions are kept.
- outputs/<stage>/manifest.json maps an item id to {cache_key, path, sha256, provider, model,
  created_at, status}. Writes are atomic (temp file + replace).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .env import ROOT
from .log import now_iso

OUTPUTS = ROOT / "outputs"


def canonical_json(obj: Any) -> str:
    """Sorted keys, no whitespace, UTF-8 (non-ASCII kept as-is, e.g. Amharic)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def file_sha256(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def cache_key(
    *, stage: str, stage_version: int | str, provider: str, model: str, params: dict | None = None,
    seed: int | None = None, inputs: Any = None, upstream_hashes: dict | list | None = None,
) -> str:
    payload = {
        "stage": stage,
        "stage_version": stage_version,
        "provider": provider,
        "model": model,
        "params": params or {},
        "seed": seed,
        "inputs": inputs,
        "upstream_hashes": upstream_hashes or {},
    }
    return sha256_text(canonical_json(payload))


def artifact_path(stage: str, item_id: str, key: str, ext: str) -> Path:
    return OUTPUTS / stage / item_id / f"{key[:16]}.{ext.lstrip('.')}"


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))  # UTF-8, no BOM, LF as given


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


class Manifest:
    """outputs/<stage>/manifest.json: item id -> the artifact that is current for it."""

    def __init__(self, stage: str, root: Path | None = None):
        self.stage = stage
        self.path = (root or OUTPUTS) / stage / "manifest.json"
        self.entries: dict[str, dict] = {}
        self.load()

    def load(self) -> "Manifest":
        if self.path.exists():
            self.entries = json.loads(self.path.read_text(encoding="utf-8"))
        return self

    def save(self) -> None:
        atomic_write_json(self.path, self.entries)

    def get(self, item_id: str) -> dict | None:
        return self.entries.get(item_id)

    def put(self, item_id: str, *, cache_key: str, path: Path | str, provider: str, model: str,
            status: str = "ok", **extra: Any) -> dict:
        entry = {
            "cache_key": cache_key,
            "path": rel(path),
            "sha256": file_sha256(ROOT / rel(path)) if (ROOT / rel(path)).exists() else None,
            "provider": provider,
            "model": model,
            "created_at": now_iso(),
            "status": status,
            **extra,
        }
        self.entries[item_id] = entry
        self.save()
        return entry

    def is_fresh(self, item_id: str, key: str, *, verify_hash: bool = False) -> bool:
        """A cache hit: same key, status ok, the file exists (and optionally its bytes match)."""
        entry = self.entries.get(item_id)
        if not entry or entry.get("cache_key") != key or entry.get("status") != "ok":
            return False
        path = ROOT / entry["path"]
        if not path.exists():
            return False
        if verify_hash and entry.get("sha256") and file_sha256(path) != entry["sha256"]:
            return False
        return True
