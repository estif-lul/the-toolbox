"""Gemini text (script / storyboard draft / translation) via google-genai generate_content,
with JSON output constrained by a JSON Schema."""

from __future__ import annotations

import json
from typing import Any

from ..common.env import require
from ..common.retry import FatalError
from .base import BaseAdapter, TextResult


class GeminiText(BaseAdapter):
    name = "gemini_text"

    def __init__(self, model: str, **params: Any):
        super().__init__(model, **params)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            # A client timeout makes an overloaded model fail fast so the fallback starts sooner
            # (a 503 once took 104 s to arrive, FAILURES.md F05). HttpOptions.timeout is in ms.
            self._client = genai.Client(
                api_key=require("GEMINI_API_KEY", why="Gemini text stage"),
                http_options={"timeout": int(float(self.params.get("timeout_s", 60)) * 1000)},
            )
        return self._client

    def generate_json(self, prompt: str, schema: dict | None = None,
                      attachments: list[tuple[bytes, str]] = ()) -> TextResult:
        """`attachments` = [(bytes, mime)], e.g. a WAV to transcribe (narration --verify)."""
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=self.params.get("temperature"),
        )
        contents: Any = prompt
        if attachments:
            contents = [*(types.Part.from_bytes(data=d, mime_type=m) for d, m in attachments), prompt]
        resp = self.client.models.generate_content(model=self.model, contents=contents, config=config)
        text = resp.text or ""
        if not text.strip():
            raise FatalError(f"empty response (finish_reason={_finish_reason(resp)})")
        usage = getattr(resp, "usage_metadata", None)
        meta = {
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "thinking_tokens": getattr(usage, "thoughts_token_count", None),
            },
            "model_version": getattr(resp, "model_version", None),
        }
        return TextResult(json.loads(text), text, meta)


def _finish_reason(resp: Any) -> Any:
    try:
        return resp.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return None
