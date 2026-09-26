"""Pure command parsing helpers for the EVE planner assistant.

The parser deliberately knows nothing about Flask, SQLite, microphones, or the
operating system.  That keeps voice input, the web UI, and the optional native
background agent on the same safe command vocabulary.
"""

from __future__ import annotations

import re
from difflib import get_close_matches
from dataclasses import dataclass
from datetime import date, timedelta


WAKE_WORDS = ("эва", "ева", "eve")
WEEKDAY_INDEX = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "среду": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}
MONTH_INDEX = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


@dataclass(frozen=True)
class ParsedCommand:
    intent: str
    raw: str
    query: str = ""
    task_text: str = ""
    task_date: str | None = None
    start_time: str | None = None
    scope: str = "planner"
    section: str | None = None
    target: str = ""
    amount_text: str = ""
    category: str = ""
    finance_kind: str = ""
    account: str = ""
    service: str = ""
    value_text: str = ""
    browser: str = ""
    search_engine: str = ""
    content: str = ""


COMMAND_WORDS = (
    "открой", "запусти", "покажи", "перейди", "зайди", "найди", "поищи",
    "добавь", "создай", "запиши", "запланируй", "отметь", "заверши",
    "выполни", "перенеси", "передвинь", "поставь", "установи", "сделай",
    "включи", "выключи", "расскажи",
    "увеличь", "прибавь", "повысь", "уменьши", "убавь", "понизь",
    "запомни", "сохрани", "забудь", "удали",
)

BROWSER_ALIASES = {
    "яндекс": "yandex", "яндекс браузер": "yandex", "yandex": "yandex",
    "гугл": "chrome", "гугл хром": "chrome", "google chrome": "chrome",
    "хром": "chrome", "chrome": "chrome", "эдж": "edge", "edge": "edge",
    "майкрософт эдж": "edge", "фаерфокс": "firefox", "файрфокс": "firefox",
    "firefox": "firefox", "опера": "opera", "opera": "opera",
    "брейв": "brave", "brave": "brave", "сафари": "safari", "safari": "safari",
}

SEARCH_ENGINE_ALIASES = {
    "яндекс": "yandex", "яндексе": "yandex", "yandex": "yandex",
    "гугл": "google", "гугле": "google", "google": "google",
    "бинг": "bing", "бинге": "bing", "bing": "bing",
}

KNOWN_SITES = {
    "яндекс": "https://ya.ru", "гугл": "https://www.google.com",
    "google": "https://www.google.com", "ютуб": "https://www.youtube.com",
    "youtube": "https://www.youtube.com", "вконтакте": "https://vk.com",
    "вк": "https://vk.com", "телеграм": "https://web.telegram.org",
    "спотифай": "https://open.spotify.com", "spotify": "https://open.spotify.com",
    "рутуб": "https://rutube.ru", "rutube": "https://rutube.ru",
    "кинопоиск": "https://www.kinopoisk.ru", "озон": "https://www.ozon.ru",
    "вайлдберриз": "https://www.wildberries.ru", "wildberries": "https://www.wildberries.ru",
    "авито": "https://www.avito.ru", "одноклассники": "https://ok.ru",
    "майл": "https://mail.ru", "мэйл": "https://mail.ru", "mail": "https://mail.ru",
    "дзен": "https://dzen.ru", "яндекс карты": "https://yandex.ru/maps",
}


def normalize_text(value: object) -> str:
    # Keep a colon so voice times such as «19:30» survive command parsing.
    return re.sub(r"\s+", " ", re.sub(r"[«».,!?;]", " ", str(value or "").lower())).strip()


def normalize_command_text(value: object) -> str:
    """Correct a likely speech typo in the command verb without touching user data."""
    text = normalize_text(value)
    words = text.split()
    if not words:
        return text
    first_index = 1 if words[0] in WAKE_WORDS and len(words) > 1 else 0
    candidate = words[first_index]
    if candidate not in COMMAND_WORDS:
        match = get_close_matches(candidate, COMMAND_WORDS, n=1, cutoff=0.72)
        if match:
            words[first_index] = match[0]
    return " ".join(words)


