"""User-defined phrases expand once into checked commands or AI requests."""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from eve_assistant import normalize_text, parse_command, strip_wake_word

SCHEMA = """
CREATE TABLE IF NOT EXISTS assistant_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phrase TEXT NOT NULL,
    normalized_phrase TEXT NOT NULL UNIQUE,
    template TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('command','prompt')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
"""

SUPPORTED_INTENTS = {
    "list_day", "open_planner", "create_task", "complete_task", "reschedule_task",
    "finance_summary", "finance_transaction", "utilities_summary", "meter_reading",
    "meter_submission", "remember_fact", "forget_fact", "list_memories",
    "open_browser", "open_url", "search_web", "open_explorer", "open_application",
    "create_folder", "create_file", "weather", "set_volume", "mute_audio",
}
RESERVED = {"да", "нет", "отмена", "подтверждаю", "подтвердить", "подтверждаю действие", "отменяю", "не надо", "стоп разговор", "заверши разговор", "хватит слушать", "останови разговор"}

CATALOG = [
    {"category": "Планирование", "text": "покажи план на сегодня", "description": "Посмотреть задачи дня", "requires_ai": False},
    {"category": "Планирование", "text": "открой планер на завтра", "description": "Перейти к планеру", "requires_ai": False},
    {"category": "Задачи", "text": "добавь задачу купить молоко на завтра в 19:30", "description": "Создать задачу", "requires_ai": False},
    {"category": "Задачи", "text": "отметь задачу купить молоко выполненной", "description": "Завершить задачу по названию", "requires_ai": False},
    {"category": "Задачи", "text": "перенеси задачу купить молоко на завтра", "description": "Перенести задачу", "requires_ai": False},
    {"category": "Финансы", "text": "покажи финансы", "description": "Получить финансовую сводку", "requires_ai": False},
    {"category": "Коммуналка", "text": "покажи коммуналку", "description": "Посмотреть коммунальные платежи", "requires_ai": False},
    {"category": "Память", "text": "запомни что я люблю прогулки вечером", "description": "Сохранить предпочтение", "requires_ai": False},
    {"category": "Память", "text": "что ты помнишь обо мне", "description": "Посмотреть сохранённые факты", "requires_ai": False},
    {"category": "Компьютер", "text": "открой браузер", "description": "Открыть браузер", "requires_ai": False},
    {"category": "Компьютер", "text": "открой проводник в загрузки", "description": "Открыть папку загрузок", "requires_ai": False},
    {"category": "Компьютер", "text": "найди в интернете прогноз погоды", "description": "Выполнить поиск", "requires_ai": False},
    {"category": "С помощью ИИ", "text": "Помоги спланировать завтра по моим задачам и привычкам", "description": "Составить план по данным приложения", "requires_ai": True},
    {"category": "С помощью ИИ", "text": "Предложи перенос незавершённых дел на завтра", "description": "Подготовить пакет изменений с подтверждением", "requires_ai": True},
    {"category": "С помощью ИИ", "text": "На что ушло больше всего денег в этом месяце?", "description": "Разобрать расходы", "requires_ai": True},
]


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Заполни поле «{field}» (до {maximum} символов).")
    return value.strip()


def validate_definition(data: Any) -> dict:
    if not isinstance(data, dict) or set(data) - {"name", "phrase", "template", "mode", "enabled"}:
        raise ValueError("Некорректный формат своей команды.")
    name = _text(data.get("name"), "Название", 60)
    phrase = _text(data.get("phrase"), "Фраза", 80)
    if not re.fullmatch(r"[\w -]+", phrase) or len(phrase) < 2 or strip_wake_word(phrase) != phrase:
        raise ValueError("Фраза должна состоять из букв, цифр, пробелов и дефисов, без имени «Эва» в начале.")
    normalized = normalize_text(phrase)
    if normalized in RESERVED or parse_command(phrase).intent != "unknown":
        raise ValueError("Эта фраза уже используется EVE. Выбери свою, например «Старт дня».")
    template = _text(data.get("template"), "Действие", 500)
    if template.count("{text}") > 1 or re.search(r"[{}]", template.replace("{text}", "")):
        raise ValueError("Можно использовать один параметр {text} для текста после фразы.")
    mode = data.get("mode", "command")
    if mode not in ("command", "prompt"):
        raise ValueError("Выбери обычную команду или запрос к ИИ.")
    enabled = data.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("enabled должен быть true или false.")
    if mode == "command" and parse_command(template.replace("{text}", "пример")).intent not in SUPPORTED_INTENTS:
        raise ValueError("Действие не распознано как основная команда. Используй пример из каталога или выбери запрос к ИИ.")
    return {"name": name, "phrase": phrase, "normalized_phrase": normalized, "template": template, "mode": mode, "enabled": int(enabled)}


