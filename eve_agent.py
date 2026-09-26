"""Optional native EVE agent and cross-platform autostart helpers.

The web app remains usable without microphone packages or a speech model. When
the optional Vosk + sounddevice dependencies and a Russian Vosk model are
present, this module provides a local wake-word loop for the packaged app.
No audio is written to disk.
"""

from __future__ import annotations

import json
import os
import plistlib
import queue
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from eve_assistant import normalize_text, strip_wake_word


APP_AUTOSTART_NAME = "RE-FORM LIFE EVE"
MAC_LAUNCH_AGENT = "com.reformlife.eve.plist"

SAFE_EXTERNAL_LOCATIONS = {
    "домой": "home",
    "дом": "home",
    "home": "home",
    "загрузки": "downloads",
    "загрузка": "downloads",
    "downloads": "downloads",
    "рабочий стол": "desktop",
    "рабочем столе": "desktop",
    "desktop": "desktop",
    "документы": "documents",
    "документах": "documents",
    "documents": "documents",
    "приложения": "applications",
    "applications": "applications",
}

MAC_APP_ALIASES = {
    "сафари": "Safari",
    "safari": "Safari",
    "файндер": "Finder",
    "finder": "Finder",
    "терминал": "Terminal",
    "terminal": "Terminal",
    "заметки": "Notes",
    "календарь": "Calendar",
    "музыка": "Music",
    "почта": "Mail",
}


def _run_osascript(script: str) -> str:
    if sys.platform != "darwin":
        raise ValueError("Эта системная команда сейчас доступна только на macOS.")
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError((completed.stderr or "Системное действие macOS не выполнено.").strip())
    return (completed.stdout or "").strip()


