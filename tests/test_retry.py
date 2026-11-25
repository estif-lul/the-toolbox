import json

import httpx
import pytest

from pipeline.common import retry
from pipeline.common.invoke import AllProvidersFailed, invoke
from pipeline.common.retry import FatalError, QuotaExhaustedError, RetryableError, classify


def http_error(status, body="", headers=None):
    req = httpx.Request("POST", "https://example.invalid/run")
    resp = httpx.Response(status, text=body, headers=headers or {}, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)


@pytest.mark.parametrize("value,expected", [("12", 12.0), ("37s", 37.0), ("1.5s", 1.5), (3, 3.0),
                                            (None, None), ("soon", None)])
def test_parse_retry_after(value, expected):
    assert retry.parse_retry_after(value) == expected


def test_classification():
    e = classify(http_error(429, "slow down", {"retry-after": "7"}))
    assert isinstance(e, RetryableError) and e.retry_after == 7.0
    assert isinstance(classify(http_error(503)), RetryableError)
    assert isinstance(classify(http_error(429, "Quota exceeded for metric ...PerDay")), QuotaExhaustedError)
    assert isinstance(classify(http_error(400, "bad prompt")), FatalError)
    assert isinstance(classify(httpx.ConnectTimeout("t")), RetryableError)
    assert isinstance(classify(json.JSONDecodeError("x", "", 0)), FatalError)


def test_genai_errors_are_classified():
    from google.genai import errors

    details = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "rate",
                         "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}}
    e = classify(errors.ClientError(429, details))
    assert isinstance(e, RetryableError) and e.retry_after == 21.0
    assert isinstance(classify(errors.ServerError(503, {"error": {"code": 503, "message": "high demand"}})),
                      RetryableError)
    assert isinstance(classify(errors.ClientError(404, {"error": {"code": 404, "message": "not found"}})),
                      FatalError)


def test_backoff_respects_retry_after_and_grows():
    assert 5.0 <= retry.backoff_delay(1, retry_after=5) <= 6.0
    d1 = retry.backoff_delay(1, jitter=0)
    d2 = retry.backoff_delay(2, jitter=0)
    assert d1 == 2.0 and d2 == 4.0


def test_retry_call_retries_then_succeeds():
    calls = []

    def fn(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise http_error(503)
        return "ok"

    assert retry.retry_call(fn, sleep=lambda s: None) == "ok" and calls == [1, 2, 3]


def test_retry_call_fails_fast_on_fatal():
    calls = []

    def fn(attempt):
        calls.append(attempt)
        raise http_error(400)

    with pytest.raises(FatalError):
        retry.retry_call(fn, sleep=lambda s: None)
    assert calls == [1]


class Fake:
    def __init__(self, name, behaviour):
        self.name, self.model, self.params, self.behaviour, self.calls = name, f"{name}-model", {}, behaviour, 0

    def go(self):
        self.calls += 1
        return self.behaviour(self.calls)


def _events(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_invoke_retries_then_falls_back_and_logs_everything(run_log):
    def always_503(n):
        raise http_error(503)

    primary = Fake("primary", always_503)
    backup = Fake("backup", lambda n: "result")
    r = invoke([primary, backup], lambda p: p.go(), stage="text", shot_id="s01", sleep=lambda s: None)
    assert r.value == "result" and r.fell_back and primary.calls == 3 and backup.calls == 1
    kinds = [(e["event"], e["provider"], e["status"]) for e in _events(run_log)]
    assert kinds == [
        ("model_call", "primary", "error"), ("retry", "primary", "waiting"),
        ("model_call", "primary", "error"), ("retry", "primary", "waiting"),
        ("model_call", "primary", "error"),
        ("fallback", "backup", "ok"),
        ("model_call", "backup", "ok"),
    ]


def test_invoke_daily_quota_skips_retries(run_log):
    primary = Fake("primary", lambda n: (_ for _ in ()).throw(http_error(429, "limit PerDay reached")))
    backup = Fake("backup", lambda n: "ok")
    r = invoke([primary, backup], lambda p: p.go(), stage="image", sleep=lambda s: None)
    assert r.value == "ok" and primary.calls == 1


def test_invoke_validation_error_does_not_fall_back(run_log):
    primary = Fake("primary", lambda n: (_ for _ in ()).throw(http_error(400, "bad request")))
    backup = Fake("backup", lambda n: "ok")
    with pytest.raises(AllProvidersFailed):
        invoke([primary, backup], lambda p: p.go(), stage="image", sleep=lambda s: None)
    assert backup.calls == 0
