import base64
from openai import OpenAI
from . import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.LLM_API_KEY or not config.LLM_MODEL:
            raise RuntimeError("Set LLM_API_KEY and LLM_MODEL in ai/.env (or DISASTERLENS_STUB=1).")
        _client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY,
                         timeout=config.REQUEST_TIMEOUT, max_retries=0)
    return _client


def _detect_mime(image: bytes) -> str:
    """Best-effort MIME for the data URL: png / webp / otherwise jpeg."""
    if image[:4] == b"\x89PNG":
        return "image/png"
    if image[0:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def chat(system: str, user_text: str, image: bytes | None = None,
         history: list[dict] | None = None, timeout: float | None = None,
         json_mode: bool = True) -> str:
    """One model call. Returns raw text. `history` = few-shot message pairs.
    `timeout` overrides the client-wide timeout for this call.
    `json_mode` asks the provider for a JSON object body (only valid when the
    system prompt asks for JSON); pass False for free-form text."""
    content: list[dict] = [{"type": "text", "text": user_text}]
    if image:
        b64 = base64.b64encode(image).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{_detect_mime(image)};base64,{b64}"}})
    messages = [{"role": "system", "content": system}, *(history or []),
                {"role": "user", "content": content if image else user_text}]
    kwargs: dict = dict(model=config.LLM_MODEL, messages=messages, temperature=0.1,
                        max_tokens=config.MAX_TOKENS,
                        timeout=timeout or config.REQUEST_TIMEOUT)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _get_client().chat.completions.create(**kwargs)
    if resp.choices[0].finish_reason == "length":
        raise ValueError("response truncated")
    return resp.choices[0].message.content or ""
