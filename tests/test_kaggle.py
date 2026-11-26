"""Step 4 without Kaggle: which Wan / ACE-Step jobs are built, their cache keys, what a push stages,
how the CLI's status text is read, and how finished outputs are ingested (once)."""

import json

import pytest

from pipeline import music, shots
from pipeline.common import cache
from pipeline.common.cache import Manifest
from pipeline.providers import kaggle_common as kc
from pipeline.providers.base import MediaJob, VideoResult
from pipeline.providers.kaggle_wan import KaggleWan

from test_schema import minimal_storyboard

PARAMS = {"width": 704, "height": 704, "frames": 81, "steps": 30, "guidance": 5.0, "time_budget_s": 100}


@pytest.fixture
def outputs(tmp_path, monkeypatch, run_log):
    monkeypatch.setattr(cache, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(kc, "STAGING", tmp_path / "outputs" / ".kaggle_staging")
    monkeypatch.setattr(kc, "username", lambda: "someone")
    return tmp_path / "outputs"


@pytest.fixture
def keyframes_chosen(tmp_path, monkeypatch):
    """Every shot has a chosen keyframe (a distinct small file per item)."""
    files = {}

    def fake_chosen(stage, item, choice, manifest=None):
        if item not in files:
            files[item] = tmp_path / f"{item}.jpg"
            files[item].write_bytes(item.encode() * 10)
        return files[item]

    monkeypatch.setattr(shots, "chosen", fake_chosen)
    return files


def sb_with_layers():
    sb = minimal_storyboard(4)
    sb["shots"][1]["motion"] = "kenburns"
    sb["shots"][3]["layers"] = [
        {"id": "a", "image_prompt": "son", "characters": [], "seed": 2101, "keyframe_choice": 0,
         "motion_prompt": "the son nods"},
        {"id": "b", "image_prompt": "dad", "characters": [], "seed": 2102, "keyframe_choice": 0,
         "motion_prompt": None},
    ]
    sb["shots"][3]["priority"] = 0
    return sb


def test_wan_jobs_order_prompts_and_layers(outputs, keyframes_chosen):
    jobs, waiting = shots.wan_jobs(sb_with_layers(), "wan-5b", PARAMS)
    assert waiting == []
    assert [j["item"] for j in jobs] == ["s04a", "s04b", "s01", "s03"]          # priority order, s02 is Ken Burns
    assert jobs[0]["prompt"].startswith("the son nods. Hand-painted")
    assert jobs[1]["prompt"].startswith("he nods slowly, camera static. ")      # a layer without one: the shot's
    assert jobs[0]["negative_prompt"].startswith("text, flicker")              # style negative + motion artifacts
    assert jobs[0]["params"] == {"width": 704, "height": 704, "frames": 81, "steps": 30, "guidance": 5.0, "fps": 24}
    assert all(j["job_id"] == j["cache_key"][:16] for j in jobs)


def test_wan_key_follows_keyframe_and_motion_only(outputs, keyframes_chosen):
    sb = sb_with_layers()
    before = {j["item"]: j["cache_key"] for j in shots.wan_jobs(sb, "wan-5b", PARAMS)[0]}
    sb["shots"][0]["narration"][0]["text"] = "a different line"                 # not a Wan input
    sb["shots"][2]["motion_prompt"] = "the camera pulls back"
    keyframes_chosen["s01"].write_bytes(b"a new keyframe")
    after = {j["item"]: j["cache_key"] for j in shots.wan_jobs(sb, "wan-5b", PARAMS)[0]}
    assert {k for k in before if before[k] != after[k]} == {"s01", "s03"}


def test_wan_waits_for_a_keyframe(outputs, monkeypatch):
    monkeypatch.setattr(shots, "chosen", lambda *a, **k: None)
    jobs, waiting = shots.wan_jobs(minimal_storyboard(2), "wan-5b", PARAMS)
    assert jobs == [] and waiting == ["s01", "s02"]


def test_push_stages_jobs_and_images(outputs, keyframes_chosen):
    jobs, _ = shots.wan_jobs(sb_with_layers(), "wan-5b", PARAMS)
    wan = KaggleWan("wan-5b", **PARAMS)
    handle = wan.submit(shots._media_jobs(jobs[:2]), {"time_budget_s": 100}, dry_run=True)
    staged = kc.STAGING / "wan" / "dataset"
    payload = json.loads((staged / "jobs.json").read_text(encoding="utf-8"))
    assert payload["model"] == "wan-5b" and payload["time_budget_s"] == 100
    assert [r["item"] for r in payload["jobs"]] == ["s04a", "s04b"]
    assert all((staged / r["image"]).exists() and r["image"] == r["job_id"] + ".jpg" for r in payload["jobs"])
    meta = json.loads((staged / "dataset-metadata.json").read_text(encoding="utf-8"))
    assert meta["id"] == "someone/toolbox-wan-jobs"
    assert handle.jobs_sha == cache.file_sha256(staged / "jobs.json") and handle.meta["dry_run"]


def test_kernel_script_gets_the_job_hash(outputs, tmp_path, monkeypatch):
    script = tmp_path / "job.py"
    script.write_text('EXPECTED_JOBS_SHA = ""\nprint(1)\n', encoding="utf-8")
    monkeypatch.setattr(kc, "run_cli", lambda args, **kw: type("P", (), {"stdout": "Kernel version 3 pushed"})())
    out = kc.push_kernel("wan", script, "abc123")
    d = kc.STAGING / "wan" / "kernel"
    assert 'EXPECTED_JOBS_SHA = "abc123"' in (d / "job.py").read_text(encoding="utf-8")
    meta = json.loads((d / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert meta["is_private"] and meta["enable_gpu"] and meta["enable_internet"]
    assert meta["dataset_sources"] == ["someone/toolbox-wan-jobs"] and meta["kernel_type"] == "script"
    assert "version 3" in out


def test_real_kernels_have_the_hash_line():
    for path in (kc.KERNELS / "wan_kernel" / "wan_job.py", kc.KERNELS / "acestep_kernel" / "acestep_job.py"):
        assert 'EXPECTED_JOBS_SHA = ""' in path.read_text(encoding="utf-8")
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


@pytest.mark.parametrize("text,expected", [
    ('someone/toolbox-wan has status "complete"', "complete"),
    ("someone/toolbox-wan has status \"KernelWorkerStatus.RUNNING\"", "running"),
    ('has status "queued"', "queued"),
    ('has status "error"', "error"),
    ('has status "cancelAcknowledged"', "cancel"),
])
def test_parse_status(text, expected):
    assert kc.parse_status(text) == expected


def test_read_results_last_row_wins_and_torn_line(tmp_path):
    (tmp_path / "results.jsonl").write_text(
        '{"job_id": "a", "ok": false}\n{"job_id": "b", "ok": true}\n{"job_id": "a", "ok": true}\n{"job_id": "c", "ok', encoding="utf-8")
    rows = {r["job_id"]: r for r in kc.read_results(tmp_path)}
    assert set(rows) == {"a", "b"} and rows["a"]["ok"] is True


def _results(tmp_path, jobs, ok=True, used=None):
    out = []
    for j in jobs:
        f = tmp_path / f"{j['job_id']}.mp4"
        f.write_bytes(b"video " + j["item"].encode())
        row = {"job_id": j["job_id"], "ok": ok, "file": f.name, "seconds": 600.0, "gpu_name": "Tesla T4",
               "params": used or {"width": 704, "height": 704, "frames": 81}}
        out.append(VideoResult(j["job_id"], ok, f if ok else None, 600.0, row, None if ok else "OOM"))
    return out


def test_ingest_copies_logs_and_skips_a_second_pull(outputs, keyframes_chosen, tmp_path, run_log):
    jobs, _ = shots.wan_jobs(sb_with_layers(), "wan-5b", PARAMS)
    handle = {"jobs_sha": "f" * 64, "jobs": jobs[:2]}
    manifest = Manifest("shots")
    res = shots.ingest(_results(tmp_path, jobs[:2]), handle, manifest, stage="shots", provider="kaggle_wan",
                       model="wan-5b")
    assert res["ingested"] == ["s04a", "s04b"] and res["failed"] == []
    entry = manifest.get("s04a")
    assert entry["path"].endswith(f"{jobs[0]['cache_key'][:16]}.mp4") and entry["degraded"] is False
    assert (cache.OUTPUTS / "shots" / "s04a" / f"{jobs[0]['cache_key'][:16]}.mp4").exists() or entry["sha256"]
    assert shots.stale_jobs(jobs, manifest) == jobs[2:]
    calls = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines()]
    assert [c["shot_id"] for c in calls if c["event"] == "model_call"] == ["s04a", "s04b"]
    assert all(c["gpu_s"] == 600.0 for c in calls if c["event"] == "model_call")
    again = shots.ingest(_results(tmp_path, jobs[:2]), handle, manifest, stage="shots", provider="kaggle_wan",
                         model="wan-5b")
    assert again["ingested"] == []
    assert len([line for line in run_log.read_text(encoding="utf-8").splitlines() if '"model_call"' in line]) == 2


def test_ingest_marks_fallback_params_and_failures(outputs, keyframes_chosen, tmp_path):
    jobs, _ = shots.wan_jobs(sb_with_layers(), "wan-5b", PARAMS)
    handle = {"jobs_sha": "f" * 64, "jobs": jobs}
    manifest = Manifest("shots")
    small = _results(tmp_path, jobs[:1], used={"width": 576, "height": 576, "frames": 49})
    failed = _results(tmp_path, jobs[1:2], ok=False)
    stray = [VideoResult("not-a-job", True, None, 1.0, {}, None)]
    res = shots.ingest(small + failed + stray, handle, manifest, stage="shots", provider="kaggle_wan", model="wan-5b")
    assert manifest.get(jobs[0]["item"])["degraded"] is True
    assert res["failed"] == [f"{jobs[1]['item']}: OOM"] and res["unknown"] == ["not-a-job"]
    assert manifest.get(jobs[1]["item"]) is None


def test_payload_without_images():
    from pipeline.providers.kaggle_acestep import KaggleAceStep

    ace = KaggleAceStep("ace", steps=8)
    payload, files = ace.payload([MediaJob("j1", "main_c1", "caption", 301, {"bpm": 80})], {"repo": "r"})
    assert files == {} and payload["repo"] == "r"
    assert payload["jobs"] == [{"job_id": "j1", "item": "main_c1", "prompt": "caption", "seed": 301, "bpm": 80}]


def test_ace_jobs_one_per_seed():
    sb = minimal_storyboard(2)
    sb["music"]["cues"][0].update(caption="gentle guitar", bpm=80, key="D major", seeds=[301, 302, 303])
    jobs = music.ace_jobs(sb, 75.7, "ace", {"steps": 8})
    assert [j["item"] for j in jobs] == ["main_c1", "main_c2", "main_c3"]
    assert [j["seed"] for j in jobs] == [301, 302, 303]
    assert jobs[0]["params"]["duration_s"] == 80.0 and jobs[0]["params"]["keyscale"] == "D Major"
    assert len({j["cache_key"] for j in jobs}) == 3
    assert music.ace_jobs(sb, 75.7, "ace", {"steps": 8})[0]["cache_key"] == jobs[0]["cache_key"]
    sb["music"]["cues"][0]["caption"] = "something else"
    assert music.ace_jobs(sb, 75.7, "ace", {"steps": 8})[0]["cache_key"] != jobs[0]["cache_key"]


def test_keyscale_spelling():
    assert music.keyscale("D major") == "D Major"
    assert music.keyscale("f# minor") == "F# Minor"
    assert music.keyscale("") == ""


def test_a_forced_redo_from_a_new_run_replaces_the_clip(outputs, keyframes_chosen, tmp_path):
    jobs, _ = shots.wan_jobs(sb_with_layers(), "wan-5b", PARAMS)
    manifest = Manifest("shots")
    small = _results(tmp_path, jobs[:1], used={"width": 576, "height": 576, "frames": 49})
    shots.ingest(small, {"jobs_sha": "a" * 64, "jobs": jobs[:1]}, manifest, stage="shots", provider="p", model="m")
    assert manifest.get(jobs[0]["item"])["degraded"] is True
    full = _results(tmp_path, jobs[:1])
    res = shots.ingest(full, {"jobs_sha": "b" * 64, "jobs": jobs[:1]}, manifest, stage="shots", provider="p", model="m")
    assert res["ingested"] == [jobs[0]["item"]] and manifest.get(jobs[0]["item"])["degraded"] is False
