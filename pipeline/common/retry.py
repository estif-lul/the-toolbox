"""Retries with exponential backoff, jitter and Retry-After.

Errors are classified first:
- `RetryableError`: 429 (per-minute limits), 5xx, timeouts, connection errors. Retried.
- `QuotaExhaustedError`: a 429 for a *daily* quota. Retrying today is pointless, so it is not
  retried; the caller moves straight to the fallback provider.
- `FatalError`: 4xx validation / auth errors, bad responses. Fail fast.
"""

from __future__ import annotations

import functools
import json
import random
import re
import time
from typing import Any, Callable, TypeVar

import httpx

T = TypeVar("T")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class RetryableError(ProviderError):
    pass


class QuotaExhaustedError(ProviderError):
    pass


class FatalError(ProviderError):
    pass


_DURATION_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*s\s*$")


def parse_retry_after(value: Any) -> float | None:
    """Accepts a Retry-After header ("12"), a protobuf duration ("37s", "1.5s") or a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    m = _DURATION_RE.match(text)
    if m:
        return float(m.group(1))
    try:
        return float(text)
    except ValueError:
        return None


def _google_retry_delay(details: Any) -> float | None:
    """Gemini puts RetryInfo.retryDelay inside error.details[]."""
    try:
        for d in (details or {}).get("error", {}).get("details", []):
            if "retryDelay" in d:
                return parse_retry_after(d["retryDelay"])
    except AttributeError:
        pass
    return None


def _looks_daily(text: str) -> bool:
    t = text.lower()
    return "perday" in t or "per day" in t or "daily" in t or "requests_per_day" in t


def classify(exc: BaseException) -> ProviderError:
    """Map any exception from a provider SDK or HTTP client onto our three error classes."""
    if isinstance(exc, ProviderError):
        return exc
    # httpx transport problems
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return RetryableError(f"{type(exc).__name__}: {exc}")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = exc.response.text[:500]
        ra = parse_retry_after(exc.response.headers.get("retry-after"))
        if status == 429 and _looks_daily(body):
            return QuotaExhaustedError(f"HTTP 429 daily quota: {body}", status=status, retry_after=ra)
        if status in RETRYABLE_STATUS:
            return RetryableError(f"HTTP {status}: {body}", status=status, retry_after=ra)
        return FatalError(f"HTTP {status}: {body}", status=status)
    # google-genai
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover
        genai_errors = None
    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        status = exc.code
        text = str(exc)
        ra = _google_retry_delay(exc.details)
        if status == 429 and _looks_daily(text):
            return QuotaExhaustedError(text, status=status, retry_after=ra)
        if status in RETRYABLE_STATUS:
            return RetryableError(text, status=status, retry_after=ra)
        return FatalError(text, status=status)
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return RetryableError(f"{type(exc).__name__}: {exc}")
    if isinstance(exc, (json.JSONDecodeError, KeyError, ValueError)):
        return FatalError(f"bad response: {type(exc).__name__}: {exc}")
    return FatalError(f"{type(exc).__name__}: {exc}")


def backoff_delay(attempt: int, *, base: float = 2.0, factor: float = 2.0, jitter: float = 0.25,
                  max_wait: float = 90.0, retry_after: float | None = None) -> float:
    """Delay before attempt `attempt + 1`. Retry-After, when given, wins (it is the server's ask)."""
    if retry_after is not None:
        return min(max(retry_after, 0.0) + random.uniform(0, 1.0), max_wait)
    delay = base * (factor ** (attempt - 1))
    return min(delay * (1 + random.uniform(-jitter, jitter)), max_wait)


def retry_call(
    fn: Callable[[int], T], *, max_attempts: int = 3, base: float = 2.0, factor: float = 2.0,
    jitter: float = 0.25, max_wait: float = 90.0,
    on_retry: Callable[[int, ProviderError, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn(attempt) until it succeeds, a non-retryable error occurs, or attempts run out."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(attempt)
        except Exception as exc:  # noqa: BLE001
            err = classify(exc)
            if not isinstance(err, RetryableError) or attempt == max_attempts:
                if err is exc:
                    raise
                raise err from exc
            delay = backoff_delay(attempt, base=base, factor=factor, jitter=jitter,
                                  max_wait=max_wait, retry_after=err.retry_after)
            if on_retry:
                on_retry(attempt, err, delay)
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def with_retry(max_attempts: int = 3, base: float = 2.0, factor: float = 2.0, jitter: float = 0.25,
               max_wait: float = 90.0):
    """Decorator form of `retry_call` for functions that don't need the attempt number."""
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return retry_call(lambda _attempt: fn(*args, **kwargs), max_attempts=max_attempts,
                              base=base, factor=factor, jitter=jitter, max_wait=max_wait)
        return wrapper
    return deco
