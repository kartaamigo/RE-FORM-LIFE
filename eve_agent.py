"""Optional native EVE agent and cross-platform autostart helpers.

The web app remains usable without microphone packages or a speech model. When
the optional Vosk + sounddevice dependencies and a Russian Vosk model are
present, this module provides a local wake-word loop for the packaged app.
No audio is written to disk.
"""

from __future__ import annotations

import json
import io
import os
import plistlib
import queue
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
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

BROWSER_LABELS = {
    "yandex": "Яндекс Браузер",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "opera": "Opera",
    "brave": "Brave",
    "safari": "Safari",
}

BROWSER_EXECUTABLES = {
    "yandex": ("browser.exe",),
    "chrome": ("chrome.exe", "google-chrome", "google-chrome-stable"),
    "edge": ("msedge.exe", "microsoft-edge"),
    "firefox": ("firefox.exe", "firefox"),
    "opera": ("opera.exe", "opera"),
    "brave": ("brave.exe", "brave-browser"),
    "safari": ("Safari",),
}

WINDOWS_APP_ALIASES = {
    "спотифай": "spotify", "spotify": "spotify",
    "телеграм": "telegram", "телега": "telegram",
    "дискорд": "discord", "стим": "steam", "steam": "steam",
    "ворд": "word", "эксель": "excel", "пауэрпоинт": "powerpoint",
    "блокнот": "notepad", "калькулятор": "calculator",
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
        "applications": Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if sys.platform == "win32" else Path("/Applications"),
    }
    path = paths[location]
    if not path.exists():
        raise ValueError(f"Папка «{requested}» не найдена на этом компьютере.")
    return location, path


def _windows_start_menu_shortcut(application: str) -> Path | None:
    """Find a named app shortcut without accepting executable paths or shell text."""

    requested = normalize_text(application).replace("ё", "е")
    if not requested or len(requested) > 100 or re.search(r"[\\/:*?\"<>|\x00-\r\n]", application):
        return None
    roots = (
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    )
    shortcuts: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for shortcut in root.rglob("*.lnk"):
            if normalize_text(shortcut.stem).replace("ё", "е") == requested:
                return shortcut
            shortcuts.append(shortcut)
    # Speech recognition often changes one or two sounds in an application
    # name. Accept a close Start-menu name, but never an arbitrary path.
    ranked = sorted(
        shortcuts,
        key=lambda item: SequenceMatcher(None, requested, normalize_text(item.stem).replace("ё", "е")).ratio(),
        reverse=True,
    )
    if ranked:
        score = SequenceMatcher(None, requested, normalize_text(ranked[0].stem).replace("ё", "е")).ratio()
        if score >= 0.74:
            return ranked[0]
    return None


