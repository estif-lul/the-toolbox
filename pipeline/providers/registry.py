"""get_provider(stage, profile) -> Chain(primary, fallbacks...) built from config/providers.yaml.

Adapters are imported lazily by dotted path, so a stage that only needs FFmpeg never imports an
SDK, and the paid lane is one new file plus one config line.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..common.env import ROOT

CONFIG = ROOT / "config" / "providers.yaml"

ADAPTERS: dict[str, str] = {
    "gemini_text": "pipeline.providers.gemini_text:GeminiText",
    "gemini_tts": "pipeline.providers.gemini_tts:GeminiTTS",
    "cloudflare_image": "pipeline.providers.cloudflare_image:CloudflareImage",
    "kenburns": "pipeline.providers.kenburns:KenBurns",
    "kaggle_wan": "pipeline.providers.kaggle_wan:KaggleWan",
    "kaggle_acestep": "pipeline.providers.kaggle_acestep:KaggleAceStep",
    # paid lane: stubs until implemented, see docs/PAID_LANE.md
    "paid_text": "pipeline.providers.paid_stubs:PaidText",
    "paid_tts": "pipeline.providers.paid_stubs:PaidTTS",
    "paid_image": "pipeline.providers.paid_stubs:PaidImage",
    "paid_video": "pipeline.providers.paid_stubs:PaidVideo",
    "rented_gpu_video": "pipeline.providers.paid_stubs:RentedGpuVideo",
    "paid_music": "pipeline.providers.paid_stubs:PaidMusic",
}


@dataclass
class Chain:
    stage: str
    profile: str
    providers: list[Any]

    @property
    def primary(self) -> Any:
        return self.providers[0]

    @property
    def fallbacks(self) -> list[Any]:
        return self.providers[1:]

    def __iter__(self):
        return iter(self.providers)


def load_config(path: Path = CONFIG) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def default_profile(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    return os.environ.get("PROFILE") or cfg.get("default_profile", "free")


def adapter_class(name: str) -> type:
    if name not in ADAPTERS:
        raise KeyError(f"unknown provider {name!r}; known: {sorted(ADAPTERS)}")
    module, _, attr = ADAPTERS[name].partition(":")
    return getattr(importlib.import_module(module), attr)


def build(entry: dict) -> Any:
    cls = adapter_class(entry["provider"])
    return cls(entry["model"], **(entry.get("params") or {}))


def stage_entries(stage: str, profile: str | None = None, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    profile = profile or default_profile(cfg)
    profiles = cfg.get("profiles", {})
    if profile not in profiles:
        raise KeyError(f"unknown profile {profile!r}; known: {sorted(profiles)}")
    entries = profiles[profile].get(stage)
    if not entries:
        raise KeyError(f"profile {profile!r} has no providers for stage {stage!r}")
    return entries


def get_provider(stage: str, profile: str | None = None, cfg: dict | None = None) -> Chain:
    cfg = cfg or load_config()
    profile = profile or default_profile(cfg)
    return Chain(stage, profile, [build(e) for e in stage_entries(stage, profile, cfg)])
