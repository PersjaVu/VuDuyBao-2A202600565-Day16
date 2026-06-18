"""LLM client dùng OpenRouter (API tương thích chuẩn OpenAI).

Cấu hình qua biến môi trường (đọc từ .env nhờ python-dotenv):
- OPENROUTER_API_KEY : bắt buộc, khóa API của OpenRouter.
- OPENROUTER_MODEL   : tùy chọn, id model trên OpenRouter
                       (mặc định: anthropic/claude-3.5-sonnet).
- OPENROUTER_BASE_URL: tùy chọn (mặc định: https://openrouter.ai/api/v1).
"""
from __future__ import annotations
import json
import os
import time
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, APIStatusError, RateLimitError

load_dotenv()

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAX_TOKENS = 1024

# Bộ đếm usage thật cho 1 đơn vị công việc (vd: 1 attempt).
# agents.py gọi reset_usage() trước mỗi attempt rồi get_usage() sau khi xong.
_USAGE = {"tokens": 0, "latency_ms": 0.0}


def reset_usage() -> None:
    _USAGE["tokens"] = 0
    _USAGE["latency_ms"] = 0.0


def get_usage() -> tuple[int, int]:
    """Trả về (tổng token, tổng latency ms) đã tích lũy kể từ reset_usage()."""
    return int(_USAGE["tokens"]), int(round(_USAGE["latency_ms"]))


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing OPENROUTER_API_KEY. Create a .env file (see .env.example) "
            "and set OPENROUTER_API_KEY=<your key>."
        )
    base_url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def _model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def _max_tokens() -> int:
    return int(os.environ.get("OPENROUTER_MAX_TOKENS", DEFAULT_MAX_TOKENS))


def chat(system: str, user: str, *, temperature: float = 0.0) -> str:
    """Gửi 1 lượt chat (system + user) tới LLM và trả về nội dung text.

    Đồng thời tích lũy token & latency thật vào bộ đếm usage.
    """
    start = time.perf_counter()
    resp = _create_with_retry(system, user, temperature)
    _USAGE["latency_ms"] += (time.perf_counter() - start) * 1000.0
    if resp.usage is not None:
        _USAGE["tokens"] += int(resp.usage.total_tokens or 0)
    return (resp.choices[0].message.content or "").strip()


def _create_with_retry(system: str, user: str, temperature: float, *, max_retries: int = 5):
    """Gọi API, tự retry khi gặp 429 (rate limit) với backoff tôn trọng Retry-After."""
    delay = 5.0
    for attempt in range(max_retries + 1):
        try:
            resp = _client().chat.completions.create(
                model=_model(),
                temperature=temperature,
                max_tokens=_max_tokens(),
                messages=[
                    {"role": "system", "content": system.strip()},
                    {"role": "user", "content": user.strip()},
                ],
            )
        except (RateLimitError, APIStatusError) as e:
            status = getattr(e, "status_code", None)
            if status != 429 or attempt == max_retries:
                raise
            time.sleep(_retry_after_seconds(e, default=delay))
            delay = min(delay * 2, 60.0)
            continue
        # OpenRouter đôi khi trả HTTP 200 nhưng choices/content rỗng (provider lỗi tạm thời).
        content = resp.choices[0].message.content if resp.choices else None
        if content and content.strip():
            return resp
        if attempt == max_retries:
            raise RuntimeError(f"LLM trả về response rỗng sau {max_retries} lần thử ({_model()}).")
        time.sleep(delay)
        delay = min(delay * 2, 60.0)


def _retry_after_seconds(err: Exception, *, default: float) -> float:
    try:
        headers = getattr(getattr(err, "response", None), "headers", {}) or {}
        if "retry-after" in headers:
            return float(headers["retry-after"])
        body = getattr(err, "body", None)
        if isinstance(body, dict):
            meta = body.get("error", {}).get("metadata", {})
            if "retry_after_seconds" in meta:
                return float(meta["retry_after_seconds"])
    except (ValueError, TypeError, AttributeError):
        pass
    return default


def chat_json(system: str, user: str, *, temperature: float = 0.0, max_tries: int = 3) -> dict[str, Any]:
    """Như chat() nhưng kỳ vọng output là JSON và parse thành dict.

    Chịu lỗi với trường hợp model bọc JSON trong ```...``` hoặc kèm text thừa;
    nếu parse fail thì gọi lại model (model free đôi khi trả output hỏng).
    """
    last_err: Exception | None = None
    for _ in range(max_tries):
        raw = chat(system, user, temperature=temperature)
        try:
            return _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
    raise RuntimeError(f"Không parse được JSON từ LLM sau {max_tries} lần: {last_err}")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Bỏ hàng rào markdown ```json ... ``` nếu có.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Lấy đoạn từ '{' đầu tiên đến '}' cuối cùng.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise
