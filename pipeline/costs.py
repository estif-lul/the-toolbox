"""`make costs`: the tables in COSTS.md sections 1-3, generated from runs.jsonl.

Only `model_call` lines are calls; `cache_hit`, `retry`, `fallback` and `external_job` lines are
counted separately. The free lane costs $0. The list-price column says what the same calls would
cost on a paid plan, from config/prices.yaml; a model with no checked price shows "unknown",
never 0. Workers AI images are priced from the documented per-tile neuron rates and the number of
reference images in each call's params. GPU seconds come from the Kaggle results (one T4 per job).
The generated block sits between markers, so re-running replaces it and leaves the manual sections.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

from .common.cache import atomic_write_text
from .common.env import ROOT
from .keyframes import neurons

BEGIN, END = "<!-- costs:begin (make costs) -->", "<!-- costs:end -->"
USD_PER_NEURON = 0.011 / 1000


def load_rows(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "runs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def list_price(row: dict, prices: dict) -> float | None:
    """What one model_call would cost on the paid tier; None if the price is not known."""
    model = row.get("model") or ""
    p = (prices.get("models") or {}).get(model)
    if row.get("provider") in ("kenburns", "ffmpeg", "placeholder") or (p and p.get("unit") == "local"):
        return 0.0
    if model.startswith("@cf/") and p and p.get("neurons"):
        return round(neurons(model, int((row.get("params") or {}).get("refs") or 0)) * USD_PER_NEURON, 6)
    if p and p.get("unit") == "per_1m_tokens" and p.get("input") is not None:
        tokens = usage_tokens(row)
        if tokens is None:
            # a failed request returns no usage; such requests are counted as not billed
            return 0.0 if row.get("status") != "ok" else None
        tin, tout = tokens
        return round((tin * p["input"] + tout * p["output"]) / 1e6, 6)
    return None


def usage_tokens(row: dict) -> tuple[int, int] | None:
    """(input, output + thinking) tokens from the usage the Gemini adapters log, if any."""
    u = (row.get("extra") or {}).get("usage") or row.get("usage")
    if not u:
        return None
    if "total_input_tokens" in u:          # Interactions API (TTS)
        return int(u.get("total_input_tokens") or 0), int(u.get("total_output_tokens") or 0) + int(
            u.get("total_thought_tokens") or 0)
    return int(u.get("prompt_tokens") or 0), int(u.get("output_tokens") or 0) + int(u.get("thinking_tokens") or 0)


def summarise(rows: list[dict], prices: dict, key) -> dict[tuple, dict]:
    out: dict[tuple, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "hits": 0, "retries": 0, "fallbacks": 0,
                                                  "latency": 0.0, "gpu_s": 0.0, "cost": 0.0, "list": 0.0,
                                                  "list_unknown": 0, "jobs": 0})
    for r in rows:
        k = key(r)
        s = out[k]
        ev = r.get("event")
        if ev == "model_call":
            s["calls"] += 1
            s["errors"] += r.get("status") != "ok"
            s["latency"] += float(r.get("latency_s") or 0)
            s["gpu_s"] += float(r.get("gpu_s") or 0)
            s["cost"] += float(r.get("cost_usd") or 0)
            lp = list_price(r, prices)
            if lp is None:
                s["list_unknown"] += 1
            else:
                s["list"] += lp
        elif ev == "cache_hit":
            s["hits"] += 1
        elif ev == "retry":
            s["retries"] += 1
        elif ev == "fallback":
            s["fallbacks"] += 1
        elif ev == "external_job":
            s["jobs"] += 1
    return dict(out)


def _money(s: dict) -> str:
    if s["calls"] == 0:
        return "—"
    known = f"${s['list']:.4f}"
    if s["list_unknown"] == s["calls"]:
        return "unknown"
    return known + (f" + unknown ({s['list_unknown']} calls)" if s["list_unknown"] else "")


def table(summary: dict[tuple, dict], first_cols: list[str]) -> str:
    head = first_cols + ["calls", "errors", "cache hits", "retries", "fallbacks", "Kaggle CLI jobs",
                         "total latency", "mean latency", "GPU min", "cost (free lane)", "list-price equivalent"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for k in sorted(summary, key=lambda x: [str(v) for v in x]):
        s = summary[k]
        mean = f"{s['latency'] / s['calls']:.1f} s" if s["calls"] else "—"
        lines.append("| " + " | ".join([*(f"`{v}`" if v else "—" for v in k), str(s["calls"]), str(s["errors"]),
                                         str(s["hits"]), str(s["retries"]), str(s["fallbacks"]), str(s["jobs"]),
                                         f"{s['latency']:.0f} s", mean, f"{s['gpu_s'] / 60:.1f}",
                                         f"${s['cost']:.2f}", _money(s)]) + " |")
    return "\n".join(lines)


def build(rows: list[dict], prices: dict) -> str:
    by_stage = summarise(rows, prices, lambda r: (r.get("stage"),))
    by_model = summarise(rows, prices, lambda r: (r.get("provider"), r.get("model")))
    total = summarise(rows, prices, lambda r: ("all",))[("all",)]
    days = sorted({r["ts"][:10] for r in rows})
    runs = len({r["run_id"] for r in rows})
    return "\n".join([
        BEGIN,
        f"*Generated by `make costs` from runs.jsonl ({len(rows)} lines, {runs} runs, {days[0]} to {days[-1]}). "
        "The smoke and narration-check stages are tests, not parts of the film, but they used the same quotas.*",
        "",
        "## 1. Per stage",
        table(by_stage, ["stage"]),
        "",
        "## 2. Per model",
        table(by_model, ["provider", "model"]),
        "",
        "## 3. Whole project",
        f"- Model calls: **{total['calls']}** ({total['errors']} failed), cache hits: **{total['hits']}**, "
        f"retries: {total['retries']}, fallbacks: {total['fallbacks']}.",
        f"- Time inside model calls: **{total['latency'] / 60:.1f} min**; Kaggle GPU time: "
        f"**{total['gpu_s'] / 60:.1f} GPU-min** (T4).",
        f"- Paid by me: **${total['cost']:.2f}** (free tiers only).",
        f"- List-price equivalent of the calls with a checked price: **${total['list']:.4f}**; "
        f"{total['list_unknown']} calls have no checked price (shown as unknown, not 0): the Kaggle GPU "
        "jobs (no T4 list price recorded), models not on the pricing page, and calls whose usage was not logged.",
        "- Gemini prices are the Standard (paid) tier for 2026 from the pricing page, applied to the token "
        "usage each call logged; a failed request (no usage returned) is counted as not billed. "
        "Workers AI images use the documented neurons per tile. Prices double for the Gemini 3.8 models "
        "from 2027-01-01.",
        END,
    ])


def run_costs(path: Path | None = None) -> str:
    rows = load_rows()
    prices = yaml.safe_load((ROOT / "config" / "prices.yaml").read_text(encoding="utf-8"))
    block = build(rows, prices)
    doc_path = path or ROOT / "COSTS.md"
    doc = doc_path.read_text(encoding="utf-8")
    if BEGIN in doc:
        doc = doc[: doc.index(BEGIN)] + block + doc[doc.index(END) + len(END):]
    else:
        start = doc.index("## 1. Per stage")
        end = doc.index("---", start)
        doc = doc[:start] + block + "\n\n" + doc[end:]
    atomic_write_text(doc_path, doc)
    return block
