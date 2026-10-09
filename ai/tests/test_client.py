from types import SimpleNamespace

import pytest

from disasterlens_ai import client


def _fake_client(resp):
    return SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: resp)))


def test_detect_mime_png_webp_jpeg_garbage():
    assert client._detect_mime(b"\x89PNG\r\n\x1a\n\x00data") == "image/png"
    assert client._detect_mime(b"RIFF\x10\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert client._detect_mime(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"
    assert client._detect_mime(b"garbage bytes \x00\x01") == "image/jpeg"
    assert client._detect_mime(b"") == "image/jpeg"


def test_truncated_response_raises_value_error(monkeypatch):
    resp = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="length", message=SimpleNamespace(content="partial"))])
    monkeypatch.setattr(client, "_get_client", lambda: _fake_client(resp))
    with pytest.raises(ValueError, match="response truncated"):
        client.chat("system", "user")


def test_per_call_timeout_overrides_the_default(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(client, "_get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))

    client.chat("system", "user", timeout=3.5)
    assert seen["timeout"] == 3.5

    client.chat("system", "user")
    assert seen["timeout"] == client.config.REQUEST_TIMEOUT


def test_image_data_url_uses_detected_mime(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(client, "_get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    client.chat("system", "user", image=b"\x89PNG\r\n\x1a\nrest")
    url = seen["messages"][1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