def choose_command_candidate(primary: str, alternatives: object, today: date | None = None) -> str:
    """Prefer the first browser speech alternative that maps to a real EVE command."""
    candidates = [str(primary or "").strip()]
    if isinstance(alternatives, list):
        candidates.extend(str(item or "").strip() for item in alternatives[:4])
    candidates = [item for index, item in enumerate(candidates) if item and item not in candidates[:index]]
    for candidate in candidates:
        if parse_command(candidate, today).intent != "unknown":
            return candidate
    return candidates[0] if candidates else ""


def _browser_from_text(value: str) -> str:
    requested = normalize_text(value).replace("браузере", "").replace("браузер", "").strip()
    if requested in BROWSER_ALIASES:
        return BROWSER_ALIASES[requested]
    match = get_close_matches(requested, BROWSER_ALIASES, n=1, cutoff=0.72)
    return BROWSER_ALIASES[match[0]] if match else ""


def _extract_browser_suffix(value: str) -> tuple[str, str]:
    default_browser = re.search(r"\s+в\s+браузере?\s*$", value, flags=re.IGNORECASE)
    if default_browser:
        return value[:default_browser.start()].strip(), ""
    match = re.search(r"\s+(?:в|через)\s+(.+?)(?:\s+браузере?|\s+browser)\s*$", value, flags=re.IGNORECASE)
    if not match:
        return value, ""
    browser = _browser_from_text(match.group(1))
    if not browser:
        return value, ""
    return value[:match.start()].strip(), browser


def strip_wake_word(value: str) -> str:
    pattern = r"^(?:" + "|".join(re.escape(word) for word in WAKE_WORDS) + r")[,:]?\s*"
    return re.sub(pattern, "", value.strip(), count=1, flags=re.IGNORECASE)


def iso_day(value: date) -> str:
    return value.isoformat()


