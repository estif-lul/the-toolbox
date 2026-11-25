import json

import pytest

from pipeline.common import env, log


def lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_event_line_is_valid_json_with_all_fields(run_log):
    log.log_event("cache_hit", stage="narration", shot_id="s05", provider="gemini_tts", model="m",
                  cache_key="abc")
    [rec] = lines(run_log)
    assert set(log.FIELDS) <= set(rec)
    assert rec["event"] == "cache_hit" and rec["shot_id"] == "s05" and rec["profile"] == "test"
    assert rec["ts"].endswith("+03:00")


def test_timed_call_logs_success_with_latency(run_log):
    with log.timed_call(stage="keyframes", provider="p", model="m", shot_id="s01", seed=7,
                        params={"steps": 4}) as rec:
        rec.output = "outputs/keyframes/s01/x.png"
    [r] = lines(run_log)
    assert r["event"] == "model_call" and r["status"] == "ok" and r["seed"] == 7
    assert isinstance(r["latency_s"], float) and r["latency_s"] >= 0
    assert r["output"] == "outputs/keyframes/s01/x.png" and r["cost_usd"] == 0.0


def test_timed_call_logs_failure_and_reraises(run_log):
    with pytest.raises(RuntimeError):
        with log.timed_call(stage="tts", provider="p", model="m", attempt=2):
            raise RuntimeError("boom")
    [r] = lines(run_log)
    assert r["status"] == "error" and "boom" in r["error"] and r["attempt"] == 2


def test_unknown_event_rejected(run_log):
    with pytest.raises(ValueError):
        log.log_event("made_up", stage="x")


def test_secrets_are_redacted_from_errors(run_log, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "FAKEKEY-1234567890-abcdef")
    log.log_event("model_call", stage="text", status="error",
                  error="401 for url ...?key=FAKEKEY-1234567890-abcdef")
    [r] = lines(run_log)
    assert "FAKEKEY" not in r["error"] and "***" in r["error"]
    assert env.redact("no secrets here") == "no secrets here"
