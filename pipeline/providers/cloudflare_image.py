"""Cloudflare Workers AI image models (FLUX.2 klein, FLUX.1 schnell).

POST https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}
- FLUX.1 schnell: JSON body {prompt, seed, steps<=8}; response JSON result.image (base64 JPEG).
- FLUX.2 models: multipart/form-data {prompt, seed, steps, width, height, input_image_0..3};
  response JSON result.image (base64). Reference images are what make character sheets reusable.
Auth is a scoped Workers AI API token (Bearer), never the account's Global API Key (FAILURES.md F02).
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Sequence

import httpx

from ..common.env import require
from ..common.retry import FatalError
from .base import BaseAdapter, ImageResult

API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


def _image_size(data: bytes) -> tuple[int, int, str]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.width, im.height, Image.MIME.get(im.format or "", "application/octet-stream")


class CloudflareImage(BaseAdapter):
    name = "cloudflare_image"

    def __init__(self, model: str, **params: Any):
        super().__init__(model, **params)
        # FLUX.2 takes multipart form-data (and reference images); FLUX.1 takes JSON.
        self.multipart = params.get("multipart", "flux-2" in model)
        self.max_steps = int(params.get("max_steps", 8 if "schnell" in model else 50))
        self.max_refs = int(params.get("max_refs", 4 if self.multipart else 0))
        self.timeout = float(params.get("timeout_s", 120))

    def _url_headers(self) -> tuple[str, dict]:
        account = require("CLOUDFLARE_ACCOUNT_ID", why="keyframes stage (Cloudflare Workers AI)")
        token = require("CLOUDFLARE_API_TOKEN", why="keyframes stage (Cloudflare Workers AI)")
        return API.format(account=account, model=self.model), {"Authorization": f"Bearer {token}"}

    def generate(self, prompt: str, seed: int, w: int = 1024, h: int = 1024, refs: Sequence[Path] = (),
                 steps: int | None = None) -> ImageResult:
        url, headers = self._url_headers()
        steps = min(int(steps or self.params.get("steps", 4)), self.max_steps)
        if refs and len(refs) > self.max_refs:
            raise FatalError(f"{self.model} accepts at most {self.max_refs} reference images, got {len(refs)}")
        if self.multipart:
            # Every field goes in as a multipart part: (None, value) is a plain form field.
            # (httpx only sends multipart/form-data when `files` is non-empty.)
            form = {"prompt": prompt, "seed": str(seed), "steps": str(steps), "width": str(w), "height": str(h)}
            parts: list[tuple[str, tuple]] = [(k, (None, v)) for k, v in form.items()]
            for i, p in enumerate(refs):
                p = Path(p)
                mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                parts.append((f"input_image_{i}", (p.name, p.read_bytes(), mime)))
            resp = httpx.post(url, headers=headers, files=parts, timeout=self.timeout)
        else:
            if refs:
                raise FatalError(f"{self.model} does not take reference images")
            body = {"prompt": prompt, "seed": seed, "steps": steps}
            if self.params.get("send_size"):
                body.update(width=w, height=h)
            resp = httpx.post(url, headers=headers, json=body, timeout=self.timeout)
        resp.raise_for_status()

        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("image/"):
            data = resp.content
        else:
            payload = resp.json()
            if not payload.get("success", True):
                raise FatalError(f"Workers AI error: {payload.get('errors')}")
            image = (payload.get("result") or {}).get("image")
            if not image:
                raise FatalError(f"no image in response: {str(payload)[:300]}")
            data = base64.b64decode(image)
        width, height, mime = _image_size(data)
        meta = {"steps": steps, "refs": [Path(p).name for p in refs], "requested": [w, h],
                "cf_ray": resp.headers.get("cf-ray")}
        return ImageResult(data, mime, width, height, seed, meta)