def date_from_text(value: str, today: date | None = None) -> date | None:
    text = normalize_text(value)
    current = today or date.today()
    relative = re.search(r"(?:на|в)?\s*(послезавтра|завтра|сегодня)\b", text)
    if relative:
        offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[relative.group(1)]
        return current + timedelta(days=offset)
    weekday = re.search(r"(?:на|в)?\s*(понедельник|вторник|среда|среду|четверг|пятница|суббота|воскресенье)\b", text)
    if weekday:
        current_index = current.weekday()
        shift = (WEEKDAY_INDEX[weekday.group(1)] - current_index) % 7
        if shift == 0:
            shift = 7
        return current + timedelta(days=shift)
    named = re.search(r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b", text)
    if named:
        year = current.year
        result = date(year, MONTH_INDEX[named.group(2)], int(named.group(1)))
        if result < current:
            result = date(year + 1, MONTH_INDEX[named.group(2)], int(named.group(1)))
        return result
    numeric = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b", text)
    if numeric:
        return date(int(numeric.group(3) or current.year), int(numeric.group(2)), int(numeric.group(1)))
    return None


def week_date_from_text(value: str, today: date | None = None) -> date | None:
    """Resolve a requested week to a representative date.

    The planner accepts a concrete day as the anchor for a week.  Supporting
    relative week phrases here keeps the web UI and the native voice agent on
    the same vocabulary without adding an LLM dependency.
    """
    text = normalize_text(value)
    current = today or date.today()
    if re.search(r"\b(?:следующ(?:ую|ей)|будущ(?:ую|ей))\s+недел", text):
        return current + timedelta(days=7)
    if re.search(r"\b(?:прошл(?:ую|ой)|предыдущ(?:ую|ей))\s+недел", text):
        return current - timedelta(days=7)
    if re.search(r"\b(?:эту|текущ(?:ую|ей))\s+недел", text):
        return current
    return date_from_text(text, current)


def schedule_from_text(value: str, today: date | None = None) -> tuple[str, str, str | None]:
    text = str(value or "").strip()
    scheduled = date_from_text(text, today) or (today or date.today())
    start_time = None
    time_match = re.search(r"(?:\s+(?:в|на)\s+)(\d{1,2})(?::(\d{2}))?(?!:)\s*(?:час(?:а|ов)?\s*)?(утра|дня|вечера|ночи)?\b", text, flags=re.IGNORECASE)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        part = (time_match.group(3) or "").lower()
        if part == "вечера" and hour < 12:
            hour += 12
        if part in {"утра", "ночи"} and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            start_time = f"{hour:02d}:{minute:02d}"
        text = text.replace(time_match.group(0), " ")
    text = re.sub(r"(?:\s+(?:на|в)\s+)?(?:послезавтра|завтра|сегодня|понедельник|вторник|среда|среду|четверг|пятница|суббота|воскресенье)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:на|в)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .,!?\t\n")
    return text, iso_day(scheduled), start_time


TASKS_SCOPE_PATTERN = re.compile(
    r"\b(?:в|во|на)\s+(?:(?:раздел(?:е)?|список)\s+)?задач(?:и|у|ах)?\b"
    r"|\b(?:на|в)\s+доску\s+задач\b"
    r"|\b(?:в|на)\s+канбан(?:-доску)?\b",
    flags=re.IGNORECASE,
)
PLANNER_SCOPE_PATTERN = re.compile(
    r"\b(?:в|на)\s+(?:(?:недельн(?:ый|ом|ую|ого)?)\s+)?планер(?:е|а)?\b",
    flags=re.IGNORECASE,
)
SECTION_TAIL = (
    r"(?:послезавтра|завтра|сегодня|понедельник|вторник|среда|среду|"
    r"четверг|пятница|суббота|воскресенье|\d{1,2}(?::\d{2})?)"
)


def command_scope(value: str) -> str:
    """Return the requested task board without coupling parsing to SQLite."""
    return "tasks" if TASKS_SCOPE_PATTERN.search(normalize_text(value)) else "planner"


def external_target(value: str | None) -> str:
    """Normalize a user-facing safe location name for the system adapter."""
    return normalize_text(value or "домой")


def url_target(value: str | None) -> str:
    """Keep a URL intact while removing only surrounding whitespace."""
    return str(value or "").strip().strip("<>\"'")


def extract_task_destination(value: str) -> tuple[str, str, str | None]:
    """Remove board/column hints from an add-task command.

    Examples accepted by the text and voice interfaces:
    ``в раздел задачи доделать ДЗ в стол Учёба`` and
    ``доделать ДЗ в раздел Учёба на завтра``.
    """
    text = normalize_text(value)
    scope = command_scope(text)
    scope_match = TASKS_SCOPE_PATTERN.search(text) or PLANNER_SCOPE_PATTERN.search(text)
    if scope_match:
        text = f"{text[:scope_match.start()]} {text[scope_match.end():]}"

    section = None
    section_match = re.search(
        r"\b(?:в|во|на)\s+(?:стол(?:е)?|колонк(?:у|е)?|категори(?:ю|и)?|раздел(?:е)?)\s+"
        rf"(?P<section>[^,;:]+?)(?=\s+(?:на|в)\s+{SECTION_TAIL}\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if section_match:
        section = section_match.group("section").strip(" -") or None
        text = f"{text[:section_match.start()]} {text[section_match.end():]}"
    return text.strip(" ,:"), scope, section


def parse_command(value: str, today: date | None = None) -> ParsedCommand:
    raw = str(value or "").strip()
    command = normalize_command_text(strip_wake_word(raw))
    raw_command = strip_wake_word(raw).strip().lower()
    raw_command_preserved = strip_wake_word(raw).strip()
    current = today or date.today()
    if not command:
        return ParsedCommand("unknown", raw)
    remember_match = re.match(r"^(?:запомни|сохрани)\s+(?:пожалуйста\s+)?(?:что\s+)?(.+)$", command)
    if remember_match:
        return ParsedCommand("remember_fact", raw, target=remember_match.group(1).strip())
    forget_match = re.match(r"^(?:забудь|удали\s+из\s+памяти)\s+(?:пожалуйста\s+)?(?:что\s+)?(.+)$", command)
    if forget_match:
        return ParsedCommand("forget_fact", raw, target=forget_match.group(1).strip())
    if re.search(r"(?:что|какие\s+факты).*(?:помнишь|знаешь).*(?:обо\s+мне|про\s+меня)", command):
        return ParsedCommand("list_memories", raw)
    savings_summary = re.search(r"(?:сколько|покажи|расскажи|что).*(?:сбереж|накоп|сейф)", command)
    if savings_summary:
        category_match = re.search(r"\b(?:в|на)\s+(?:категори(?:и|ю|е)?\s+)?(.+?)\s*$", command)
        if category_match is None:
            category_match = re.search(r"\bкатегори(?:я|ю|и|е)\s+(.+?)\s*$", command)
        category = category_match.group(1).strip() if category_match else ""
        return ParsedCommand("savings_summary", raw, category=category)
    savings_deposit = re.match(
        r"^(?:пополни|добавь|положи|отложи)\s+(?:(?:в|на)\s+)?(?:сбережения\s+)?(.+?)(?:\s+(?:на|сумму)\s+|\s+)([\d\s.,]+)\s*(?:руб(?:лей|ля)?|₽)?$",
        command,
    )
    if savings_deposit:
        return ParsedCommand("savings_deposit", raw, category=savings_deposit.group(1).strip(), amount_text=savings_deposit.group(2).strip())
    savings_withdrawal = re.match(
        r"^(?:сними|выведи|забери)\s+(?:(?:из|с)\s+)?(?:сбережения\s+)?(.+?)(?:\s+(?:на|сумму)\s+|\s+)([\d\s.,]+)\s*(?:руб(?:лей|ля)?|₽)?$",
        command,
    )
    if savings_withdrawal:
        return ParsedCommand("savings_withdrawal", raw, category=savings_withdrawal.group(1).strip(), amount_text=savings_withdrawal.group(2).strip())
    finance_transaction = re.match(
        r"^(?:добавь|запиши|внеси)\s+(расход|доход)\s+([\d\s.,]+)\s+(?:на\s+|за\s+|в\s+категори(?:ю|и)?\s+)?(.+)$",
        command,
    )
    if finance_transaction:
        return ParsedCommand(
            "finance_transaction",
            raw,
            amount_text=finance_transaction.group(2).strip(),
            category=finance_transaction.group(3).strip(),
            finance_kind="expense" if finance_transaction.group(1) == "расход" else "income",
        )
    finance_transaction_reverse = re.match(
        r"^(?:добавь|запиши|внеси)\s+(расход|доход)\s+(.+?)\s+(?:на|сумму)\s+([\d\s.,]+)$",
        command,
    )
    if finance_transaction_reverse:
        return ParsedCommand(
            "finance_transaction",
            raw,
            amount_text=finance_transaction_reverse.group(3).strip(),
            category=finance_transaction_reverse.group(2).strip(),
            finance_kind="expense" if finance_transaction_reverse.group(1) == "расход" else "income",
        )
    if re.search(r"(?:финанс|баланс|бюджет|расход|доход)", command) and re.search(r"(?:покажи|сколько|какой|итог|сводк)", command):
        return ParsedCommand("finance_summary", raw)
    volume_match = re.match(r"^(?:поставь|установи|сделай)\s+(?:громкость|звук)\s+(?:на\s+)?(\d{1,3})\s*(?:%|процент(?:а|ов)?)?$", command)
    if volume_match:
        return ParsedCommand("set_volume", raw, target=volume_match.group(1))
    volume_adjust = re.match(r"^(?:сделай\s+)?(?:звук|громкость)\s+(громче|тише)(?:\s+на\s+(\d{1,3}))?(?:\s*%)?$", command)
    if volume_adjust:
        step = int(volume_adjust.group(2) or 10)
        return ParsedCommand("adjust_volume", raw, target=str(step if volume_adjust.group(1) == "громче" else -step))
    volume_adjust_verb = re.match(r"^(увеличь|прибавь|повысь|уменьши|убавь|понизь)\s+(?:громкость|звук)(?:\s+на\s+(\d{1,3}))?(?:\s*%)?$", command)
    if volume_adjust_verb:
        step = int(volume_adjust_verb.group(2) or 10)
        return ParsedCommand("adjust_volume", raw, target=str(step if volume_adjust_verb.group(1) in {"увеличь", "прибавь", "повысь"} else -step))
    if re.match(r"^(?:выключи|отключи|заглуши)\s+(?:звук|микрофон)$", command):
        return ParsedCommand("mute_audio", raw, target="on")
    if re.match(r"^(?:включи|верни)\s+(?:звук|аудио)$", command):
        return ParsedCommand("mute_audio", raw, target="off")
    brightness_match = re.match(r"^(?:поставь|установи|сделай)\s+яркость\s+(?:на\s+)?(\d{1,3})\s*(?:%|процент(?:а|ов)?)?$", command)
    if brightness_match:
        return ParsedCommand("set_brightness", raw, target=brightness_match.group(1))
    brightness_adjust = re.match(r"^(увеличь|прибавь|повысь|уменьши|убавь|понизь)\s+яркость(?:\s+на\s+(\d{1,3}))?(?:\s*%)?$", command)
    if brightness_adjust:
        step = int(brightness_adjust.group(2) or 10)
        return ParsedCommand("adjust_brightness", raw, target=str(step if brightness_adjust.group(1) in {"увеличь", "прибавь", "повысь"} else -step))
    if re.search(r"\b(?:сверни|минимизируй)\s+(?:текущее\s+)?окно\b", command):
        return ParsedCommand("minimize_window", raw)
    if re.search(r"\b(?:статус|состояние)\s+(?:вайфай|wi[- ]?fi|wifi)\b", command):
        return ParsedCommand("wifi_status", raw)
    if re.search(r"\b(?:включи|подключи)\s+(?:вайфай|wi[- ]?fi|wifi)\b", command):
        return ParsedCommand("toggle_wifi", raw, target="on")
    if re.search(r"\b(?:выключи|отключи)\s+(?:вайфай|wi[- ]?fi|wifi)\b", command):
        return ParsedCommand("toggle_wifi", raw, target="off")
    if re.search(r"\b(?:закрой)\s+(?:текущее\s+)?окно\b", command):
        return ParsedCommand("close_window", raw)
    if re.search(r"\b(?:выключи|заверши работу|выключение)\b.*(?:компьютер|мак|mac)", command):
        return ParsedCommand("shutdown", raw)
    if re.search(r"\b(?:перезагрузи|перезапусти)\b.*(?:компьютер|мак|mac)", command):
        return ParsedCommand("restart", raw)
    delete_match = re.match(r"^(?:удали|удалить)\s+(?:файл\s+|документ\s+)(.+)$", raw_command_preserved, flags=re.IGNORECASE)
    if delete_match:
        return ParsedCommand("delete_file", raw, target=delete_match.group(1).strip())
    if re.search(r"(?:коммунал|квартир|сч[её]т)", command) and re.search(r"(?:сколько|покажи|долг|оплат|итог)", command):
        return ParsedCommand("utilities_summary", raw)
    meter_match = re.match(
        r"^(?:внеси|добавь|запиши)\s+(?:показани(?:я|е)\s+)?(.+?)\s+([\d\s.,]+)(?:\s+(?:для|в)\s+(.+))?$",
        command,
    )
    if meter_match and "показ" in command:
        return ParsedCommand("meter_reading", raw, service=meter_match.group(1).strip(), value_text=meter_match.group(2).strip(), account=(meter_match.group(3) or "").strip())
    if re.match(r"^(?:отметь|пометь).*(?:показани|счетчик).*(?:подан|передан|готов)", command):
        return ParsedCommand("meter_submission", raw)
    explorer_match = re.match(
        r"^(?:открой|запусти|покажи)\s+(?:проводник|файлы|finder|файндер)"
        r"(?:\s+(?:в|на)\s+(.+))?$",
        command,
    )
    if explorer_match:
        return ParsedCommand("open_explorer", raw, target=external_target(explorer_match.group(1)))
    folder_match = re.match(r"^(?:открой|покажи)\s+(?:папку|каталог)\s+(.+)$", command)
    if folder_match:
        return ParsedCommand("open_explorer", raw, target=external_target(folder_match.group(1)))
    named_browser = re.match(r"^(?:открой|запусти)\s+(.+?)\s+браузер$", command)
    if named_browser and _browser_from_text(named_browser.group(1)):
        return ParsedCommand("open_browser", raw, browser=_browser_from_text(named_browser.group(1)))
    if re.match(r"^(?:открой|запусти)\s+(?:браузер|интернет)$", command):
        return ParsedCommand("open_browser", raw)
    web_command, requested_browser = _extract_browser_suffix(raw_command)
    url_match = re.match(
        r"^(?:открой|перейди|зайди)\s+(?:на\s+)?(?:сайт\s+)?(https?://[^\s]+|www\.[^\s]+|[a-z0-9а-яё-]+\.[a-zа-яё]{2,}(?:/[^\s]*)?)$",
        web_command,
    )
    if url_match:
        target = url_target(url_match.group(1))
        if not re.match(r"^https?://", target, flags=re.IGNORECASE):
            target = f"https://{target}"
        return ParsedCommand("open_url", raw, target=target, browser=requested_browser)
    normalized_web_command, _normalized_browser = _extract_browser_suffix(command)
    site_match = re.match(r"^(?:открой|перейди|зайди)\s+(?:на\s+)?(?:сайт\s+)?(.+)$", normalized_web_command)
    if site_match:
        requested_site = site_match.group(1).strip()
        site_key = requested_site if requested_site in KNOWN_SITES else ""
        if not site_key:
            close_sites = get_close_matches(requested_site, KNOWN_SITES, n=1, cutoff=0.72)
            site_key = close_sites[0] if close_sites else ""
        if site_key:
            return ParsedCommand("open_url", raw, target=KNOWN_SITES[site_key], browser=requested_browser)
    engine_match = re.match(r"^(?:найди|поищи)\s+(?:в\s+)?(яндексе|яндекс|yandex|гугле|гугл|google|бинге|бинг|bing)\s+(.+)$", normalized_web_command)
    if engine_match:
        return ParsedCommand("search_web", raw, target=engine_match.group(2).strip(), browser=requested_browser, search_engine=SEARCH_ENGINE_ALIASES[engine_match.group(1)])
    search_match = re.match(r"^(?:найди|поищи)\s+(?:в\s+интернете\s+)?(.+)$", normalized_web_command)
    if search_match:
        return ParsedCommand("search_web", raw, target=search_match.group(1).strip(), browser=requested_browser)
    weather_match = re.match(r"^(?:(?:скажи|покажи|узнай)\s+)?(?:какая|какой|что\s+с)?\s*погод(?:а|ой|у)(.*)$", normalized_web_command)
    if weather_match:
        place = re.sub(r"^(?:сейчас\s+)?(?:в|для)\s+", "", weather_match.group(1).strip())
        return ParsedCommand("weather", raw, target=place or "Москва")
    terminal_match = re.match(r"^(?:выполни(?:\s+команду)?|терминал(?:\s+выполни)?)\s+(.+)$", command)
    if terminal_match:
        return ParsedCommand("run_terminal", raw, target=terminal_match.group(1).strip())
    download_match = re.match(r"^(?:скачай|загрузи)\s+(?:файл\s+)?(https://[^\s]+)$", raw_command_preserved, flags=re.IGNORECASE)
    if download_match:
        return ParsedCommand("download_file", raw, target=url_target(download_match.group(1)))
    installer_match = re.match(
        r"^(?:запусти|открой|установи)\s+(?:(?:скачанный|загруженный)\s+)?(?:установщик|файл)?\s*(.+\.(?:exe|msi)|последний\s+(?:файл|установщик))$",
        raw_command_preserved,
        flags=re.IGNORECASE,
    )
    if installer_match:
        return ParsedCommand("run_installer", raw, target=installer_match.group(1).strip())
    file_create_match = re.match(
        r"^(?:создай|сделай)\s+файл\s+(?P<path>.+?)(?:\s+с\s+текстом\s+(?P<content>.+)|$)",
        raw_command_preserved,
        flags=re.IGNORECASE,
    )
    if file_create_match:
        return ParsedCommand(
            "create_file",
            raw,
            target=file_create_match.group("path").strip(),
            content=(file_create_match.group("content") or "").strip(),
        )
    folder_create_match = re.match(r"^(?:создай|сделай)\s+папку\s+(.+)$", raw_command_preserved, flags=re.IGNORECASE)
    if folder_create_match:
        return ParsedCommand("create_folder", raw, target=folder_create_match.group(1).strip())
    app_match = re.match(r"^(?:открой|запусти)\s+(.+)$", command)
    if app_match and not re.search(r"\b(?:планер|недел|папк|файл|проводник|браузер|интернет)\b", command):
        return ParsedCommand("open_application", raw, target=app_match.group(1).strip())
    if re.match(r"^(?:открой|перейди|покажи).*(?:планер|недельн|недел)", command):
        requested = week_date_from_text(command, current) or current
        return ParsedCommand("open_planner", raw, task_date=iso_day(requested))
    if re.search(r"\b(?:открой|перейди|покажи)\b.*\b(?:следующ(?:ую|ей)|прошл(?:ую|ой)|предыдущ(?:ую|ей)|эту|текущ(?:ую|ей))\s+недел", command):
        requested = week_date_from_text(command, current) or current
        return ParsedCommand("open_planner", raw, task_date=iso_day(requested))
    if re.match(r"^(?:покажи|расскажи|что|какие|сколько).*(?:план|задач|сегодня|завтра|послезавтра)", command) or re.search(r"план\s+на\s+", command):
        requested = date_from_text(command, current) or current
        return ParsedCommand("list_day", raw, task_date=iso_day(requested))
    add_match = re.match(r"^(?:добавь|создай|запиши|запланируй)\s+(?:задачу\s*)?(.+)$", command)
    if add_match:
        task_input, scope, section = extract_task_destination(add_match.group(1))
        text, task_date, start_time = schedule_from_text(task_input, current)
        return ParsedCommand(
            "create_task",
            raw,
            task_text=text,
            task_date=task_date,
            start_time=start_time,
            scope=scope,
            section=section,
        )
    move_match = re.match(r"^(?:перенеси|передвинь|измени\s+дату)\s+(?:задачу\s+)?(.+?)\s+(?:на|в)\s+(.+)$", command)
    if move_match:
        task_date = date_from_text(move_match.group(2), current)
        if task_date:
            return ParsedCommand(
                "reschedule_task",
                raw,
                query=move_match.group(1).strip(),
                task_date=iso_day(task_date),
                scope=command_scope(command),
            )
    complete_match = re.match(r"^(?:отметь|заверши|выполни)\s+(?:задачу\s+)?(.*)$", command)
    if complete_match:
        query = re.sub(r"^(?:как\s+)?(?:выполненной|выполненным|выполнено|сделанной|готовой)$", "", complete_match.group(1)).strip()
        query = re.sub(r"\s+(?:как\s+)?(?:выполненной|выполненным|выполнено|сделанной|готовой)$", "", query).strip()
        if normalize_text(query) in {"", "задачу", "эту задачу", "ее", "её"}:
            query = ""
        return ParsedCommand("complete_task", raw, query=query, scope=command_scope(command))
    return ParsedCommand("unknown", raw)