def _wifi_device() -> str:
    if sys.platform != "darwin":
        raise ValueError("Управление Wi‑Fi сейчас доступно только на macOS.")
    completed = subprocess.run(
        ["networksetup", "-listallhardwareports"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    lines = (completed.stdout or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() in {"hardware port: wi-fi", "hardware port: wi‑fi"}:
            for candidate in lines[index + 1:index + 4]:
                if candidate.strip().lower().startswith("device:"):
                    return candidate.split(":", 1)[1].strip()
    return "en0"


def _run_networksetup(arguments: list[str]) -> str:
    device = _wifi_device()
    command = ["networksetup", *arguments, device]
    if arguments and arguments[0] == "-setairportpower" and len(arguments) == 2:
        command = ["networksetup", "-setairportpower", device, arguments[1]]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError((completed.stderr or completed.stdout or "Команда networksetup не выполнена.").strip())
    return (completed.stdout or "").strip()


def _safe_location(value: str | None) -> tuple[str, Path]:
    requested = normalize_text(value or "домой").replace("ё", "е")
    location = SAFE_EXTERNAL_LOCATIONS.get(requested)
    if location is None:
        raise ValueError("Эва может открыть только Домой, Загрузки, Рабочий стол или Документы.")
    home = Path.home()
    paths = {
        "home": home,
        "downloads": home / "Downloads",
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "applications": Path("/Applications"),
    }
    path = paths[location]
    if not path.exists():
        raise ValueError(f"Папка «{requested}» не найдена на этом компьютере.")
    return location, path


def perform_external_action(intent: str, target: str | None = None) -> dict[str, Any]:
    """Run one of EVE's deliberately small, non-destructive system actions.

    No shell, arbitrary executable, or user-supplied command is accepted here.
    New system actions should be added explicitly to this allow-list.
    """
    if intent == "open_explorer":
        location, path = _safe_location(target)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            raise ValueError("Открытие файлового менеджера для этой ОС пока не настроено.")
        return {"location": location, "path": str(path)}

    if intent == "open_browser":
        import webbrowser

        if not webbrowser.open("about:blank", new=2):
            raise OSError("Системный браузер не ответил.")
        return {"location": "browser", "path": "about:blank"}

    if intent == "open_url":
        url = str(target or "").strip()
        if url.startswith("www."):
            url = f"https://{url}"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Эва открывает только веб-адреса http или https.")
        import webbrowser

        if not webbrowser.open(url, new=2):
            raise OSError("Системный браузер не ответил.")
        return {"location": "browser", "path": url}

    if intent == "search_web":
        query = str(target or "").strip()
        if not query or len(query) > 240:
            raise ValueError("Скажи, что найти в интернете.")
        import webbrowser

        url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})
        if not webbrowser.open(url, new=2):
            raise OSError("Системный браузер не ответил.")
        return {"location": "browser", "path": url}

    if intent == "set_volume":
        try:
            level = int(str(target or ""))
        except ValueError as exc:
            raise ValueError("Громкость должна быть числом от 0 до 100.") from exc
        if not 0 <= level <= 100:
            raise ValueError("Громкость должна быть от 0 до 100 процентов.")
        if sys.platform == "darwin":
            _run_osascript(f"set volume output volume {level}")
        else:
            raise ValueError("Изменение громкости голосом пока настроено для macOS.")
        return {"location": "audio", "path": str(level), "reply": f"Громкость установлена на {level} процентов."}

    if intent == "mute_audio":
        muted = str(target or "on").lower() == "on"
        if sys.platform == "darwin":
            _run_osascript(f"set volume output muted {str(muted).lower()}")
        else:
            raise ValueError("Управление звуком голосом пока настроено для macOS.")
        return {"location": "audio", "path": "muted" if muted else "unmuted", "reply": "Звук выключен." if muted else "Звук включён."}

    if intent == "minimize_window":
        _run_osascript('tell application "System Events" to keystroke "m" using {command down}')
        return {"location": "window", "path": "minimized", "reply": "Текущее окно свернуто."}

    if intent == "close_window":
        _run_osascript('tell application "System Events" to keystroke "w" using {command down}')
        return {"location": "window", "path": "closed", "reply": "Текущее окно закрыто."}

    if intent == "wifi_status":
        output = _run_networksetup(["-getairportpower"])
        return {"location": "wifi", "path": output or "Состояние Wi‑Fi не определено.", "reply": output or "Состояние Wi‑Fi не определено."}

    if intent == "toggle_wifi":
        state = str(target or "").lower()
        if state not in {"on", "off"}:
            raise ValueError("Укажи, включить или выключить Wi‑Fi.")
        output = _run_networksetup(["-setairportpower", state])
        return {"location": "wifi", "path": state, "reply": f"Wi‑Fi {'включён' if state == 'on' else 'выключен'}. {output}".strip()}

    if intent in {"shutdown", "restart"}:
        if sys.platform != "darwin":
            raise ValueError("Системное выключение голосом пока настроено для macOS.")
        verb = "restart" if intent == "restart" else "shut down"
        _run_osascript(f'tell application "System Events" to {verb}')
        return {"location": "system", "path": intent, "reply": "Перезагружаю Mac." if intent == "restart" else "Выключаю Mac."}

    if intent == "delete_file":
        requested = Path(str(target or "").strip()).expanduser()
        home = Path.home().resolve()
        path = (home / requested if not requested.is_absolute() else requested).resolve()
        try:
            path.relative_to(home)
        except ValueError as exc:
            raise ValueError("Эва удаляет только файлы внутри домашней папки пользователя.") from exc
        if path == home or not path.exists() or not path.is_file():
            raise ValueError("Найден только обычный файл внутри домашней папки.")
        path.unlink()
        return {"location": "file", "path": str(path), "reply": f"Файл «{path.name}» удалён."}

    if intent == "open_application":
        application = str(target or "").strip()
        if not application or len(application) > 160 or any(char in application for char in "\n\r\x00"):
            raise ValueError("Назови приложение, которое нужно открыть.")
        if sys.platform == "darwin":
            application = MAC_APP_ALIASES.get(normalize_text(application), application)
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", application], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(application)  # type: ignore[attr-defined]
        elif sys.platform.startswith("linux"):
            subprocess.Popen([application], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            raise ValueError("Запуск приложений для этой ОС пока не настроен.")
        return {"location": "application", "path": application}

    raise ValueError("Это внешнее действие пока не разрешено.")


def data_dir() -> Path:
    configured = os.environ.get("REFORM_LIFE_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "RE-FORM LIFE"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RE-FORM LIFE"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "RE-FORM LIFE"


def model_path() -> Path:
    configured = os.environ.get("EVE_VOSK_MODEL")
    if configured:
        return Path(configured).expanduser()
    user_model = data_dir() / "voice-models" / "vosk-model-small-ru-0.22"
    if user_model.is_dir():
        return user_model

    # Keep the first launch self-contained when the packaged distribution
    # includes the small Russian model. A user-provided model above still
    # takes precedence, so advanced setups can replace it without rebuilding.
    bundle_roots = []
    if getattr(sys, "frozen", False):
        bundle_roots.append(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)))
    bundle_roots.append(Path(__file__).resolve().parent)
    for root in bundle_roots:
        bundled = root / "voice-models" / "vosk-model-small-ru-0.22"
        if bundled.is_dir():
            return bundled
    return user_model


def native_agent_status() -> dict[str, Any]:
    missing: list[str] = []
    for module_name in ("vosk", "sounddevice"):
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)
    model_ready = model_path().is_dir()
    ready = not missing and model_ready
    if ready:
        message = "Локальный микрофон и русская модель готовы"
    else:
        missing_message = "Нужны дополнительные пакеты: " + ", ".join(missing) if missing else ""
        model_message = "Нужна русская голосовая модель: " + str(model_path()) if not model_ready else ""
        message = ". ".join(item for item in (missing_message, model_message) if item)
    return {
        "ready": ready,
        "backend": "vosk" if ready else "browser-fallback",
        "missing_packages": missing,
        "model_path": str(model_path()),
        "model_ready": model_ready,
        "autostart_supported": sys.platform in {"darwin", "win32"},
        "message": message,
    }


