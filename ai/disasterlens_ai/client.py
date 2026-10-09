import base64
from openai import OpenAI
from . import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.LLM_API_KEY or not config.LLM_MODEL:
            raise RuntimeError("Set LLM_API_KEY and LLM_MODEL in ai/.env (or DISASTERLENS_STUB=1).")
        _client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    return _client


def chat(system: str, user_text: str, image: bytes | None = None,
         history: list[dict] | None = None) -> str:
    """One model call. Returns raw text. `history` = few-shot message pairs."""
    content: list[dict] = [{"type": "text", "text": user_text}]
    if image:
        b64 = base64.b64encode(image).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    messages = [{"role": "system", "content": system}, *(history or []),
                {"role": "user", "content": content if image else user_text}]
    resp = _get_client().chat.completions.create(
        model=config.LLM_MODEL, messages=messages, temperature=0.1)
    return resp.choices[0].message.content or ""
