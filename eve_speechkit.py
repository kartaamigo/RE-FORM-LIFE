"""Optional Yandex SpeechKit speech recognition and synthesis adapters."""

from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import wave
from typing import Any

from eve_local import LocalProviderError, strip_reasoning


TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
VOICES = (
    {"id": "alena", "name": "Алёна · мягкий женский"},
    {"id": "jane", "name": "Джейн · уверенный женский"},
)


def speechkit_status() -> dict[str, Any]:
    ready = bool(os.environ.get("YANDEX_SPEECHKIT_API_KEY", "").strip()) and bool(
        os.environ.get("YANDEX_SPEECHKIT_FOLDER_ID", "").strip()
    )
    return {
        "ready": ready,
        "backend": "yandex-speechkit",
        "voices": list(VOICES),
        "message": "SpeechKit готов. Голос и распознавание будут отправляться в Яндекс."
        if ready else "Для SpeechKit задай YANDEX_SPEECHKIT_API_KEY и YANDEX_SPEECHKIT_FOLDER_ID и перезапусти приложение.",
    }


def _credentials() -> tuple[str, str]:
    key = os.environ.get("YANDEX_SPEECHKIT_API_KEY", "").strip()
    folder = os.environ.get("YANDEX_SPEECHKIT_FOLDER_ID", "").strip()
    if not key or not folder:
        raise LocalProviderError(speechkit_status()["message"])
    return key, folder


def _request(url: str, payload: bytes, key: str, content_type: str) -> bytes:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Api-Key {key}",
            "Content-Type": content_type,
            "User-Agent": "RE-FORM-LIFE-EVE/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise LocalProviderError(f"SpeechKit вернул ошибку HTTP {exc.code}. Проверь ключ, каталог и доступ к сервису.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LocalProviderError("SpeechKit недоступен. Проверь интернет-соединение и попробуй ещё раз.") from exc


def synthesize_speechkit(text: str, voice: str = "alena") -> bytes:
    """Return a WAV wrapper around SpeechKit's mono 48 kHz signed PCM."""
    key, folder = _credentials()
    cleaned = strip_reasoning(text)[:2000]
    if not cleaned:
        raise LocalProviderError("Нечего озвучивать.")
    if voice not in {item["id"] for item in VOICES}:
        raise LocalProviderError("Выбранный голос SpeechKit недоступен.")
    payload = urllib.parse.urlencode({
        "text": cleaned,
        "lang": "ru-RU",
        "voice": voice,
        "format": "lpcm",
        "sampleRateHertz": "48000",
        "folderId": folder,
    }).encode("utf-8")
    pcm = _request(TTS_URL, payload, key, "application/x-www-form-urlencoded")
    if not pcm or len(pcm) % 2:
        raise LocalProviderError("SpeechKit вернул пустой или повреждённый звук.")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)
        wav_file.writeframes(pcm)
    return output.getvalue()


def transcribe_speechkit(pcm: bytes, sample_rate: int = 16000) -> str:
    """Recognize at most 30 seconds of mono signed 16-bit PCM."""
    if sample_rate != 16000:
        raise ValueError("SpeechKit ожидает запись с частотой 16 кГц.")
    if not pcm or len(pcm) < 3200:
        return ""
    if len(pcm) > 16000 * 2 * 30 or len(pcm) % 2:
        raise ValueError("Запись слишком длинная или повреждена.")
    key, folder = _credentials()
    query = urllib.parse.urlencode({
        "topic": "general",
        "lang": "ru-RU",
        "format": "lpcm",
        "sampleRateHertz": "16000",
        "folderId": folder,
    })
    raw = _request(f"{STT_URL}?{query}", pcm, key, "application/octet-stream")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalProviderError("SpeechKit вернул некорректный ответ распознавания.") from exc
    if not isinstance(result, dict):
        raise LocalProviderError("SpeechKit вернул некорректный ответ распознавания.")
    return str(result.get("result") or "").strip()
