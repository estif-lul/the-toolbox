"""runs.jsonl: one JSON line per model call (plus cache-hit / fallback / retry / stale / job events).

Every line has the same keys (missing values are null) so the log is easy to query and
`pipeline/costs.py` can build COSTS.md from it. Secrets are never logged: prompts are logged by
hash (the full text is in storyboard.json), and error text passes through `env.redact`.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .env import ROOT, redact

EAT = timezone(timedelta(hours=3), "EAT")  # Africa/Addis_Ababa, no DST

EVENTS = {"model_call", "cache_hit", "fallback", "stale", "retry", "external_job"}

FIELDS = (
    "ts", "run_id", "profile", "event", "stage", "shot_id", "provider", "model", "params", "seed",
    "input_hash", "cache_key", "output", "latency_s", "gpu_s", "cost_usd", "list_price_usd",
    "attempt", "status", "error",
)


def now_iso() -> str:
    return datetime.now(EAT).isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now(EAT).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


@dataclass
class RunContext:
    run_id: str = field(default_factory=new_run_id)
    profile: str = "free"
    log_path: Path = field(default_factory=lambda: Path(os.environ.get("RUNS_LOG", ROOT / "runs.jsonl")))
    dry_run: bool = False


_current: RunContext | None = None


def start_run(profile: str = "free", *, log_path: Path | None = None, dry_run: bool = False) -> RunContext:
    global _current
    _current = RunContext(profile=profile, dry_run=dry_run)
    if log_path is not None:
        _current.log_path = Path(log_path)
    return _current


def get_run() -> RunContext:
    global _current
    if _current is None:
        _current = RunContext()
    return _current


def _rel(path: Any) -> Any:
    """Log paths relative to the repo root with forward slashes (portable across machines)."""
    if isinstance(path, Path):
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return path.as_posix()
    return path


def log_event(event: str, *, stage: str, status: str = "ok", **fields: Any) -> dict:
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}; expected one of {sorted(EVENTS)}")
    run = get_run()
    record: dict[str, Any] = {k: None for k in FIELDS}
    record.update(ts=now_iso(), run_id=run.run_id, profile=run.profile, event=event, stage=stage, status=status)
    extra = {}
    for key, value in fields.items():
        value = _rel(value)
        if key in record:
            record[key] = value
        else:
            extra[key] = value
    if isinstance(record.get("error"), str):
        record["error"] = redact(record["error"])[:800]
    if isinstance(record.get("latency_s"), float):
        record["latency_s"] = round(record["latency_s"], 3)
    if extra:
        record["extra"] = extra
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
    run.log_path.parent.mkdir(parents=True, exist_ok=True)
    # One write() of one line in append mode: lines never interleave within this process.
    with open(run.log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    return record


@dataclass
class CallRecord:
    """Filled in by the code inside `timed_call`; written to the log when the block exits."""
    output: Any = None
    cost_usd: float | None = 0.0
    gpu_s: float | None = None
    extra: dict = field(default_factory=dict)


@contextmanager
def timed_call(
    *, stage: str, provider: str, model: str, shot_id: str | None = None, params: dict | None = None,
    seed: int | None = None, input_hash: str | None = None, cache_key: str | None = None,
    attempt: int = 1, list_price_usd: float | None = None,
) -> Iterator[CallRecord]:
    """Measure one model call and write its `model_call` line, also when it fails."""
    rec = CallRecord()
    t0 = time.perf_counter()
    status, error = "ok", None
    try:
        yield rec
    except BaseException as exc:  # noqa: BLE001 - logged, then re-raised unchanged
        status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        log_event(
            "model_call", stage=stage, status=status, error=error, shot_id=shot_id, provider=provider,
            model=model, params=params, seed=seed, input_hash=input_hash, cache_key=cache_key,
            output=rec.output, latency_s=time.perf_counter() - t0, gpu_s=rec.gpu_s,
            cost_usd=rec.cost_usd, list_price_usd=list_price_usd, attempt=attempt, **rec.extra,
        )


def read_log(path: Path | None = None) -> list[dict]:
    path = Path(path) if path else get_run().log_path
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
