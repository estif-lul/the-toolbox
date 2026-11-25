"""The one way a stage calls a model: client-side pacing + retries + a log line per attempt +
the fallback chain from config/providers.yaml.

    result = invoke(chain, lambda p: p.generate(...), stage="keyframes", shot_id="s05",
                    key_fn=lambda p: cache_key(...), save=lambda p, key, r: write_png(...))

- Each attempt writes one `model_call` line (status ok/error, attempt n).
- A retryable error writes a `retry` line with the wait, then sleeps (Retry-After wins).
- When a provider is exhausted (retries used up, daily quota gone, or the model no longer
  exists), the next provider in the chain is tried and a `fallback` line records why.
- Validation errors (other 4xx) and missing keys stop immediately: a fallback would fail the same way.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .env import MissingKeyError
from .log import log_event, timed_call
from .retry import FatalError, ProviderError, QuotaExhaustedError, RetryableError, backoff_delay, classify


class AllProvidersFailed(RuntimeError):
    def __init__(self, stage: str, shot_id: str | None, errors: list[tuple[str, ProviderError]]):
        self.errors = errors
        lines = "\n".join(f"  - {name}: {err}" for name, err in errors)
        super().__init__(f"{stage}{'/' + shot_id if shot_id else ''}: every provider failed:\n{lines}")


@dataclass
class Invoked:
    value: Any
    provider: Any
    cache_key: str | None
    output: Path | None
    attempts: int
    fell_back: bool


_pace_lock = threading.Lock()
_last_call: dict[str, float] = {}


def _pace(provider: Any) -> None:
    """Honour `min_interval_s` from the provider's config (free-tier RPM limits)."""
    interval = float(getattr(provider, "min_interval_s", 0) or 0)
    if interval <= 0:
        return
    ident = f"{provider.name}:{provider.model}"
    with _pace_lock:
        wait = _last_call.get(ident, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[ident] = time.monotonic()


def _should_fall_back(err: ProviderError) -> bool:
    if isinstance(err, (RetryableError, QuotaExhaustedError)):
        return True
    # A retired / renamed model: the next provider in the chain may still work.
    return isinstance(err, FatalError) and err.status == 404


def invoke(
    chain: Any, call: Callable[[Any], Any], *, stage: str, shot_id: str | None = None,
    params: dict | None = None, seed: int | None = None, input_hash: str | None = None,
    key_fn: Callable[[Any], str] | None = None,
    save: Callable[[Any, str | None, Any], Path | None] | None = None,
    max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep,
) -> Invoked:
    errors: list[tuple[str, ProviderError]] = []
    providers = list(getattr(chain, "providers", chain))
    for index, provider in enumerate(providers):
        label = f"{provider.name}:{provider.model}"
        if index > 0:
            prev_name, prev_err = errors[-1]
            log_event("fallback", stage=stage, shot_id=shot_id, provider=provider.name,
                      model=provider.model, status="ok", error=f"from {prev_name}: {prev_err}")
        key = key_fn(provider) if key_fn else None
        call_params = {**(getattr(provider, "params", {}) or {}), **(params or {})}
        for attempt in range(1, max_attempts + 1):
            _pace(provider)
            try:
                with timed_call(stage=stage, provider=provider.name, model=provider.model, shot_id=shot_id,
                                params=call_params, seed=seed, input_hash=input_hash, cache_key=key,
                                attempt=attempt) as rec:
                    value = call(provider)
                    out = save(provider, key, value) if save else None
                    rec.output = out
                    meta = getattr(value, "meta", None)
                    if isinstance(meta, dict) and meta.get("usage"):
                        rec.extra["usage"] = meta["usage"]
                return Invoked(value, provider, key, out, attempt, index > 0)
            except MissingKeyError:
                raise
            except Exception as exc:  # noqa: BLE001
                err = classify(exc)
                if isinstance(err, RetryableError) and attempt < max_attempts:
                    delay = backoff_delay(attempt, retry_after=err.retry_after)
                    log_event("retry", stage=stage, shot_id=shot_id, provider=provider.name,
                              model=provider.model, attempt=attempt, status="waiting",
                              error=str(err), wait_s=round(delay, 2))
                    sleep(delay)
                    continue
                errors.append((label, err))
                if not _should_fall_back(err):
                    raise AllProvidersFailed(stage, shot_id, errors) from exc
                break
    raise AllProvidersFailed(stage, shot_id, errors)