def application_command() -> list[str]:
    override = os.environ.get("REFORM_LIFE_AUTOSTART_COMMAND")
    if override:
        return shlex.split(override)
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).with_name("launcher.py"))]


def configure_autostart(enabled: bool) -> dict[str, Any]:
    """Install or remove a per-user startup entry without requiring admin rights."""
    command = application_command()
    if sys.platform == "win32":
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(APP_AUTOSTART_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, APP_AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return {"supported": True, "enabled": enabled, "location": "Windows user startup"}
    if sys.platform == "darwin":
        launch_agents = Path.home() / "Library" / "LaunchAgents"
        plist_path = launch_agents / MAC_LAUNCH_AGENT
        if enabled:
            launch_agents.mkdir(parents=True, exist_ok=True)
            payload = {
                "Label": MAC_LAUNCH_AGENT.removesuffix(".plist"),
                "ProgramArguments": command,
                "RunAtLoad": True,
                "KeepAlive": False,
                "ProcessType": "Interactive",
            }
            with plist_path.open("wb") as handle:
                plistlib.dump(payload, handle)
        elif plist_path.exists():
            plist_path.unlink()
        return {"supported": True, "enabled": enabled, "location": str(plist_path)}
    return {"supported": False, "enabled": False, "location": None, "message": "Для этой ОС автозапуск пока не настроен."}


def _post_command(server_url: str, text: str) -> dict[str, Any]:
    payload = json.dumps({"text": text, "source": "background"}).encode("utf-8")
    request = urllib.request.Request(
        f"{server_url.rstrip('/')}/api/assistant/command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _speak(text: str) -> None:
    if not text:
        return
    if sys.platform == "darwin":
        subprocess.Popen(["say", "-v", os.environ.get("EVE_MAC_VOICE", "Milena"), text])
        return
    if sys.platform == "win32":
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception:
            return


def run_native_agent(
    server_url: str = "http://127.0.0.1:8765",
    wake_word: str | None = None,
    stop_event: Any = None,
) -> None:
    """Run a local Vosk wake-word loop until the process is stopped."""
    status = native_agent_status()
    if not status["ready"]:
        raise RuntimeError(status["message"])
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except Exception as exc:  # pragma: no cover - status check catches this first
        raise RuntimeError(f"Голосовой движок EVE недоступен: {exc}") from exc

    audio_queue: queue.Queue[bytes] = queue.Queue()
    model = Model(str(model_path()))

    def callback(indata, _frames, _time, _status):
        audio_queue.put(bytes(indata))

    accepted_wake_words = tuple(dict.fromkeys((wake_word or "эва", "эва", "ева", "eve")))
    wake = KaldiRecognizer(model, 16000, json.dumps([*accepted_wake_words, "[unk]"], ensure_ascii=False))
    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1, callback=callback):
        while not (stop_event and stop_event.is_set()):
            try:
                chunk = audio_queue.get(timeout=.25)
            except queue.Empty:
                continue
            if not wake.AcceptWaveform(chunk):
                continue
            result = normalize_text(json.loads(wake.Result()).get("text", ""))
            if not any(result == word or result.startswith(f"{word} ") for word in accepted_wake_words):
                continue
            inline_command = strip_wake_word(result)
            _speak("Слушаю")
            command_text = inline_command.strip()
            if not command_text:
                command_recognizer = KaldiRecognizer(model, 16000)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not (stop_event and stop_event.is_set()):
                    try:
                        command_chunk = audio_queue.get(timeout=.25)
                    except queue.Empty:
                        continue
                    if command_recognizer.AcceptWaveform(command_chunk):
                        command_text = normalize_text(json.loads(command_recognizer.Result()).get("text", ""))
                        if command_text:
                            break
                if not command_text:
                    try:
                        command_text = normalize_text(json.loads(command_recognizer.FinalResult()).get("text", ""))
                    except (AttributeError, ValueError, TypeError):
                        command_text = ""
            if not command_text:
                continue
            try:
                response = _post_command(server_url, command_text)
                _speak(str(response.get("reply", "")))
            except (urllib.error.URLError, OSError, ValueError):
                _speak("Не удалось связаться с планером")


if __name__ == "__main__":
    run_native_agent(os.environ.get("EVE_AGENT_URL", "http://127.0.0.1:8765"))
