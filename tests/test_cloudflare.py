"""The Cloudflare adapter builds the right request per model family (no network)."""

import base64
import io

import httpx
import pytest
from PIL import Image

from pipeline.providers import cloudflare_image
from pipeline.providers.cloudflare_image import CloudflareImage


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def captured(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "FAKE-token-for-tests")
    calls = []

    def fake_post(url, headers=None, json=None, files=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "files": files})
        req = httpx.Request("POST", url)
        body = {"success": True, "result": {"image": base64.b64encode(_jpeg()).decode()}}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(cloudflare_image.httpx, "post", fake_post)
    return calls


def test_schnell_sends_json_without_seed(captured):
    img = CloudflareImage("@cf/black-forest-labs/flux-1-schnell").generate("an apple", 42, 1024, 1024, steps=4)
    [call] = captured
    assert call["json"] == {"prompt": "an apple", "steps": 4}  # no seed: schnell rejects it (F06)
    assert call["headers"]["Authorization"] == "Bearer FAKE-token-for-tests"
    assert img.seed is None and img.mime == "image/jpeg" and (img.width, img.height) == (64, 64)


def test_schnell_caps_steps_and_rejects_refs(captured, tmp_path):
    CloudflareImage("@cf/black-forest-labs/flux-1-schnell").generate("x", 1, 1024, 1024, steps=30)
    assert captured[-1]["json"]["steps"] == 8
    ref = tmp_path / "r.png"
    ref.write_bytes(b"png")
    with pytest.raises(Exception, match="reference"):
        CloudflareImage("@cf/black-forest-labs/flux-1-schnell").generate("x", 1, 1024, 1024, refs=[ref])


def test_klein_sends_multipart_with_seed_size_and_refs(captured, tmp_path):
    ref = tmp_path / "dad_sheet.jpg"
    ref.write_bytes(_jpeg())
    img = CloudflareImage("@cf/black-forest-labs/flux-2-klein-4b").generate("Dad", 1101, 1024, 1024, refs=[ref])
    parts = dict((name, value) for name, value in captured[-1]["files"])
    assert parts["prompt"] == (None, "Dad") and parts["seed"] == (None, "1101")
    assert parts["width"] == (None, "1024") and parts["height"] == (None, "1024")
    assert parts["input_image_0"][0] == "dad_sheet.jpg" and parts["input_image_0"][2] == "image/jpeg"
    assert captured[-1]["json"] is None and img.seed == 1101


def test_klein_rejects_too_many_refs(captured, tmp_path):
    refs = []
    for i in range(5):
        p = tmp_path / f"r{i}.png"
        p.write_bytes(b"x")
        refs.append(p)
    with pytest.raises(Exception, match="at most 4"):
        CloudflareImage("@cf/black-forest-labs/flux-2-klein-4b").generate("x", 1, 1024, 1024, refs=refs)
