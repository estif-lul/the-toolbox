"""Smoke test: one minimal call per provider, with neutral test prompts, each logged to runs.jsonl.

    make smoke            # all checks
    make smoke ONLY=tts   # one check (text, text_fallback, tts, tts_fallback, flux1, flux2, flux2_repeat,
                          #            flux2_ref, kenburns, kaggle)

Also `python -m pipeline.run models`: list the models the keys can see (to verify model ids
against the brief), written to outputs/smoke/models_*.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import httpx

from .common import env, ffmpeg
from .common.cache import OUTPUTS, atomic_write_bytes, atomic_write_json, rel
from .common.invoke import AllProvidersFailed, invoke
from .common.log import get_run, log_event
from .providers import registry
from .providers.cloudflare_image import CloudflareImage

SMOKE = OUTPUTS / "smoke"
TEXT_PROMPT = 'This is a connectivity test. Reply with the JSON object {"ok": true} and nothing else.'
TEXT_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
TTS_TEXT = "Testing one two three."
IMAGE_PROMPT = "a red apple on a wooden table, soft daylight, simple background"
REF_PROMPT = "the same red apple from the reference image, now on a blue ceramic plate"
SEED = 42


@dataclass
class Row:
    check: str
    provider: str
    model: str
    ok: bool
    latency_s: float | None
    notes: str


def _ext(mime: str) -> str:
    return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")


def _one(provider) -> list:
    return [provider]


def check_text(chain_index: int, profile: str) -> Row:
    p = registry.get_provider("text", profile).providers[chain_index]
    out = SMOKE / f"text_{chain_index}.json"
    r = invoke(_one(p), lambda prov: prov.generate_json(TEXT_PROMPT, TEXT_SCHEMA), stage="smoke",
               shot_id=f"text{'_fallback' if chain_index else ''}", max_attempts=2,
               save=lambda prov, key, res: (atomic_write_json(out, res.data), out)[1])
    usage = r.value.meta.get("usage") or {}
    ok = r.value.data.get("ok") is True
    return Row(f"text{' (fallback)' if chain_index else ''}", p.name, p.model, ok, _last_latency(),
               f"returned {json.dumps(r.value.data)}; tokens in/out {usage.get('prompt_tokens')}/{usage.get('output_tokens')}")


def check_tts(chain_index: int, profile: str) -> Row:
    p = registry.get_provider("tts", profile).providers[chain_index]
    p.min_interval_s = 0  # a single call; no pacing needed
    out = SMOKE / f"tts_{chain_index}.wav"
    r = invoke(_one(p), lambda prov: prov.synthesize(TTS_TEXT, "Kore", "calm and clear"), stage="smoke",
               shot_id=f"tts{'_fallback' if chain_index else ''}", max_attempts=2,
               params={"voice": "Kore", "style": "calm and clear"},
               save=lambda prov, key, res: (atomic_write_bytes(out, res.wav_bytes), out)[1])
    probed = ffmpeg.probe(out)
    a = probed.get("audio", {})
    words = len(TTS_TEXT.split())
    return Row(f"tts{' (fallback)' if chain_index else ''}", p.name, p.model, True, _last_latency(),
               f"{r.value.duration_s:.2f}s WAV, {a.get('rate')} Hz, {a.get('channels')} ch, "
               f"{8 * r.value.meta.get('sample_width', 2)}-bit; ffprobe {probed['duration']:.2f}s; "
               f"{words / max(r.value.duration_s, 0.01):.2f} words/s")


def _image_provider(model_contains: str, profile: str) -> CloudflareImage:
    for p in registry.get_provider("image", profile):
        if model_contains in p.model:
            return p
    raise KeyError(f"no image provider with {model_contains!r} in profile {profile!r}")


def check_image(model_contains: str, label: str, profile: str, refs: list[Path] | None = None,
                prompt: str = IMAGE_PROMPT) -> Row:
    p = _image_provider(model_contains, profile)
    stem = label.replace(" ", "_").replace("(", "").replace(")", "")

    def save(prov, key, res):
        out = SMOKE / f"{stem}.{_ext(res.mime)}"
        atomic_write_bytes(out, res.data)
        return out

    seed = SEED if (p.send_seed or p.multipart) else None  # schnell takes no seed (F06)
    r = invoke(_one(p), lambda prov: prov.generate(prompt, SEED, 1024, 1024, refs=refs or ()), stage="smoke",
               shot_id=stem, seed=seed, max_attempts=2, save=save,
               params={"w": 1024, "h": 1024, "steps": p.params.get("steps"), "refs": len(refs or [])})
    v = r.value
    note = f"{v.width}x{v.height} {v.mime}, {len(v.data) // 1024} KB, steps {v.meta.get('steps')}"
    if seed is None:
        note += ", no seed (not reproducible)"
    if refs:
        note += f"; reference input accepted ({', '.join(v.meta.get('refs', []))}), check the picture"
    if label == "flux2_repeat":
        first = sorted(SMOKE.glob("flux2.*"))
        if first:
            same = first[0].read_bytes() == v.data
            note += f"; same seed+prompt as flux2 -> {'IDENTICAL bytes' if same else 'DIFFERENT bytes'}"
    return Row(label, p.name, p.model, True, _last_latency(), f"{note} -> {rel(r.output)}")


def _ref_image() -> list[Path] | None:
    found = sorted(SMOKE.glob("flux2.*")) or sorted(SMOKE.glob("flux1.*"))
    return found[:1] or None


def check_kenburns(profile: str) -> Row:
    p = registry.get_provider("kenburns", profile).primary
    stills = sorted(SMOKE.glob("flux2.*")) or sorted(SMOKE.glob("flux1.*"))
    if not stills:
        from PIL import Image, ImageDraw

        still = SMOKE / "kenburns_test_card.png"
        SMOKE.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (1024, 1024), (214, 160, 92))
        ImageDraw.Draw(im).ellipse((312, 312, 712, 712), fill=(180, 40, 40))
        im.save(still)
        stills = [still]
    out = SMOKE / "kenburns.mp4"
    r = invoke(_one(p), lambda prov: prov.render(stills[0], out, duration_s=2.0, move="push_in", amount=0.08),
               stage="smoke", shot_id="kenburns", max_attempts=1,
               params={"move": "push_in", "amount": 0.08, "duration_s": 2.0},
               save=lambda prov, key, res: res.path)
    info = ffmpeg.probe(out)
    v = info.get("video", {})
    return Row("kenburns", p.name, p.model, True, _last_latency(),
               f"{v.get('w')}x{v.get('h')} @ {v.get('fps')} fps, {info['duration']:.2f}s from {stills[0].name}")


def _kaggle_cli() -> str | None:
    exe_dir = Path(sys.executable).parent
    for name in ("kaggle.exe", "kaggle"):
        if (exe_dir / name).exists():
            return str(exe_dir / name)
    return shutil.which("kaggle")


def check_kaggle(profile: str) -> Row:
    cli = _kaggle_cli()
    if not cli:
        raise RuntimeError("kaggle CLI not found; run `make setup`")
    if not env.kaggle_auth_available():
        raise env.MissingKeyError(f"Kaggle credentials not found. Get them from: {env.WHERE['KAGGLE_API_TOKEN']}")
    t0 = time.perf_counter()
    proc = subprocess.run([cli, "kernels", "list", "--mine", "--page-size", "5"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)
    latency = time.perf_counter() - t0
    ok = proc.returncode == 0
    detail = (proc.stdout if ok else (proc.stderr or proc.stdout)).strip()
    log_event("external_job", stage="smoke", shot_id="kaggle", provider="kaggle", model="kaggle-cli",
              params={"cmd": "kernels list --mine"}, latency_s=latency, status="ok" if ok else "error",
              error=None if ok else env.redact(detail[-400:]))
    n = max(len([l for l in detail.splitlines() if l.strip()]) - 2, 0) if ok else 0
    note = (f"auth ok; {n} kernel(s) listed (no GPU used)" if ok else env.redact(detail.splitlines()[-1] if detail else "failed"))
    if ok:
        quota = kaggle_quota(cli)
        if quota:
            atomic_write_json(SMOKE / "kaggle_quota.json", quota)
            note += "; " + "; ".join(f"{r['resource']} {r['remaining']} of {r['total']} left (refresh {r['refreshAt'][:10]})"
                                     for r in quota)
    return Row("kaggle auth", "kaggle", "kaggle-cli " + _kaggle_version(cli), ok, latency, note)


def kaggle_quota(cli: str) -> list[dict]:
    """`kaggle quota`: weekly GPU/TPU hours (the $ figures in Settings are the Model Proxy, not GPU)."""
    try:
        out = subprocess.run([cli, "quota"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60).stdout
    except Exception:  # noqa: BLE001
        return []
    lines = [l.split() for l in out.splitlines() if l.strip() and not l.startswith("-")]
    if not lines or lines[0][:2] != ["resource", "used"]:
        return []
    header = lines[0]
    return [dict(zip(header, row)) for row in lines[1:] if len(row) == len(header)]


def _kaggle_version(cli: str) -> str:
    try:
        return subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30).stdout.strip().split()[-1]
    except Exception:  # noqa: BLE001
        return "?"


def _last_latency() -> float | None:
    """Latency of the last model_call line written by this run (what runs.jsonl recorded)."""
    run = get_run()
    try:
        with open(run.log_path, encoding="utf-8") as fh:
            for line in reversed(fh.readlines()):
                rec = json.loads(line)
                if rec.get("run_id") == run.run_id and rec.get("event") == "model_call":
                    return rec.get("latency_s")
    except FileNotFoundError:
        pass
    return None


CHECKS: dict[str, Callable[[str], Row]] = {
    "text": lambda prof: check_text(0, prof),
    "text_fallback": lambda prof: check_text(1, prof),
    "tts": lambda prof: check_tts(0, prof),
    "tts_fallback": lambda prof: check_tts(1, prof),
    "flux1": lambda prof: check_image("flux-1-schnell", "flux1", prof),
    "flux2": lambda prof: check_image("flux-2", "flux2", prof),
    "flux2_repeat": lambda prof: check_image("flux-2", "flux2_repeat", prof),
    "flux2_ref": lambda prof: check_image("flux-2", "flux2_ref", prof, refs=_ref_image(), prompt=REF_PROMPT),
    "kenburns": check_kenburns,
    "kaggle": check_kaggle,
}


def run_smoke(profile: str, only: list[str] | None = None) -> list[Row]:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    SMOKE.mkdir(parents=True, exist_ok=True)
    rows: list[Row] = []
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        if name == "flux2_ref" and not _ref_image():
            rows.append(Row(name, "cloudflare_image", "flux-2", False, None, "skipped: needs a flux image first"))
            continue
        console.print(f"[dim]smoke: {name}...[/dim]")
        try:
            rows.append(fn(profile))
        except env.MissingKeyError as exc:
            rows.append(Row(name, "-", "-", False, None, f"missing key: {str(exc).splitlines()[0]}"))
        except AllProvidersFailed as exc:
            err = exc.errors[-1][1] if exc.errors else exc
            rows.append(Row(name, exc.errors[-1][0] if exc.errors else "-", "", False, _last_latency(),
                            env.redact(str(err))[:240]))
        except Exception as exc:  # noqa: BLE001 - the table must always print
            rows.append(Row(name, "-", "-", False, None, env.redact(f"{type(exc).__name__}: {exc}")[:240]))

    table = Table(title=f"Smoke test  run_id={get_run().run_id}  profile={profile}")
    for col in ("check", "provider", "model", "ok", "latency_s", "notes"):
        table.add_column(col, overflow="fold")
    for r in rows:
        table.add_row(r.check, r.provider, r.model, "[green]ok[/green]" if r.ok else "[red]FAIL[/red]",
                      f"{r.latency_s:.2f}" if r.latency_s is not None else "-", r.notes)
    console.print(table)
    atomic_write_json(SMOKE / "summary.json", {"run_id": get_run().run_id, "profile": profile,
                                               "rows": [asdict(r) for r in rows]})
    return rows


# ---------------------------------------------------------------------------------------------
# Model listing (verifies the brief's model names against what the keys can actually see)

def list_models(profile: str) -> dict:
    from rich.console import Console

    console = Console()
    SMOKE.mkdir(parents=True, exist_ok=True)
    found: dict = {}

    try:
        from google import genai

        client = genai.Client(api_key=env.require("GEMINI_API_KEY", why="model listing"))
        gem = [{"name": m.name, "display_name": m.display_name, "actions": list(m.supported_actions or [])}
               for m in client.models.list(config={"page_size": 200})]
        atomic_write_json(SMOKE / "models_gemini.json", gem)
        found["gemini"] = gem
        console.print(f"Gemini: {len(gem)} models listed -> outputs/smoke/models_gemini.json")
        for stage in ("text", "tts"):
            for p in registry.get_provider(stage, profile):
                listed = any(m["name"] == f"models/{p.model}" for m in gem)
                console.print(f"  {stage:5} {p.model:32} listed={listed}")
    except env.MissingKeyError as exc:
        console.print(f"[yellow]Gemini skipped:[/yellow] {exc}")

    try:
        account = env.require("CLOUDFLARE_ACCOUNT_ID", why="model listing")
        token = env.require("CLOUDFLARE_API_TOKEN", why="model listing")
        resp = httpx.get(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/models/search",
                         params={"task": "Text-to-Image", "per_page": 100},
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if resp.status_code != 200:
            console.print(f"[red]Cloudflare listing failed:[/red] HTTP {resp.status_code} {env.redact(resp.text)[:300]}")
        else:
            cf = [{"name": m["name"], "description": m.get("description", "")[:160],
                   "properties": {p["property_id"]: p["value"] for p in m.get("properties", [])}}
                  for m in resp.json().get("result", [])]
            atomic_write_json(SMOKE / "models_cloudflare.json", cf)
            found["cloudflare"] = cf
            console.print(f"Cloudflare: {len(cf)} text-to-image models -> outputs/smoke/models_cloudflare.json")
            for m in cf:
                console.print(f"  {m['name']}")
    except env.MissingKeyError as exc:
        console.print(f"[yellow]Cloudflare skipped:[/yellow] {exc}")
    return found
