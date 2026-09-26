"""Local Ollama and Piper adapters used by EVE.

The adapters deliberately expose text and audio only.  Command execution is
still owned by :mod:`eve_assistant` and ``app.py`` so a model response cannot
silently turn into a system action.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "deepseek-r1:8b"
DEFAULT_PIPER_MODEL_NAME = "ru_RU-irina-medium.onnx"
OLLAMA_TIMEOUT_SECONDS = 3.0
OLLAMA_GENERATE_TIMEOUT_SECONDS = 60.0

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)


class LocalProviderError(RuntimeError):
    """A user-facing failure from Ollama or Piper."""


def strip_reasoning(text: Any) -> str:
    """Remove DeepSeek/Ollama reasoning markup before it reaches the user."""

    value = str(text or "").replace("\x00", "").strip()
    if not value:
        return ""
    value = _THINK_BLOCK_RE.sub("", value)
    # A short generation can end inside a reasoning block.  Do not expose a
    # partial chain of thought in that case.
    if re.search(r"<think\b", value, re.IGNORECASE) and not re.search(r"</think\s*>", value, re.IGNORECASE):
        return ""
    value = _THINK_TAG_RE.sub("", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _ollama_url() -> str:
    configured = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL).strip()
    if not configured:
        configured = DEFAULT_OLLAMA_URL
    if "://" not in configured:
        configured = f"http://{configured}"
    return configured.rstrip("/")


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except OSError:
            pass
        raise LocalProviderError(f"Локальный сервис вернул ошибку {exc.code}. {detail}".strip()) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LocalProviderError(f"Локальный сервис недоступен: {exc}") from exc
    try:
        result = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise LocalProviderError("Локальный сервис вернул некорректный ответ.") from exc
    if not isinstance(result, dict):
        raise LocalProviderError("Локальный сервис вернул неожиданный ответ.")
    return result


def ollama_status(model: str = DEFAULT_OLLAMA_MODEL) -> dict[str, Any]:
    """Return a non-throwing health snapshot for Ollama and its model."""

    url = _ollama_url()
    requested_model = str(model or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    try:
        payload = _json_request(f"{url}/api/tags", timeout=OLLAMA_TIMEOUT_SECONDS)
    except LocalProviderError as exc:
        return {
            "ready": False,
            "service_ready": False,
            "model_ready": False,
            "backend": "ollama",
            "url": url,
            "model": requested_model,
            "message": str(exc),
        }
    models = payload.get("models") if isinstance(payload.get("models"), list) else []
    names = {str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")}
    model_ready = requested_model in names
    return {
        "ready": model_ready,
        "service_ready": True,
        "model_ready": model_ready,
        "backend": "ollama",
        "url": url,
        "model": requested_model,
        "installed_models": sorted(names),
        "message": "DeepSeek готова к работе" if model_ready else f"Модель «{requested_model}» не загружена в Ollama.",
    }


def generate_local_reply(text: str, model: str = DEFAULT_OLLAMA_MODEL) -> str:
    """Ask DeepSeek for a conversational answer to an unknown command.

    The prompt explicitly disallows action instructions.  The caller only
    invokes this after the deterministic command parser returned ``unknown``.
    """

    user_text = str(text or "").strip()
    if not user_text:
        raise LocalProviderError("Пустой запрос к локальной модели.")
    prompt = (
        "Ты — EVE, локальный помощник приложения RE:FORM LIFE. "
        "Ответь пользователю по-русски коротко и дружелюбно, максимум 3 предложения. "
        "Если просьба требует изменения задач, финансов, коммуналки или системы, "
        "скажи, что для этого нужна более точная команда. Не придумывай выполненные "
        "действия, не используй XML-теги и не показывай рассуждения.\n\n"
        f"Сообщение пользователя: {user_text}"
    )
    payload = _json_request(
        f"{_ollama_url()}/api/generate",
        method="POST",
        payload={
            "model": str(model or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0.2, "num_predict": 768},
        },
        timeout=OLLAMA_GENERATE_TIMEOUT_SECONDS,
    )
    reply = strip_reasoning(payload.get("response"))
    if not reply:
        raise LocalProviderError("Локальная модель не вернула готовый ответ.")
    return reply


def _piper_model_candidates() -> list[Path]:
    configured = os.environ.get("EVE_PIPER_MODEL", "").strip()
    candidates: list[Path] = [Path(configured).expanduser()] if configured else []
    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "RE-FORM LIFE" / "tts-models" / DEFAULT_PIPER_MODEL_NAME)
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path.cwd())))
    roots.extend((Path(__file__).resolve().parent, Path.cwd()))
    candidates.extend(root / "tts-models" / DEFAULT_PIPER_MODEL_NAME for root in roots)
    return candidates


def piper_model_path() -> Path | None:
    """Find the configured or bundled Piper model without downloading anything."""

    for candidate in _piper_model_candidates():
        if candidate.is_file() and Path(f"{candidate}.json").is_file():
            return candidate.resolve()
    return None


def piper_status() -> dict[str, Any]:
    model = piper_model_path()
    try:
        from piper.voice import PiperVoice  # noqa: F401
    except Exception as exc:
        return {
            "ready": False,
            "backend": "piper",
            "model_ready": model is not None,
            "model_path": str(model) if model else None,
            "message": f"Piper недоступен: {exc}",
        }
    if model is None:
        return {
            "ready": False,
            "backend": "piper",
            "model_ready": False,
            "model_path": None,
            "message": "Русская модель Piper не найдена.",
        }
    return {
        "ready": True,
        "backend": "piper",
        "model_ready": True,
        "model_path": str(model),
        "message": "Локальный русский голос готов",
    }


@lru_cache(maxsize=2)
def _load_piper_voice(model_path: str):
    try:
        from piper.voice import PiperVoice

        return PiperVoice.load(model_path)
    except Exception as exc:
        raise LocalProviderError(f"Не удалось загрузить голос Piper: {exc}") from exc


def synthesize_speech(text: str) -> bytes:
    """Synthesize a WAV payload with the local Russian Piper voice."""

    cleaned = strip_reasoning(text)
    if not cleaned:
        raise LocalProviderError("Нечего озвучивать.")
    if len(cleaned) > 2000:
        cleaned = cleaned[:1997].rstrip() + "…"
    model = piper_model_path()
    if model is None:
        raise LocalProviderError("Русская модель Piper не найдена.")
    output = io.BytesIO()
    voice = _load_piper_voice(str(model))
    try:
        with wave.open(output, "wb") as wav_file:
            voice.synthesize_wav(cleaned, wav_file)
    except Exception as exc:
        raise LocalProviderError(f"Не удалось синтезировать речь: {exc}") from exc
    return output.getvalue()


def local_providers_status(model: str = DEFAULT_OLLAMA_MODEL) -> dict[str, Any]:
    return {"llm": ollama_status(model), "tts": piper_status()}