def list_commands(db) -> list[dict]:
    result = []
    for row in db.execute("SELECT id,name,phrase,template,mode,enabled FROM assistant_commands ORDER BY id"):
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        result.append(item)
    return result


def save_command(db, data, command_id=None) -> dict:
    item = validate_definition(data)
    try:
        db.execute("BEGIN IMMEDIATE")
        if command_id is None and db.execute("SELECT COUNT(*) FROM assistant_commands").fetchone()[0] >= 100:
            raise ValueError("Можно сохранить до 100 своих команд.")
        if command_id is None:
            cursor = db.execute("INSERT INTO assistant_commands(name,phrase,normalized_phrase,template,mode,enabled) VALUES(:name,:phrase,:normalized_phrase,:template,:mode,:enabled)", item)
            command_id = cursor.lastrowid
        else:
            cursor = db.execute("UPDATE assistant_commands SET name=:name,phrase=:phrase,normalized_phrase=:normalized_phrase,template=:template,mode=:mode,enabled=:enabled WHERE id=:id", {**item, "id": command_id})
            if cursor.rowcount == 0:
                raise ValueError("Своя команда не найдена.")
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise ValueError("Команда с такой фразой уже существует.") from exc
    except Exception:
        db.rollback()
        raise
    return next(item for item in list_commands(db) if item["id"] == command_id)


def import_commands(db, data) -> int:
    if not isinstance(data, dict) or set(data) != {"version", "commands"} or type(data.get("version")) is not int or data["version"] != 1 or not isinstance(data.get("commands"), list):
        raise ValueError("Нужен файл команд EVE версии 1.")
    definitions = data["commands"]
    if len(definitions) > 100:
        raise ValueError("В файле должно быть не больше 100 команд.")
    items = [validate_definition(item) for item in definitions]
    phrases = [item["normalized_phrase"] for item in items]
    if len(set(phrases)) != len(phrases):
        raise ValueError("В файле повторяются фразы команд.")
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM assistant_commands").fetchone()[0] + len(items) > 100:
            raise ValueError("Всего можно сохранить до 100 своих команд.")
        db.executemany("INSERT INTO assistant_commands(name,phrase,normalized_phrase,template,mode,enabled) VALUES(:name,:phrase,:normalized_phrase,:template,:mode,:enabled)", items)
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise ValueError("Одна из фраз уже существует. Импорт отменён целиком.") from exc
    except Exception:
        db.rollback()
        raise
    return len(items)


def resolve_command(db, text: str) -> dict | None:
    spoken = strip_wake_word(text).strip()
    for row in db.execute("SELECT * FROM assistant_commands WHERE enabled=1 ORDER BY length(normalized_phrase) DESC,id"):
        phrase = row["normalized_phrase"]
        argument = ""
        if "{text}" in row["template"]:
            pattern = r"^" + r"\s+".join(re.escape(word) for word in phrase.split()) + r"(?=\s|$)[\s,]*"
            match = re.match(pattern, spoken, flags=re.IGNORECASE)
            if not match:
                continue
            argument = spoken[match.end():].strip()
            if not argument:
                raise ValueError("Добавь текст после своей фразы, например: «Быстрое дело купить молоко».")
        elif normalize_text(spoken) != phrase:
            continue
        expanded = row["template"].replace("{text}", argument)
        if len(expanded) > 500:
            raise ValueError("Получившаяся команда длиннее 500 символов. Сократи текст.")
        if row["mode"] == "command":
            expected = parse_command(row["template"].replace("{text}", "пример")).intent
            if parse_command(expanded).intent != expected:
                raise ValueError("Текст изменил тип действия. Уточни свою команду.")
        return {"text": expanded, "mode": row["mode"], "name": row["name"]}
    return None