def _windows_start_app(application: str) -> str | None:
    """Search the complete Windows Start Apps index, including Store apps."""
    requested = normalize_text(application).replace("ё", "е")
    requested = WINDOWS_APP_ALIASES.get(requested, requested)
    if not requested or len(requested) > 100 or re.search(r"[\\/:*?\"<>|\x00-\r\n]", application):
        return None
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    apps = payload if isinstance(payload, list) else [payload]
    candidates: list[tuple[float, str, str]] = []
    for item in apps:
        if not isinstance(item, dict) or not item.get("Name") or not item.get("AppID"):
            continue
        name = normalize_text(item["Name"]).replace("ё", "е")
        comparable = WINDOWS_APP_ALIASES.get(name, name)
        score = 1.0 if requested == comparable else SequenceMatcher(None, requested, comparable).ratio()
        if requested in comparable or comparable in requested:
            score = max(score, 0.9)
        candidates.append((score, str(item["Name"]), str(item["AppID"])))
    if not candidates:
        return None
    score, name, app_id = max(candidates, key=lambda item: item[0])
    if score < 0.68:
        return None
    executable = Path(app_id)
    if executable.is_absolute() and executable.is_file():
        subprocess.Popen([str(executable)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
        subprocess.Popen([str(explorer), f"shell:AppsFolder\\{app_id}"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return name


def _browser_executable(browser: str) -> str | None:
    for executable in BROWSER_EXECUTABLES.get(browser, ()):
        located = shutil.which(executable)
        if located:
            return located
    if sys.platform != "win32":
        return None
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    known = {
        "yandex": (local / "Yandex" / "YandexBrowser" / "Application" / "browser.exe",),
        "chrome": (program_files / "Google" / "Chrome" / "Application" / "chrome.exe", program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe"),
        "edge": (program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe", program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        "firefox": (program_files / "Mozilla Firefox" / "firefox.exe", program_files_x86 / "Mozilla Firefox" / "firefox.exe"),
        "opera": (local / "Programs" / "Opera" / "opera.exe",),
        "brave": (program_files / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",),
    }
    return next((str(path) for path in known.get(browser, ()) if path.is_file()), None)


def _open_web_target(url: str, browser: str | None = None) -> str:
    requested = str(browser or "").strip().lower()
    if not requested:
        import webbrowser

        if not webbrowser.open(url, new=2):
            raise OSError("Системный браузер не ответил.")
        return "браузер по умолчанию"
    if requested not in BROWSER_LABELS:
        raise ValueError("Поддерживаются Яндекс Браузер, Chrome, Edge, Firefox, Opera, Brave и Safari.")
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", BROWSER_LABELS[requested], url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return BROWSER_LABELS[requested]
    executable = _browser_executable(requested)
    if not executable:
        raise ValueError(f"Не нашла {BROWSER_LABELS[requested]} на этом компьютере.")
    subprocess.Popen([executable, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return BROWSER_LABELS[requested]


def _send_file_to_trash(path: Path) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        operation = SHFILEOPSTRUCTW()
        operation.wFunc = 3  # FO_DELETE
        operation.pFrom = str(path) + "\0"
        operation.fFlags = 0x0040 | 0x0010 | 0x0004  # allow undo; silent; no second prompt
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            raise OSError("Windows не смог переместить файл в Корзину.")
        return
    if sys.platform == "darwin":
        escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
        _run_osascript(f'tell application "Finder" to delete POSIX file "{escaped}"')
        return
    try:
        from send2trash import send2trash

        send2trash(str(path))
    except ImportError as exc:
        raise OSError("Для безопасного перемещения в Корзину нужен модуль send2trash.") from exc


def _windows_audio_endpoint():
    try:
        from comtypes import CLSCTX_ALL, POINTER, cast
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as exc:
        raise OSError(f"Управление звуком Windows недоступно: {exc}") from exc


def _windows_brightness(level: int | None = None) -> int:
    """Read or set laptop/internal-display brightness without elevation."""
    if level is None:
        script = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness"
    else:
        safe_level = max(0, min(100, int(level)))
        script = f"$m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select-Object -First 1; Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness=[byte]{safe_level}}} | Out-Null; {safe_level}"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    output = (completed.stdout or "").strip().splitlines()
    if completed.returncode != 0 or not output or not output[-1].strip().isdigit():
        detail = (completed.stderr or "Монитор не поддерживает программное управление яркостью.").strip()
        raise OSError(detail[-300:])
    return int(output[-1].strip())


def _windows_wifi_adapter() -> str:
    script = "Get-NetAdapter -Physical | Where-Object { $_.NdisPhysicalMedium -eq 9 } | Select-Object -First 1 -ExpandProperty Name"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    name = (completed.stdout or "").strip()
    if completed.returncode != 0 or not name:
        detail = (completed.stderr or "Беспроводной адаптер не найден.").strip()
        raise OSError(detail[-300:])
    return name


def _windows_wifi_status() -> str:
    adapter = _windows_wifi_adapter()
    escaped = adapter.replace("'", "''")
    script = f"(Get-NetAdapter -Name '{escaped}').Status"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError((completed.stderr or "Не удалось прочитать состояние Wi-Fi.").strip()[-300:])
    state = (completed.stdout or "").strip()
    return f"Wi-Fi {adapter}: {'включён' if state.lower() == 'up' else 'выключен'}"


def _set_windows_wifi(state: str) -> str:
    adapter = _windows_wifi_adapter()
    cmdlet = "Enable-NetAdapter" if state == "on" else "Disable-NetAdapter"
    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            f"{cmdlet} -Name $args[0] -Confirm:$false",
            adapter,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError((completed.stderr or completed.stdout or "Windows не разрешил переключить Wi-Fi.").strip()[-300:])
    return _windows_wifi_status()


def _windows_active_window(intent: str) -> str:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        raise OSError("Не нашла активное окно.")
    if intent == "minimize_window":
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        return "Свернула активное окно."
    if intent == "close_window":
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return "Отправила активному окну запрос на закрытие."
    raise ValueError("Неизвестное действие с окном.")


def perform_external_action(
    intent: str,
    target: str | None = None,
    *,
    browser: str | None = None,
    search_engine: str | None = None,
) -> dict[str, Any]:
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
        opened_with = _open_web_target("about:blank", browser)
        return {"location": "browser", "path": "about:blank", "reply": f"Открываю {opened_with}."}

    if intent == "open_url":
        url = str(target or "").strip()
        if url.startswith("www."):
            url = f"https://{url}"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Эва открывает только веб-адреса http или https.")
        opened_with = _open_web_target(url, browser)
        return {"location": "browser", "path": url, "reply": f"Открываю сайт в {opened_with}."}

    if intent == "search_web":
        query = str(target or "").strip()
        if not query or len(query) > 240:
            raise ValueError("Скажи, что найти в интернете.")
        engines = {
            "google": ("Google", "https://www.google.com/search?"),
            "yandex": ("Яндексе", "https://yandex.ru/search/?"),
            "bing": ("Bing", "https://www.bing.com/search?"),
        }
        engine_name, base_url = engines.get(str(search_engine or "google"), engines["google"])
        url = base_url + urllib.parse.urlencode({"text" if search_engine == "yandex" else "q": query})
        opened_with = _open_web_target(url, browser)
        return {"location": "browser", "path": url, "reply": f"Ищу в {engine_name}: «{query}». Открываю результат в {opened_with}."}

    if intent == "set_volume":
        try:
            level = int(str(target or ""))
        except ValueError as exc:
            raise ValueError("Громкость должна быть числом от 0 до 100.") from exc
        if not 0 <= level <= 100:
            raise ValueError("Громкость должна быть от 0 до 100 процентов.")
        if sys.platform == "darwin":
            _run_osascript(f"set volume output volume {level}")
        elif sys.platform == "win32":
            _windows_audio_endpoint().SetMasterVolumeLevelScalar(level / 100.0, None)
        else:
            raise ValueError("Изменение громкости голосом для этой ОС не настроено.")
        return {"location": "audio", "path": str(level), "reply": f"Громкость установлена на {level} процентов."}

    if intent == "adjust_volume":
        try:
            delta = max(-100, min(100, int(str(target or "0"))))
        except ValueError as exc:
            raise ValueError("Изменение громкости должно быть числом.") from exc
        if sys.platform == "win32":
            endpoint = _windows_audio_endpoint()
            level = round(endpoint.GetMasterVolumeLevelScalar() * 100)
            level = max(0, min(100, level + delta))
            endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
        elif sys.platform == "darwin":
            current = int(_run_osascript("output volume of (get volume settings)"))
            level = max(0, min(100, current + delta))
            _run_osascript(f"set volume output volume {level}")
        else:
            raise ValueError("Изменение громкости голосом для этой ОС не настроено.")
        return {"location": "audio", "path": str(level), "reply": f"Громкость теперь {level} процентов."}

    if intent == "mute_audio":
        muted = str(target or "on").lower() == "on"
        if sys.platform == "darwin":
            _run_osascript(f"set volume output muted {str(muted).lower()}")
        elif sys.platform == "win32":
            _windows_audio_endpoint().SetMute(1 if muted else 0, None)
        else:
            raise ValueError("Управление звуком голосом для этой ОС не настроено.")
        return {"location": "audio", "path": "muted" if muted else "unmuted", "reply": "Звук выключен." if muted else "Звук включён."}

    if intent in {"set_brightness", "adjust_brightness"}:
        try:
            requested = int(str(target or "0"))
        except ValueError as exc:
            raise ValueError("Яркость должна быть числом от 0 до 100.") from exc
        if sys.platform == "win32":
            level = requested if intent == "set_brightness" else _windows_brightness() + requested
            level = _windows_brightness(max(0, min(100, level)))
        elif sys.platform == "darwin":
            raise ValueError("Управление яркостью голосом на macOS пока не настроено.")
        else:
            raise ValueError("Управление яркостью для этой ОС пока не настроено.")
        return {"location": "display", "path": str(level), "reply": f"Яркость установлена на {level} процентов."}

    if intent == "minimize_window":
        if sys.platform == "win32":
            reply = _windows_active_window(intent)
        else:
            _run_osascript('tell application "System Events" to keystroke "m" using {command down}')
            reply = "Текущее окно свернуто."
        return {"location": "window", "path": "minimized", "reply": reply}

    if intent == "close_window":
        if sys.platform == "win32":
            reply = _windows_active_window(intent)
        else:
            _run_osascript('tell application "System Events" to keystroke "w" using {command down}')
            reply = "Текущее окно закрыто."
        return {"location": "window", "path": "closed", "reply": reply}

    if intent == "wifi_status":
        output = _windows_wifi_status() if sys.platform == "win32" else _run_networksetup(["-getairportpower"])
        return {"location": "wifi", "path": output or "Состояние Wi‑Fi не определено.", "reply": output or "Состояние Wi‑Fi не определено."}

    if intent == "toggle_wifi":
        state = str(target or "").lower()
        if state not in {"on", "off"}:
            raise ValueError("Укажи, включить или выключить Wi‑Fi.")
        if sys.platform == "win32":
            output = _set_windows_wifi(state)
        else:
            output = _run_networksetup(["-setairportpower", state])
        return {"location": "wifi", "path": state, "reply": f"Wi‑Fi {'включён' if state == 'on' else 'выключен'}. {output}".strip()}

    if intent in {"shutdown", "restart"}:
        if sys.platform == "win32":
            action = "/r" if intent == "restart" else "/s"
            shutdown_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "shutdown.exe"
            subprocess.Popen(
                [str(shutdown_exe), action, "/t", "0"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            verb = "Перезагружаю компьютер." if intent == "restart" else "Выключаю компьютер."
            return {"location": "system", "path": intent, "reply": verb}
        if sys.platform != "darwin":
            raise ValueError("Системное выключение голосом для этой ОС не настроено.")
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
        _send_file_to_trash(path)
        return {"location": "file", "path": str(path), "reply": f"Файл «{path.name}» перемещён в Корзину."}

    if intent == "open_application":
        application = str(target or "").strip()
        if not application or len(application) > 160 or any(char in application for char in "\n\r\x00"):
            raise ValueError("Назови приложение, которое нужно открыть.")
        if sys.platform == "darwin":
            application = MAC_APP_ALIASES.get(normalize_text(application), application)
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", application], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            shortcut = _windows_start_menu_shortcut(application)
            if shortcut is not None:
                os.startfile(str(shortcut))  # type: ignore[attr-defined]
                application = shortcut.stem
            else:
                indexed_name = _windows_start_app(application)
                if indexed_name is None:
                    raise ValueError("Не нашла приложение среди установленных программ Windows. Проверь название или установку приложения.")
                application = indexed_name
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


def input_devices() -> list[dict[str, Any]]:
    """Return local microphone choices without recording audio."""
    try:
        import sounddevice as sd

        devices = []
        seen_names: set[str] = set()
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_input_channels", 0)) < 1:
                continue
            name = str(device.get("name") or f"Микрофон {index}").strip()
            normalized_name = name.casefold()
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            devices.append({
                "id": str(index),
                "name": name,
                "channels": int(device.get("max_input_channels", 1)),
                "sample_rate": int(float(device.get("default_samplerate") or 16000)),
            })
        return devices
    except Exception:
        return []


@lru_cache(maxsize=1)
def _shared_vosk_model():
    from vosk import Model

    return Model(str(model_path()))


def transcribe_pcm(payload: bytes, sample_rate: int = 16000) -> str:
    """Transcribe mono signed 16-bit PCM captured from the selected UI device."""
    if not payload or len(payload) < 3200:
        return ""
    if len(payload) > 16000 * 2 * 30:
        raise ValueError("Запись слишком длинная. Говори не дольше 30 секунд.")
    from vosk import KaldiRecognizer

    recognizer = KaldiRecognizer(_shared_vosk_model(), int(sample_rate))
    recognizer.AcceptWaveform(payload)
    return normalize_text(json.loads(recognizer.FinalResult()).get("text", ""))


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
    try:
        from eve_local import synthesize_speech

        wav_payload = synthesize_speech(text)
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(wav_payload, winsound.SND_MEMORY)
            return
        import numpy as np
        import sounddevice as sd

        with wave.open(io.BytesIO(wav_payload), "rb") as stream:
            audio = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
            channels = stream.getnchannels()
            sample_rate = stream.getframerate()
        if channels > 1:
            audio = audio.reshape(-1, channels)
        sd.play(audio, sample_rate, blocking=True)
    except Exception:
        # Do not silently switch to an unrelated system voice: the selected
        # build profile is the only permitted TTS engine.
        return


def run_native_agent(
    server_url: str = "http://127.0.0.1:8765",
    wake_word: str | None = None,
    continuous_dialog: bool = True,
    device: str | int | None = None,
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

    def discard_queued_audio() -> None:
        while True:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                return

    last_command = ""
    last_command_at = 0.0

    def respond(command_text: str) -> None:
        nonlocal last_command, last_command_at
        now = time.monotonic()
        if command_text == last_command and now - last_command_at < 5:
            discard_queued_audio()
            return
        last_command, last_command_at = command_text, now
        try:
            response = _post_command(server_url, command_text)
            _speak(str(response.get("reply", "")))
        except (urllib.error.URLError, OSError, ValueError):
            _speak("Не удалось связаться с планером")
        discard_queued_audio()

    conversation_recognizer = None
    conversation_deadline = 0.0
    selected_device: int | str | None = None
    if str(device or "").strip():
        selected_device = int(str(device)) if str(device).isdigit() else str(device)
    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1, device=selected_device, callback=callback):
        while not (stop_event and stop_event.is_set()):
            if conversation_recognizer is not None and time.monotonic() >= conversation_deadline:
                conversation_recognizer = None
                wake = KaldiRecognizer(model, 16000, json.dumps([*accepted_wake_words, "[unk]"], ensure_ascii=False))
            try:
                chunk = audio_queue.get(timeout=.25)
            except queue.Empty:
                continue
            if conversation_recognizer is not None:
                if conversation_recognizer.AcceptWaveform(chunk):
                    command_text = normalize_text(json.loads(conversation_recognizer.Result()).get("text", ""))
                    if command_text:
                        if command_text in {"стоп разговор", "заверши разговор", "хватит слушать", "останови разговор"}:
                            _speak("Хорошо. Скажи «Эва», когда понадоблюсь.")
                            discard_queued_audio()
                            conversation_recognizer = None
                            wake = KaldiRecognizer(model, 16000, json.dumps([*accepted_wake_words, "[unk]"], ensure_ascii=False))
                            continue
                        respond(command_text)
                        conversation_deadline = time.monotonic() + 20
                        conversation_recognizer = KaldiRecognizer(model, 16000)
                else:
                    partial = json.loads(conversation_recognizer.PartialResult()).get("partial", "")
                    if partial:
                        conversation_deadline = time.monotonic() + 12
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
                deadline = time.monotonic() + 12
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
            respond(command_text)
            if continuous_dialog:
                conversation_recognizer = KaldiRecognizer(model, 16000)
                conversation_deadline = time.monotonic() + 20
            else:
                wake = KaldiRecognizer(model, 16000, json.dumps([*accepted_wake_words, "[unk]"], ensure_ascii=False))


if __name__ == "__main__":
    run_native_agent(os.environ.get("EVE_AGENT_URL", "http://127.0.0.1:8765"))
