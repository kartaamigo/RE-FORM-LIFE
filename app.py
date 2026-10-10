from __future__ import annotations

import os
import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, redirect, render_template, request, url_for

from eve_agent import configure_autostart, input_devices, native_agent_status, perform_external_action, transcribe_pcm
from eve_assistant import choose_command_candidate, has_wake_word, normalize_text, parse_command, strip_wake_word
from eve_local import (
    DEFAULT_GEMINI_MODEL,
    LocalProviderError,
    available_tts_voices,
    build_profile,
    generate_gemini_reply,
    providers_status,
    resolve_gemini_model,
    synthesize_speech,
    tts_status,
)
from eve_speechkit import VOICES as YANDEX_VOICES, speechkit_status, synthesize_speechkit, transcribe_speechkit
from eve_harness import SCHEMA as HARNESS_SCHEMA, ConfirmationRequired, EveHarness, confirm_proposal, pending_proposal, relevant_memories, tool_declarations
from eve_commands import SCHEMA as COMMAND_SCHEMA, CATALOG as COMMAND_CATALOG, import_commands, list_commands, resolve_command, save_command


APP_NAME = "RE:FORM LIFE"
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

MOOD_LABELS = {
    1: "Тяжело",
    2: "Не очень",
    3: "Спокойно",
    4: "Хорошо",
    5: "Отлично",
}

DEFAULT_ASSISTANT_SETTINGS = {
    "enabled": "1",
    "auto_start": "1",
    "wake_word": "эва",
    "voice_lang": "ru-RU",
    "voice_name": "",
    "microphone_device": "",
    "speech_provider": "local",
    "yandex_voice": "alena",
    "gemini_enabled": "1",
    "local_tts_enabled": "1",
    "gemini_model": DEFAULT_GEMINI_MODEL,
    "continuous_dialog": "1",
    "interrupt_responses": "0",
    "personalization_enabled": "1",
}

ASSISTANT_WAKE_WORDS = {"эва", "ева", "eve"}
GEMINI_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,120}$")
RETIRED_GEMINI_MODELS = {"gemini-2.5-flash-lite"}
assistant_pending_actions: dict[str, dict[str, Any]] = {}
_recent_voice_commands: dict[str, float] = {}
_recent_voice_commands_lock = threading.Lock()
_assistant_harness_lock = threading.Lock()
_VOICE_COMMAND_SOURCES = {"local_voice", "browser_voice", "background"}
_VOICE_DEDUPE_SECONDS = 3.0


def is_duplicate_voice_command(text: str, source: str) -> bool:
    """Collapse the same microphone command arriving from two EVE listeners."""
    if source not in _VOICE_COMMAND_SOURCES:
        return False
    key = normalize_text(strip_wake_word(text))
    if not key:
        return False
    now = time.monotonic()
    with _recent_voice_commands_lock:
        expired = [item for item, timestamp in _recent_voice_commands.items() if now - timestamp >= _VOICE_DEDUPE_SECONDS]
        for item in expired:
            _recent_voice_commands.pop(item, None)
        previous = _recent_voice_commands.get(key)
        _recent_voice_commands[key] = now
    return previous is not None and now - previous < _VOICE_DEDUPE_SECONDS

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def default_data_dir() -> Path:
    """Return a writable, stable directory for user data in source and frozen builds."""
    configured = os.environ.get("REFORM_LIFE_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(local_app_data or (Path.home() / "AppData" / "Local")) / "RE-FORM LIFE"
    return Path(app.instance_path)


app.config["DATABASE"] = os.environ.get(
    "REFORM_LIFE_DB", str(default_data_dir() / "reform_life.sqlite3")
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_date TEXT NOT NULL,
    text TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT 'Личное',
    scope TEXT NOT NULL DEFAULT 'planner',
    start_time TEXT,
    end_time TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date);

CREATE TABLE IF NOT EXISTS weekly_goals (
    week_monday TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    note_date TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color TEXT NOT NULL DEFAULT '#4D67FF',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monthly_priorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    text TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monthly_priorities_month ON monthly_priorities(month, sort_order, id);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    category TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);

CREATE TABLE IF NOT EXISTS utility_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    account_number TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utility_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    billing_month TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'paid')) DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    paid_at TEXT,
    paid_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, billing_month)
);
CREATE INDEX IF NOT EXISTS idx_utility_payments_month ON utility_payments(billing_month);

CREATE TABLE IF NOT EXISTS utility_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, name)
);
CREATE INDEX IF NOT EXISTS idx_utility_services_account ON utility_services(account_id, archived, id);

CREATE TABLE IF NOT EXISTS utility_meter_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES utility_services(id) ON DELETE CASCADE,
    reading_value REAL NOT NULL CHECK (reading_value >= 0),
    reading_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(service_id, reading_date)
);
CREATE INDEX IF NOT EXISTS idx_utility_meter_readings_service ON utility_meter_readings(service_id, reading_date DESC);

CREATE TABLE IF NOT EXISTS utility_meter_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    submission_month TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    UNIQUE(account_id, submission_month)
);

CREATE TABLE IF NOT EXISTS utility_payment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES utility_payments(id) ON DELETE CASCADE,
    service_id INTEGER REFERENCES utility_services(id) ON DELETE SET NULL,
    service_name TEXT NOT NULL,
    tariff_minor INTEGER,
    previous_reading REAL,
    current_reading REAL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_utility_payment_items_payment ON utility_payment_items(payment_id, id);

CREATE TABLE IF NOT EXISTS utility_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    goal_minor INTEGER NOT NULL DEFAULT 0 CHECK (goal_minor >= 0),
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES savings_categories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('initial', 'deposit', 'withdrawal')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    operation_date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_savings_operations_category ON savings_operations(category_id, operation_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS savings_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL UNIQUE REFERENCES savings_categories(id) ON DELETE CASCADE,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly')) DEFAULT 'daily',
    schedule_days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
    target_per_week INTEGER NOT NULL DEFAULT 7,
    color TEXT NOT NULL DEFAULT '#ff2290',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS habit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    entry_date TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    UNIQUE(habit_id, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_habit_entries_date ON habit_entries(entry_date);

CREATE TABLE IF NOT EXISTS mood_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL UNIQUE,
    score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
    label TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_entries_date ON mood_entries(entry_date);

CREATE TABLE IF NOT EXISTS assistant_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_history_id ON assistant_history(id);

CREATE TABLE IF NOT EXISTS assistant_chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_chat_history_id ON assistant_chat_history(id);

CREATE TABLE IF NOT EXISTS assistant_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    normalized_fact TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def maybe_send_utility_reminder_notification(
    db: sqlite3.Connection,
    reminders: list[dict[str, Any]],
    settings: dict[str, str],
) -> bool:
    """Send one native reminder per day after the configured local time.

    The banner is always returned by the API. Native notifications are best
    effort: macOS uses its built-in Notification Center, while the browser UI
    provides a Notification API fallback on platforms without a native bridge.
    """
    if not reminders or not parse_bool(settings.get("notifications_enabled", "1")):
        return False
    configured_time = settings.get("reminder_time", "09:00")
    try:
        reminder_minutes = int(configured_time[:2]) * 60 + int(configured_time[3:])
    except (TypeError, ValueError):
        reminder_minutes = 9 * 60
    current = datetime.now()
    if current.hour * 60 + current.minute < reminder_minutes:
        return False
    notification_day = current.date().isoformat()
    if settings.get("last_meter_notification") == notification_day:
        return False
    names = ", ".join(str(item.get("account_name") or "квартира") for item in reminders[:4])
    if len(reminders) > 4:
        names += f" и ещё {len(reminders) - 4}"
    title = "RE:FORM LIFE · Показания"
    message = f"Пора передать показания: {names}."
    sent = False
    if sys.platform == "darwin":
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        try:
            completed = subprocess.run(
                ["osascript", "-e", f'display notification "{safe_message}" with title "{safe_title}"'],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            sent = completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            sent = False
    if sent:
        timestamp = now_iso()
        db.execute(
            "INSERT INTO utility_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            ("last_meter_notification", notification_day, timestamp),
        )
        db.commit()
    return sent


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = Path(app.config["DATABASE"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.executescript(SCHEMA)
        conn.executescript(HARNESS_SCHEMA)
        conn.executescript(COMMAND_SCHEMA)
        ensure_legacy_columns(conn)
        seed_sections(conn)
        ensure_assistant_settings(conn)
        ensure_utility_settings(conn)
        seed_savings_categories(conn)
        seed_utility_services(conn)
        g.db = conn
    return g.db


def ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    """Bring databases created by the first version up to the current schema."""
    migrations = (
        ("tasks", "section", "TEXT NOT NULL DEFAULT 'Личное'"),
        ("tasks", "scope", "TEXT NOT NULL DEFAULT 'planner'"),
        ("notes", "pinned", "INTEGER NOT NULL DEFAULT 0"),
        ("utility_accounts", "address", "TEXT NOT NULL DEFAULT ''"),
        ("utility_payments", "paid_date", "TEXT"),
    )
    for table, column, definition in migrations:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_scope_date ON tasks(scope, task_date)")
    conn.commit()


def seed_sections(conn: sqlite3.Connection) -> None:
    defaults = (
        ("Личное", "#F13785"),
        ("Учёба", "#9954EE"),
        ("Здоровье", "#42D187"),
    )
    timestamp = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO sections(name,color,created_at,updated_at) VALUES(?,?,?,?)",
        [(name, color, timestamp, timestamp) for name, color in defaults],
    )
    conn.commit()


def ensure_assistant_settings(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO assistant_settings(key,value,updated_at) VALUES(?,?,?)",
        [(key, value, timestamp) for key, value in DEFAULT_ASSISTANT_SETTINGS.items()],
    )
    conn.commit()


def ensure_utility_settings(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO utility_settings(key,value,updated_at) VALUES(?,?,?)",
        [("reminder_time", "09:00", timestamp), ("notifications_enabled", "1", timestamp)],
    )
    conn.commit()


def seed_savings_categories(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO savings_categories(name,goal_minor,archived,created_at,updated_at) VALUES(?,?,?,?,?)",
        [(name, 0, 0, timestamp, timestamp) for name in ("Личное", "За квартиру", "За парковку")],
    )
    conn.commit()


def seed_utility_services(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    accounts = conn.execute("SELECT id FROM utility_accounts WHERE archived=0").fetchall()
    defaults = (("Электричество", "кВт·ч"), ("Холодная вода", "м³"), ("Горячая вода", "м³"), ("Газ", "м³"))
    conn.executemany(
        "INSERT OR IGNORE INTO utility_services(account_id,name,unit,created_at,updated_at) VALUES(?,?,?,?,?)",
        [(account["id"], name, unit, timestamp, timestamp) for account in accounts for name, unit in defaults],
    )
    conn.commit()


@app.teardown_appcontext
def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def record_assistant_message(role: str, text: Any) -> None:
    if role not in {"user", "assistant"}:
        return
    message = str(text or "").strip()
    if not message:
        return
    db = get_db()
    db.execute(
        "INSERT INTO assistant_history(role,text,created_at) VALUES(?,?,?)",
        (role, message, now_iso()),
    )
    db.execute(
        "DELETE FROM assistant_history WHERE id NOT IN "
        "(SELECT id FROM assistant_history ORDER BY id DESC LIMIT 2000)"
    )
    db.commit()


def record_assistant_chat_message(role: str, text: Any) -> None:
    if role not in {"user", "assistant"}:
        return
    message = str(text or "").strip()
    if not message:
        return
    db = get_db()
    db.execute(
        "INSERT INTO assistant_chat_history(role,text,created_at) VALUES(?,?,?)",
        (role, message, now_iso()),
    )
    db.execute(
        "DELETE FROM assistant_chat_history WHERE id NOT IN "
        "(SELECT id FROM assistant_chat_history ORDER BY id DESC LIMIT 2000)"
    )
    db.commit()


def assistant_memories() -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id,fact,created_at,updated_at FROM assistant_memories ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def find_assistant_memory(value: str) -> dict[str, Any] | None:
    requested = normalize_text(value)
    memories = assistant_memories()
    if not requested or not memories:
        return None
    for memory in memories:
        normalized = normalize_text(memory["fact"])
        if requested == normalized or requested in normalized or normalized in requested:
            return memory
    ranked = sorted(
        memories,
        key=lambda item: SequenceMatcher(None, requested, normalize_text(item["fact"])).ratio(),
        reverse=True,
    )
    if ranked and SequenceMatcher(None, requested, normalize_text(ranked[0]["fact"])).ratio() >= 0.68:
        return ranked[0]
    return None


@app.after_request
def persist_assistant_exchange(response):
    """Persist every chat exchange independently of the UI lifecycle."""
    if request.path != "/api/assistant/command":
        return response
    command_text = getattr(g, "assistant_command_text", "")
    if not command_text:
        return response
    try:
        payload = response.get_json(silent=True) or {}
        record_assistant_message("user", command_text)
        if isinstance(payload, dict):
            record_assistant_message("assistant", payload.get("reply") or payload.get("error"))
    except (sqlite3.Error, OSError):
        app.logger.exception("Не удалось сохранить историю EVE")
    return response


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_dict(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def require_text(value: Any, label: str, max_length: int = 180) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Заполните поле «{label}».")
    if len(text) > max_length:
        raise ValueError(f"Поле «{label}» слишком длинное.")
    return text


def optional_text(value: Any, max_length: int = 180) -> str:
    return str(value or "").strip()[:max_length]


def validate_date(value: Any, label: str = "Дата") -> str:
    text = str(value or "").strip()
    if not DATE_RE.match(text):
        raise ValueError(f"Некорректное значение поля «{label}».")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Некорректное значение поля «{label}».") from exc
    return text


def validate_month(value: Any, label: str = "Месяц") -> str:
    text = str(value or "").strip()
    if not MONTH_RE.match(text):
        raise ValueError(f"Некорректное значение поля «{label}».")
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"Некорректное значение поля «{label}».") from exc
    return text


def validate_time(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not TIME_RE.match(text):
        raise ValueError(f"Некорректное время в поле «{label}».")
    return text


def parse_amount(value: Any) -> int:
    if isinstance(value, int):
        amount = value
    else:
        normalized = str(value or "").replace(" ", "").replace(",", ".")
        try:
            amount = round(float(normalized) * 100)
        except ValueError as exc:
            raise ValueError("Введите корректную сумму.") from exc
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля.")
    return int(amount)


def parse_bool(value: Any) -> int:
    return 1 if value in (True, 1, "1", "true", "True", "on") else 0


def parse_progress(value: Any, label: str = "Процент выполнения") -> int:
    try:
        progress = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Некорректное значение поля «{label}».") from exc
    if not 0 <= progress <= 100:
        raise ValueError(f"Поле «{label}» должно быть от 0 до 100.")
    return progress


def parse_mood_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Выберите настроение от 1 до 5.") from exc
    if score not in MOOD_LABELS:
        raise ValueError("Выберите настроение от 1 до 5.")
    return score


def validate_color(value: Any, default: str = "#4D67FF") -> str:
    color = str(value or default).strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
        raise ValueError("Выберите цвет в формате #RRGGBB.")
    return color.upper()


def section_name(value: Any, fallback: str = "Личное") -> str:
    name = optional_text(value, 48) or fallback
    requested = normalize_text(name).replace("ё", "е")
    rows = get_db().execute(
        "SELECT name FROM sections WHERE archived = 0 ORDER BY id"
    ).fetchall()
    for row in rows:
        candidate = normalize_text(row["name"]).replace("ё", "е")
        if candidate == requested:
            return row["name"]
    raise ValueError("Выберите существующий раздел.")


def serialize_task(row: dict[str, Any]) -> dict[str, Any]:
    row["done"] = bool(row["done"])
    row["scope"] = row.get("scope") or "planner"
    return row


def task_scope(value: Any, fallback: str = "planner") -> str:
    scope = str(value or fallback).strip().lower()
    if scope not in {"planner", "tasks"}:
        raise ValueError("Некорректный раздел хранения задачи.")
    return scope


def serialize_transaction(row: dict[str, Any]) -> dict[str, Any]:
    row["amount_minor"] = int(row["amount_minor"])
    return row


def serialize_payment(row: dict[str, Any]) -> dict[str, Any]:
    row["amount_minor"] = int(row["amount_minor"])
    if row["status"] == "pending" and row["due_date"] < date.today().isoformat():
        row["status"] = "overdue"
    return row


def parse_decimal(value: Any, label: str = "Показание") -> float:
    try:
        parsed = float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Введите корректное значение поля «{label}».") from exc
    if parsed < 0:
        raise ValueError(f"Поле «{label}» не может быть отрицательным.")
    return round(parsed, 3)


def serialize_savings_category(row: dict[str, Any]) -> dict[str, Any]:
    row["goal_minor"] = int(row.get("goal_minor") or 0)
    row["balance_minor"] = int(row.get("balance_minor") or 0)
    row["archived"] = bool(row.get("archived"))
    row["planned_amount_minor"] = int(row.get("planned_amount_minor") or 0)
    row["plan_enabled"] = bool(row.get("plan_enabled"))
    return row


def serialize_savings_operation(row: dict[str, Any]) -> dict[str, Any]:
    row["amount_minor"] = int(row["amount_minor"])
    return row


def serialize_utility_service(row: dict[str, Any]) -> dict[str, Any]:
    row["archived"] = bool(row.get("archived"))
    return row


def serialize_meter_reading(row: dict[str, Any]) -> dict[str, Any]:
    row["reading_value"] = float(row["reading_value"])
    return row


def utility_payment_items(payment_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT * FROM utility_payment_items WHERE payment_id=? ORDER BY id",
        (payment_id,),
    ).fetchall()
    result = rows_dict(rows)
    for item in result:
        if item.get("tariff_minor") is not None:
            item["tariff_minor"] = int(item["tariff_minor"])
        item["amount_minor"] = int(item["amount_minor"])
    return result


def serialize_mood(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row["score"] = int(row["score"])
    row["label"] = MOOD_LABELS.get(row["score"], row.get("label") or "")
    return row


def assistant_settings_payload() -> dict[str, Any]:
    rows = get_db().execute("SELECT key,value FROM assistant_settings").fetchall()
    raw = {row["key"]: row["value"] for row in rows}
    boolean_keys = {
        "enabled", "auto_start", "gemini_enabled", "local_tts_enabled",
        "continuous_dialog", "interrupt_responses", "personalization_enabled",
    }
    result: dict[str, Any] = {}
    for key, default in DEFAULT_ASSISTANT_SETTINGS.items():
        value = raw.get(key, default)
        if key in boolean_keys:
            result[key] = bool(parse_bool(value))
        elif key == "gemini_model":
            environment_model = os.environ.get("GEMINI_MODEL", "").strip()
            saved_model = resolve_gemini_model(value or default)
            if environment_model in RETIRED_GEMINI_MODELS:
                environment_model = resolve_gemini_model(environment_model)
            result[key] = environment_model if GEMINI_MODEL_RE.fullmatch(environment_model) else saved_model
        elif key == "voice_name":
            allowed_voices = {voice["id"] for voice in available_tts_voices()}
            result[key] = value if value in allowed_voices else available_tts_voices()[0]["id"]
        elif key == "yandex_voice":
            result[key] = value if value in {voice["id"] for voice in YANDEX_VOICES} else "alena"
        else:
            result[key] = value
    return result


def assistant_date_label(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def assistant_task_word(value: int) -> str:
    number = abs(int(value)) % 100
    last = number % 10
    if 11 <= number <= 19 or last == 0 or 5 <= last <= 9:
        return "задач"
    if 2 <= last <= 4:
        return "задачи"
    return "задача"


def current_weather(place: str) -> str:
    """Fetch a compact current-weather answer suitable for spoken playback."""
    location = require_text(place, "Город", 100)
    url = "https://wttr.in/" + urllib.parse.quote(location) + "?format=j1&lang=ru"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = payload["current_condition"][0]
        description_items = current.get("lang_ru") or current.get("weatherDesc") or []
        description = str(description_items[0].get("value", "") if description_items else "").lower()
        weather_words = {
            "sunny": "солнечно", "clear": "ясно", "partly cloudy": "переменная облачность",
            "cloudy": "облачно", "overcast": "пасмурно", "mist": "дымка", "fog": "туман",
            "smog": "смог", "light rain": "небольшой дождь", "rain": "дождь",
            "light snow": "небольшой снег", "snow": "снег", "thunder": "гроза",
        }
        description = weather_words.get(description, description)
        temperature = int(current.get("temp_C"))
        feels = int(current.get("FeelsLikeC", temperature))
        wind = int(current.get("windspeedKmph", 0))
        feel_text = f", ощущается как {feels:+d}" if feels != temperature else ""
        wind_text = f" Ветер {wind} километров в час." if wind else ""
        return f"Сейчас в городе {location}: {temperature:+d} градусов{feel_text}, {description or 'без уточнения условий'}.{wind_text}"
    except (KeyError, IndexError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise ValueError("Не удалось получить актуальную погоду. Проверь интернет и попробуй ещё раз.") from exc


def find_assistant_task(query: str, scope: str = "planner") -> dict[str, Any] | None:
    normalized_query = normalize_text(query)
    selected_scope = task_scope(scope)
    if normalized_query:
        rows = get_db().execute(
            "SELECT * FROM tasks WHERE done=0 ORDER BY CASE WHEN scope=? THEN 0 ELSE 1 END, task_date, start_time IS NULL, start_time, id",
            (selected_scope,),
        ).fetchall()
    else:
        rows = get_db().execute(
            "SELECT * FROM tasks WHERE scope=? AND done=0 ORDER BY task_date, start_time IS NULL, start_time, id",
            (selected_scope,),
        ).fetchall()
    candidates = [serialize_task(row_dict(row)) for row in rows]
    if not normalized_query:
        return candidates[0] if len(candidates) == 1 else None
    exact = [task for task in candidates if normalize_text(task["text"]) == normalized_query]
    if exact:
        return exact[0] if len(exact) == 1 else None
    matches = [task for task in candidates if normalized_query in normalize_text(task["text"]) or normalize_text(task["text"]) in normalized_query]
    return matches[0] if len(matches) == 1 else None


def find_savings_category_by_text(value: str) -> sqlite3.Row | None:
    requested = normalize_text(value).replace("ё", "е").strip(" .,:;!?-")
    requested = re.sub(r"^(?:категори(?:я|ю|и|е)\s+)", "", requested)
    aliases = {
        "личном": "личное",
        "личного": "личное",
        "личную": "личное",
        "квартиру": "за квартиру",
        "квартире": "за квартиру",
        "квартиры": "за квартиру",
        "парковке": "за парковку",
        "парковки": "за парковку",
        "парковку": "за парковку",
    }
    requested = aliases.get(requested, requested)
    if not requested:
        categories = [item for item in savings_categories_query(False)]
        return get_db().execute("SELECT * FROM savings_categories WHERE archived=0 ORDER BY id LIMIT 1").fetchone() if len(categories) == 1 else None
    rows = get_db().execute("SELECT * FROM savings_categories WHERE archived=0 ORDER BY id").fetchall()
    for row in rows:
        name = normalize_text(row["name"]).replace("ё", "е")
        if requested == name or requested in name or name in requested:
            return row
    return None


def savings_amount_from_text(value: str) -> int:
    text = normalize_text(value).replace("рублей", "").replace("рубля", "").replace("руб", "").replace("₽", "").strip()
    thousand = re.match(r"^(\d+(?:[.,]\d+)?)\s*(?:тысяч(?:а|и)?|к|к)$", text)
    if thousand:
        return parse_amount(float(thousand.group(1)) * 1000)
    return parse_amount(text)


def find_utility_account_by_text(value: str) -> sqlite3.Row | None:
    requested = normalize_text(value).replace("ё", "е").strip(" .,:;!?-")
    rows = get_db().execute("SELECT * FROM utility_accounts WHERE archived=0 ORDER BY id").fetchall()
    if not requested:
        return rows[0] if len(rows) == 1 else None
    for row in rows:
        haystack = " ".join(
            normalize_text(row[key]).replace("ё", "е")
            for key in ("name", "address")
            if row[key]
        )
        if requested in haystack or haystack in requested:
            return row
    return None


def find_utility_service_by_text(account_id: int, value: str) -> sqlite3.Row | None:
    requested = normalize_text(value).replace("ё", "е").strip(" .,:;!?-")
    rows = get_db().execute(
        "SELECT * FROM utility_services WHERE account_id=? AND archived=0 ORDER BY id",
        (account_id,),
    ).fetchall()
    if not requested:
        return rows[0] if len(rows) == 1 else None
    for row in rows:
        name = normalize_text(row["name"]).replace("ё", "е")
        if requested == name or requested in name or name in requested:
            return row
    return None


def confirmed_action_path(value: str) -> Path:
    requested = Path(str(value or "").strip()).expanduser()
    home = Path.home().resolve()
    if not requested.is_absolute() and len(requested.parts) == 1:
        requested = Path("Desktop") / requested
    if not requested.is_absolute() and requested.parts and requested.parts[0] in {"Desktop", "Documents"}:
        usual = home / requested.parts[0]
        synced = home / "OneDrive" / requested.parts[0]
        if not usual.is_dir() and synced.is_dir():
            requested = Path("OneDrive") / requested
    path = (home / requested if not requested.is_absolute() else requested).resolve()
    try:
        path.relative_to(home)
    except ValueError as exc:
        raise ValueError("Для создания файла или папки укажи путь внутри домашней папки пользователя.") from exc
    return path


def execute_pending_action(pending: dict[str, Any]) -> dict[str, Any]:
    kind = pending.get("kind")
    if kind == "create_folder":
        path = confirmed_action_path(str(pending.get("target") or ""))
        if path.exists():
            raise ValueError("Папка с таким именем уже существует. Я не стала менять её.")
        path.mkdir(parents=True, exist_ok=True)
        return {"action": "create_folder", "reply": f"Папка создана: {path.name}.", "path": str(path)}
    if kind == "create_file":
        path = confirmed_action_path(str(pending.get("target") or ""))
        if path.exists():
            raise ValueError("Такой файл уже существует. Я не стала его перезаписывать.")
        if not path.name or path.suffix == "":
            path = path.with_suffix(".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(pending.get("content") or "")[:5000]
        path.write_text(content, encoding="utf-8")
        return {"action": "create_file", "reply": f"Файл создан: {path.name}.", "path": str(path)}
    if kind == "download_file":
        url = str(pending.get("target") or "").strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("EVE скачивает файлы только по прямым защищённым HTTPS-ссылкам.")
        name = Path(urllib.parse.unquote(parsed.path)).name
        if not name or name in {".", ".."}:
            raise ValueError("В ссылке не указано имя файла.")
        destination = (Path.home() / "Downloads" / name).resolve()
        if destination.exists():
            raise ValueError("Файл с таким именем уже есть в папке «Загрузки». Я не стала его перезаписывать.")
        request_object = urllib.request.Request(url, headers={"User-Agent": "RE-FORM-LIFE-EVE/1.0"})
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(request_object, timeout=30) as source, destination.open("xb") as output:
                total = 0
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 500 * 1024 * 1024:
                        raise ValueError("Файл больше 500 МБ. Загрузка отменена.")
                    output.write(chunk)
        except Exception:
            if destination.exists():
                destination.unlink()
            raise
        return {"action": "download_file", "reply": f"Скачала файл «{name}» в Загрузки. Перед запуском проверь издателя и подпись.", "path": str(destination)}
    if kind == "run_installer":
        downloads = (Path.home() / "Downloads").resolve()
        requested = str(pending.get("target") or "").strip()
        candidates = [item for item in downloads.iterdir() if item.is_file() and item.suffix.lower() in {".exe", ".msi"}]
        if normalize_text(requested).startswith("последний"):
            path = max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None
        else:
            path = next((item for item in candidates if item.name.casefold() == Path(requested).name.casefold()), None)
        if path is None:
            raise ValueError("Не нашла такой установщик в папке «Загрузки».")
        if path.suffix.lower() == ".msi":
            subprocess.Popen(["msiexec.exe", "/i", str(path)], stdin=subprocess.DEVNULL)
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
        return {"action": "run_installer", "reply": f"Запустила «{path.name}» без повышения прав. Проверь издателя в окне установки.", "path": str(path)}
    if kind == "run_terminal":
        raise ValueError("EVE не исполняет произвольные команды терминала или скрипты.")
    if kind in {"toggle_wifi", "close_window", "shutdown", "restart", "delete_file"}:
        result = perform_external_action(kind, str(pending.get("target") or ""))
        return {"action": kind, **result, "reply": result.get("reply", "Действие выполнено.")}
    if kind == "savings_operation":
        category_id = int(pending["category_id"])
        operation_kind = str(pending["operation_kind"])
        amount_minor = int(pending["amount_minor"])
        if operation_kind == "withdrawal" and amount_minor > savings_balance(category_id):
            raise ValueError("Пока ждало подтверждение, доступный остаток изменился. Снятие отменено.")
        db = get_db()
        timestamp = now_iso()
        cursor = db.execute(
            "INSERT INTO savings_operations(category_id,kind,amount_minor,operation_date,comment,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (category_id, operation_kind, amount_minor, date.today().isoformat(), pending.get("comment", "Изменение через EVE"), timestamp, timestamp),
        )
        db.commit()
        category = db.execute("SELECT name FROM savings_categories WHERE id=?", (category_id,)).fetchone()
        verb = "пополнила" if operation_kind in {"deposit", "initial"} else "сняла"
        return {"action": "savings_operation", "operation_id": cursor.lastrowid, "reply": f"Готово. Я {verb} {amount_minor / 100:g} ₽ в категории «{category['name']}»."}
    raise ValueError("Подтверждённое действие больше не поддерживается.")


def assistant_day_summary(task_rows: list[dict[str, Any]], task_date: str) -> str:
    if not task_rows:
        return f"{assistant_date_label(task_date)} свободен. Задач нет."
    preview = ". ".join(
        f"{index}. {task['text']}{' — выполнено' if task['done'] else ''}"
        for index, task in enumerate(task_rows[:5], start=1)
    )
    open_count = sum(1 for task in task_rows if not task["done"])
    done_count = len(task_rows) - open_count
    tail = f" Выполнено {done_count}, осталось {open_count}." if open_count else " Выполнено всё."
    return f"План на {assistant_date_label(task_date)}: {len(task_rows)} {assistant_task_word(len(task_rows))}. {preview}.{tail}"


def mood_summary(rows: list[sqlite3.Row], start: str, end: str) -> dict[str, Any]:
    entries = [serialize_mood(item) for item in rows_dict(rows)]
    scores = [item["score"] for item in entries]
    average = round(sum(scores) / len(scores), 2) if scores else None
    average_score = min(5, max(1, int(average + 0.5))) if average is not None else None
    planner = get_db().execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM tasks WHERE scope='planner' AND task_date BETWEEN ? AND ?",
        (start, end),
    ).fetchone()
    return {
        "entries": entries,
        "average": average,
        "average_score": average_score,
        "label": MOOD_LABELS.get(average_score) if average_score else "Пока нет отметок",
        "planner_total": int(planner["total"]),
        "planner_done": int(planner["done"]),
    }


@app.context_processor
def inject_app_name():
    return {"app_name": APP_NAME}


@app.route("/")
def index():
    return redirect(url_for("page_week"))


@app.route("/week")
def page_week():
    return render_template("week.html", page_key="week", page_title="Недельный планер", page_subtitle="Задачи и фокус на каждый день")


@app.route("/tasks")
def page_tasks():
    return render_template("tasks.html", page_key="tasks", page_title="Задачи", page_subtitle="Все задачи в одном месте")


@app.route("/assistant")
def page_assistant():
    return render_template("assistant.html", page_key="assistant", page_title="EVE · AI-чат", page_subtitle="AI-чат, голосовой помощник и управление задачами в одном месте")


@app.route("/month")
def page_month():
    return render_template("month.html", page_key="month", page_title="Месячный планер", page_subtitle="Обзор задач на месяц")


@app.route("/finance")
def page_finance():
    return render_template("finance.html", page_key="finance", page_title="Финансы", page_subtitle="Доходы, расходы и баланс")


@app.route("/utilities")
def page_utilities():
    return render_template("utilities.html", page_key="utilities", page_title="Коммуналка", page_subtitle="Счета и сроки оплаты")


@app.route("/habits")
def page_habits():
    return render_template("habits.html", page_key="habits", page_title="Привычки", page_subtitle="Ритм, серии и ежедневные отметки")


@app.get("/api/health")
def api_health():
    get_db().execute("SELECT 1")
    return jsonify({"ok": True, "app": APP_NAME})


@app.get("/api/assistant/status")
def api_assistant_status():
    native = native_agent_status()
    settings = assistant_settings_payload()
    providers = providers_status(settings["gemini_model"])
    gemini = providers["gemini"]
    tts = providers["tts"]
    return jsonify({
        "ok": True,
        "assistant": {
            "name": "EVE",
            "display_name": "EVE · Эва",
            "wake_words": sorted(ASSISTANT_WAKE_WORDS),
            "enabled": settings["enabled"],
            "auto_start": settings["auto_start"],
            "native": native,
            "microphones": input_devices(),
            "voice": settings["voice_lang"],
            "voice_name": settings["voice_name"],
            "voices": tts.get("voices", []),
            "build_profile": build_profile(),
            "speechkit": speechkit_status(),
            "gemini": {
                **gemini,
                "enabled": settings["gemini_enabled"],
                "model": settings["gemini_model"],
            },
            "tts": {
                **tts,
                "tts_enabled": settings["local_tts_enabled"],
            },
        },
    })


@app.post("/api/assistant/tts")
def api_assistant_tts():
    try:
        settings = assistant_settings_payload()
        if not settings["local_tts_enabled"]:
            return json_error("Голос выключен в настройках EVE.", 503)
        data = body()
        text = require_text(data.get("text"), "Текст", 2000)
        if settings["speech_provider"] == "yandex":
            requested_voice = optional_text(data.get("voice"), 80) or settings["yandex_voice"]
            audio = synthesize_speechkit(text, requested_voice)
            backend = "yandex-speechkit"
        else:
            requested_voice = optional_text(data.get("voice"), 80) or settings["voice_name"]
            allowed_voices = {voice["id"] for voice in available_tts_voices()}
            if requested_voice not in allowed_voices:
                return json_error("Этот голос недоступен в выбранном профиле сборки.")
            audio = synthesize_speech(text, requested_voice)
            backend = str(tts_status().get("backend", "local"))
    except LocalProviderError as exc:
        return json_error(str(exc), 503)
    except ValueError as exc:
        return json_error(str(exc))
    response = Response(audio, mimetype="audio/wav")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-EVE-TTS"] = backend
    return response


@app.post("/api/assistant/transcribe")
def api_assistant_transcribe():
    try:
        sample_rate = int(request.args.get("sample_rate", "16000"))
        if sample_rate != 16000:
            return json_error("EVE ожидает запись с частотой 16 кГц.")
        settings = assistant_settings_payload()
        payload = request.get_data(cache=False)
        text = transcribe_speechkit(payload, sample_rate) if settings["speech_provider"] == "yandex" else transcribe_pcm(payload, sample_rate)
        return jsonify({"ok": True, "text": text})
    except (OSError, RuntimeError, ValueError, LocalProviderError) as exc:
        return json_error(str(exc), 503)


@app.get("/api/assistant/settings")
def api_assistant_settings_get():
    return jsonify({"ok": True, "settings": assistant_settings_payload()})


@app.patch("/api/assistant/settings")
def api_assistant_settings_patch():
    data = body()
    allowed = set(DEFAULT_ASSISTANT_SETTINGS)
    unknown = set(data) - allowed
    if unknown:
        return json_error(f"Неизвестные настройки EVE: {', '.join(sorted(unknown))}.")
    try:
        values: dict[str, str] = {}
        for key, value in data.items():
            if key in {
                "enabled", "auto_start", "gemini_enabled", "local_tts_enabled",
                "continuous_dialog", "interrupt_responses", "personalization_enabled",
            }:
                values[key] = "1" if parse_bool(value) else "0"
            elif key == "speech_provider":
                provider = str(value or "").strip().lower()
                if provider not in {"local", "yandex"}:
                    raise ValueError("Выбери локальный голос или Yandex SpeechKit.")
                values[key] = provider
            elif key == "yandex_voice":
                voice = str(value or "").strip().lower()
                if voice not in {item["id"] for item in YANDEX_VOICES}:
                    raise ValueError("Этот голос SpeechKit недоступен.")
                values[key] = voice
            elif key == "voice_name":
                voice_name = str(value or "").strip().lower()
                if voice_name not in {voice["id"] for voice in available_tts_voices()}:
                    raise ValueError("Этот голос недоступен в выбранном профиле сборки.")
                values[key] = voice_name
            elif key == "wake_word":
                wake_word = normalize_text(value)
                if wake_word not in ASSISTANT_WAKE_WORDS:
                    raise ValueError("Ключевое слово должно быть «Эва», «Ева» или «EVE».")
                values[key] = wake_word
            elif key == "voice_lang":
                voice_lang = optional_text(value, 20) or "ru-RU"
                if not re.match(r"^[a-z]{2}(?:-[A-Z]{2})?$", voice_lang):
                    raise ValueError("Некорректный язык голоса.")
                values[key] = voice_lang
            elif key == "microphone_device":
                microphone = optional_text(value, 120)
                available = {item["id"] for item in input_devices()}
                if microphone and microphone not in available:
                    raise ValueError("Выбранный микрофон больше недоступен.")
                values[key] = microphone
            elif key == "gemini_model":
                model = optional_text(value, 120) or DEFAULT_GEMINI_MODEL
                if not GEMINI_MODEL_RE.fullmatch(model):
                    raise ValueError("Некорректное имя модели Gemini.")
                values[key] = resolve_gemini_model(model)
            else:
                values[key] = optional_text(value, 80)
        db = get_db()
        db.executemany(
            "INSERT INTO assistant_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            [(key, value, now_iso()) for key, value in values.items()],
        )
        db.commit()
        autostart = None
        if "auto_start" in values:
            try:
                autostart = configure_autostart(values["auto_start"] == "1")
            except Exception as exc:  # platform setup must not break the planner
                autostart = {"supported": False, "enabled": values["auto_start"] == "1", "message": str(exc)}
        return jsonify({"ok": True, "settings": assistant_settings_payload(), "autostart": autostart})
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/assistant/history")
def api_assistant_history_get():
    try:
        limit = max(1, min(2000, int(request.args.get("limit", 40))))
    except (TypeError, ValueError):
        limit = 40
    rows = get_db().execute(
        "SELECT id,role,text,created_at FROM assistant_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return jsonify({"ok": True, "messages": [row_dict(row) for row in reversed(rows)]})


@app.delete("/api/assistant/history")
def api_assistant_history_delete():
    db = get_db()
    db.execute("DELETE FROM assistant_history")
    db.execute("UPDATE assistant_task_proposals SET status='cancelled' WHERE status='pending'")
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/assistant/chat/history")
def api_assistant_chat_history_get():
    try:
        limit = max(1, min(2000, int(request.args.get("limit", 80))))
    except (TypeError, ValueError):
        limit = 80
    rows = get_db().execute(
        "SELECT id,role,text,created_at FROM assistant_chat_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return jsonify({"ok": True, "messages": [row_dict(row) for row in reversed(rows)]})


@app.delete("/api/assistant/chat/history")
def api_assistant_chat_history_delete():
    db = get_db()
    db.execute("DELETE FROM assistant_chat_history")
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/assistant/chat")
def api_assistant_chat():
    """Conversation with read-only application tools; never changes data."""
    try:
        data = body()
        text = require_text(data.get("text"), "Сообщение", 1000)
        settings = assistant_settings_payload()
        rows = get_db().execute(
            "SELECT role,text FROM assistant_chat_history ORDER BY id DESC LIMIT 20"
        ).fetchall()
        history = [dict(row) for row in reversed(rows)]
        memories = [item["fact"] for item in assistant_memories()] if settings["personalization_enabled"] else []
        if not settings["gemini_enabled"]:
            return json_error("Разговорная модель Gemini выключена в настройках EVE.", 503)
        result = assistant_harness_reply(text, settings, history, memories, allow_changes=False)
        reply = result["reply"]
        provider = "gemini"
        record_assistant_chat_message("user", text)
        record_assistant_chat_message("assistant", reply)
        return jsonify({"ok": True, "action": "conversation_reply", "provider": provider, "reply": reply})
    except LocalProviderError as exc:
        return json_error(str(exc), 503)
    except ValueError as exc:
        return json_error(str(exc))


def assistant_harness_reply(text, settings, history, memories, *, allow_changes=True):
    if not _assistant_harness_lock.acquire(blocking=False):
        raise LocalProviderError("EVE ещё обрабатывает предыдущий запрос. Дождись ответа.")
    try:
        harness = EveHarness(get_db(), memories, allow_changes=allow_changes)
        reply = generate_gemini_reply(
            text, settings["gemini_model"], history, relevant_memories(text, memories),
            context=harness.context(), tools=tool_declarations(allow_changes), execute_tool=harness.execute,
        )
        return {"ok": True, "action": "gemini_reply", "provider": "gemini", "model": settings["gemini_model"], "reply": reply}
    except ConfirmationRequired as exc:
        return exc.payload
    finally:
        _assistant_harness_lock.release()


def assistant_harness_command(text):
    settings = assistant_settings_payload()
    if not settings["gemini_enabled"]:
        return jsonify({"ok": True, "action": "gemini_unavailable", "reply": "Разговорная модель Gemini выключена в настройках EVE. Простые команды остаются доступны."})
    rows = get_db().execute("SELECT role,text FROM assistant_history ORDER BY id DESC LIMIT 16").fetchall()
    history = [dict(row) for row in reversed(rows)]
    memories = [item["fact"] for item in assistant_memories()] if settings["personalization_enabled"] else []
    try:
        return jsonify(assistant_harness_reply(text, settings, history, memories))
    except LocalProviderError as exc:
        return jsonify({"ok": True, "action": "gemini_unavailable", "reply": f"Не смогла обработать запрос через Gemini. {exc} Можно использовать простую команду или повторить запрос."})


@app.get("/api/assistant/proposals/pending")
def api_assistant_pending_proposal():
    return jsonify({"ok": True, "proposal": pending_proposal(get_db())})


@app.get("/api/assistant/memories")
def api_assistant_memories_get():
    return jsonify({"ok": True, "memories": assistant_memories()})


@app.delete("/api/assistant/memories")
def api_assistant_memories_delete():
    db = get_db()
    db.execute("DELETE FROM assistant_memories")
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/assistant/command")
def api_assistant_command():
    try:
        data = body()
        text = require_text(data.get("text"), "Команда", 500)
        source = str(data.get("source") or "web").strip().lower()
        alternatives = data.get("alternatives")
        if source in {"local_voice", "browser_voice"}:
            voice_candidates = [text]
            if isinstance(alternatives, list):
                voice_candidates.extend(str(item or "").strip() for item in alternatives[:4])
            voice_candidates = [item for item in voice_candidates if item and has_wake_word(item)]
            if not voice_candidates:
                return jsonify({"ok": True, "action": "ignored", "reply": ""})
            text = choose_command_candidate(voice_candidates[0], voice_candidates[1:])
        else:
            text = choose_command_candidate(text, alternatives)
        if is_duplicate_voice_command(text, source):
            return jsonify({"ok": True, "action": "ignored", "reply": ""})
        g.assistant_command_text = text
        custom_command = resolve_command(get_db(), text)
        if custom_command is not None:
            text = custom_command["text"]
            if custom_command["mode"] == "prompt":
                return assistant_harness_command(text)
        parsed = parse_command(text)
        if parsed.intent == "missing_folder_name":
            return jsonify({
                "ok": True,
                "action": "missing_folder_name",
                "reply": "Как назвать папку? Скажи, например: «Создай папку с названием Дом».",
            })
        if parsed.intent == "run_terminal":
            return jsonify({
                "ok": True,
                "action": "unsupported",
                "reply": "Я не запускаю произвольные команды терминала и скрипты. Попроси открыть приложение, папку или сайт либо используй одну из поддерживаемых команд.",
            })
        confirmation_phrase = normalize_text(text)
        if not assistant_pending_actions and confirmation_phrase in {"да", "подтверждаю", "подтвердить", "подтверждаю действие", "нет", "отмена", "отменяю", "не надо"}:
            proposal = get_db().execute("SELECT id FROM assistant_task_proposals WHERE status='pending' AND created_at>? ORDER BY created_at DESC LIMIT 1", (time.time() - 600,)).fetchone()
            if proposal is not None:
                return jsonify(confirm_proposal(get_db(), proposal["id"], confirmation_phrase in {"да", "подтверждаю", "подтвердить", "подтверждаю действие"}))
        if confirmation_phrase in {"да", "подтверждаю", "подтвердить", "подтверждаю действие"} and assistant_pending_actions:
            confirmation_id, pending = max(
                assistant_pending_actions.items(),
                key=lambda item: float(item[1].get("created_at", 0)),
            )
            assistant_pending_actions.pop(confirmation_id, None)
            if datetime.now().timestamp() - float(pending.get("created_at", 0)) > 600:
                return json_error("Подтверждение истекло. Повтори команду.", 410)
            try:
                result = execute_pending_action(pending)
                return jsonify({"ok": True, "action": result.get("action", "confirmed"), **result, "reply": f"Подтверждено. {result.get('reply', 'Действие выполнено.')}"})
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                return json_error(str(exc))
        if confirmation_phrase in {"нет", "отмена", "отменяю", "не надо"} and assistant_pending_actions:
            confirmation_id, _pending = max(
                assistant_pending_actions.items(),
                key=lambda item: float(item[1].get("created_at", 0)),
            )
            assistant_pending_actions.pop(confirmation_id, None)
            return jsonify({"ok": True, "action": "cancelled", "reply": "Команда отменена."})
        if parsed.intent == "remember_fact":
            settings = assistant_settings_payload()
            if not settings["personalization_enabled"]:
                return jsonify({"ok": True, "action": "memory_disabled", "reply": "Персональная память выключена в настройках EVE."})
            fact = require_text(parsed.target, "Факт", 300)
            normalized = normalize_text(fact)
            timestamp = now_iso()
            db = get_db()
            db.execute(
                "INSERT INTO assistant_memories(fact,normalized_fact,created_at,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(normalized_fact) DO UPDATE SET fact=excluded.fact,updated_at=excluded.updated_at",
                (fact, normalized, timestamp, timestamp),
            )
            db.commit()
            return jsonify({"ok": True, "action": "remember_fact", "reply": f"Хорошо, запомнила: {fact}."})
        if parsed.intent == "forget_fact":
            memory = find_assistant_memory(parsed.target)
            if memory is None:
                return jsonify({"ok": True, "action": "memory_not_found", "reply": "Не нашла такого факта в своей памяти."})
            db = get_db()
            db.execute("DELETE FROM assistant_memories WHERE id=?", (memory["id"],))
            db.commit()
            return jsonify({"ok": True, "action": "forget_fact", "reply": f"Забыла: {memory['fact']}."})
        if parsed.intent == "list_memories":
            memories = assistant_memories()
            if not memories:
                return jsonify({"ok": True, "action": "list_memories", "memories": [], "reply": "Пока я не сохраняла фактов о тебе."})
            facts = "; ".join(item["fact"] for item in memories[-12:])
            return jsonify({"ok": True, "action": "list_memories", "memories": memories, "reply": f"Я помню: {facts}."})
        if parsed.intent == "weather":
            return jsonify({"ok": True, "action": "weather", "place": parsed.target, "reply": current_weather(parsed.target)})
        if parsed.intent in {"open_explorer", "open_browser", "open_application", "open_url", "search_web", "set_volume", "adjust_volume", "mute_audio", "set_brightness", "adjust_brightness", "minimize_window", "wifi_status"}:
            try:
                if parsed.intent in {"open_browser", "open_url", "search_web"}:
                    opened = perform_external_action(
                        parsed.intent,
                        parsed.target,
                        browser=parsed.browser,
                        search_engine=parsed.search_engine,
                    )
                else:
                    opened = perform_external_action(parsed.intent, parsed.target)
            except (OSError, ValueError) as exc:
                return json_error(str(exc))
            if opened.get("reply"):
                reply = opened["reply"]
            elif parsed.intent == "open_browser":
                reply = "Открываю браузер."
            elif parsed.intent == "open_url":
                reply = f"Открываю ссылку: {opened['path']}."
            elif parsed.intent == "search_web":
                reply = f"Ищу в интернете: «{parsed.target}»."
            elif parsed.intent == "open_application":
                reply = f"Открываю приложение «{opened['path']}»."
            else:
                labels = {
                    "home": "домашнюю папку",
                    "downloads": "Загрузки",
                    "desktop": "Рабочий стол",
                    "documents": "Документы",
                    "applications": "Приложения",
                }
                reply = f"Открываю Проводник: {labels.get(opened['location'], opened['location'])}."
            return jsonify({"ok": True, "action": parsed.intent, "target": opened["location"], "reply": reply})
        if parsed.intent in {"create_folder", "create_file", "download_file", "run_installer", "toggle_wifi", "close_window", "shutdown", "restart", "delete_file"}:
            confirmation_id = uuid.uuid4().hex
            assistant_pending_actions[confirmation_id] = {
                "kind": parsed.intent,
                "target": parsed.target,
                "content": parsed.content,
                "created_at": datetime.now().timestamp(),
            }
            labels = {
                "create_folder": f"создать папку «{parsed.target}»",
                "create_file": f"создать файл «{parsed.target}»",
                "download_file": f"скачать файл по адресу «{parsed.target}» в папку «Загрузки»",
                "run_installer": f"запустить установщик «{parsed.target}» из папки «Загрузки»",
                "toggle_wifi": f"{'включить' if parsed.target == 'on' else 'выключить'} Wi‑Fi",
                "close_window": "закрыть текущее окно",
                "shutdown": "выключить компьютер",
                "restart": "перезагрузить компьютер",
                "delete_file": f"удалить файл «{parsed.target}»",
            }
            label = labels[parsed.intent]
            return jsonify({
                "ok": True,
                "action": "needs_confirmation",
                "confirmation_id": confirmation_id,
                "confirmation_label": label,
                "reply": f"Готова {label}. Подтверди действие кнопкой и голосом.",
            })
        if parsed.intent == "savings_summary":
            category = find_savings_category_by_text(parsed.category)
            categories = savings_categories_query(False)
            if category is not None:
                selected = next(item for item in categories if item["id"] == category["id"])
                return jsonify({"ok": True, "action": "savings_summary", "categories": [selected], "reply": f"В сейфе «{selected['name']}» сейчас {selected['balance_minor'] / 100:g} ₽."})
            total = sum(item["balance_minor"] for item in categories)
            preview = ", ".join(f"{item['name']} — {item['balance_minor'] / 100:g} ₽" for item in categories)
            return jsonify({"ok": True, "action": "savings_summary", "categories": categories, "reply": f"Всего накоплено {total / 100:g} ₽. {preview}."})
        if parsed.intent in {"savings_deposit", "savings_withdrawal"}:
            category = find_savings_category_by_text(parsed.category)
            if category is None:
                return jsonify({"ok": True, "action": "not_found", "reply": "Не нашла такую категорию сейфа. Назови «Личное», «За квартиру» или «За парковку»."})
            amount_minor = savings_amount_from_text(parsed.amount_text)
            operation_kind = "deposit" if parsed.intent == "savings_deposit" else "withdrawal"
            if operation_kind == "withdrawal" and amount_minor > savings_balance(category["id"]):
                return json_error("Нельзя снять больше, чем накоплено в этой категории.")
            confirmation_id = uuid.uuid4().hex
            assistant_pending_actions[confirmation_id] = {
                "kind": "savings_operation",
                "category_id": category["id"],
                "operation_kind": operation_kind,
                "amount_minor": amount_minor,
                "created_at": datetime.now().timestamp(),
            }
            verb = "пополнить" if operation_kind == "deposit" else "снять"
            return jsonify({"ok": True, "action": "needs_confirmation", "confirmation_id": confirmation_id, "confirmation_label": f"{verb} {amount_minor / 100:g} ₽ в категории «{category['name']}»", "reply": f"Могу {verb} {amount_minor / 100:g} ₽ в категории «{category['name']}». Подтверди кнопкой и голосом."})
        if parsed.intent == "finance_summary":
            month = date.today().strftime("%Y-%m")
            rows = get_db().execute("SELECT kind, amount_minor FROM transactions WHERE transaction_date LIKE ?", (f"{month}%",)).fetchall()
            income = sum(int(row["amount_minor"]) for row in rows if row["kind"] == "income")
            expense = sum(int(row["amount_minor"]) for row in rows if row["kind"] == "expense")
            return jsonify({"ok": True, "action": "finance_summary", "income_minor": income, "expense_minor": expense, "balance_minor": income - expense, "reply": f"За текущий месяц доходы {income / 100:g} ₽, расходы {expense / 100:g} ₽. Баланс {((income - expense) / 100):g} ₽."})
        if parsed.intent == "finance_transaction":
            amount_minor = parse_amount(parsed.amount_text)
            category = require_text(parsed.category, "Категория", 80)
            kind = parsed.finance_kind if parsed.finance_kind in {"income", "expense"} else "expense"
            timestamp = now_iso()
            db = get_db()
            cursor = db.execute(
                "INSERT INTO transactions(kind,amount_minor,category,transaction_date,comment,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (kind, amount_minor, category, date.today().isoformat(), "Внесено через EVE", timestamp, timestamp),
            )
            db.commit()
            verb = "доход" if kind == "income" else "расход"
            return jsonify({"ok": True, "action": "finance_transaction", "transaction_id": cursor.lastrowid, "reply": f"Записала {verb} {amount_minor / 100:g} ₽ в категории «{category}»."}), 201
        if parsed.intent == "meter_reading":
            account = find_utility_account_by_text(parsed.account)
            if account is None:
                return jsonify({"ok": True, "action": "not_found", "reply": "Уточни квартиру для этого показания."})
            db = get_db()
            seed_utility_services(db)
            service = find_utility_service_by_text(account["id"], parsed.service)
            if service is None:
                return jsonify({"ok": True, "action": "not_found", "reply": f"Не нашла услугу «{parsed.service}» в квартире «{account['name']}»."})
            reading_value = parse_decimal(parsed.value_text)
            reading_date = date.today().isoformat()
            timestamp = now_iso()
            db.execute(
                "INSERT INTO utility_meter_readings(account_id,service_id,reading_value,reading_date,note,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(service_id,reading_date) DO UPDATE SET reading_value=excluded.reading_value, note=excluded.note, created_at=excluded.created_at",
                (account["id"], service["id"], reading_value, reading_date, "Внесено через EVE", timestamp),
            )
            db.commit()
            return jsonify({"ok": True, "action": "meter_reading", "reply": f"Записала показание «{service['name']}» для квартиры «{account['name']}»: {reading_value:g} {service['unit'] or ''}."})
        if parsed.intent == "utilities_summary":
            month = date.today().strftime("%Y-%m")
            rows = get_db().execute("SELECT * FROM utility_payments WHERE billing_month=?", (month,)).fetchall()
            payments = [serialize_payment(row_dict(row)) for row in rows]
            due = sum(item["amount_minor"] for item in payments if item["status"] != "paid")
            overdue = sum(item["amount_minor"] for item in payments if item["status"] == "overdue")
            return jsonify({"ok": True, "action": "utilities_summary", "reply": f"За текущий месяц к оплате {due / 100:g} ₽. Просрочено {overdue / 100:g} ₽."})
        if parsed.intent == "meter_submission":
            accounts = get_db().execute("SELECT id,name FROM utility_accounts WHERE archived=0 ORDER BY id").fetchall()
            if len(accounts) != 1:
                return jsonify({"ok": True, "action": "not_found", "reply": "Уточни, для какой квартиры показания уже поданы."})
            account_id = accounts[0]["id"]
            month = date.today().strftime("%Y-%m")
            db = get_db()
            db.execute("INSERT INTO utility_meter_submissions(account_id,submission_month,submitted_at) VALUES(?,?,?) ON CONFLICT(account_id,submission_month) DO UPDATE SET submitted_at=excluded.submitted_at", (account_id, month, now_iso()))
            db.commit()
            return jsonify({"ok": True, "action": "meter_submission", "reply": f"Отметила показания для квартиры «{accounts[0]['name']}» как поданные."})
        if parsed.intent == "open_planner":
            target_date = validate_date(parsed.task_date or date.today().isoformat())
            return jsonify({
                "ok": True,
                "action": "open_planner",
                "target": f"/week?date={target_date}",
                "date": target_date,
                "reply": f"Открываю недельный планер на неделю с {assistant_date_label(target_date)}.",
            })
        if parsed.intent == "list_day":
            task_date = validate_date(parsed.task_date or date.today().isoformat())
            rows = get_db().execute(
                "SELECT * FROM tasks WHERE scope='planner' AND task_date=? ORDER BY start_time IS NULL,start_time,id",
                (task_date,),
            ).fetchall()
            tasks = [serialize_task(row_dict(row)) for row in rows]
            return jsonify({"ok": True, "action": "list_day", "date": task_date, "tasks": tasks, "reply": assistant_day_summary(tasks, task_date)})
        if parsed.intent == "create_task":
            task_date = validate_date(parsed.task_date or date.today().isoformat())
            text_value = require_text(parsed.task_text, "Название")
            scope = task_scope(parsed.scope or data.get("scope"), "planner")
            section = section_name(parsed.section or data.get("section"), "Личное")
            timestamp = now_iso()
            db = get_db()
            cursor = db.execute(
                "INSERT INTO tasks(task_date,text,section,scope,start_time,end_time,done,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_date, text_value, section, scope, parsed.start_time, None, 0, timestamp, timestamp),
            )
            db.commit()
            row = db.execute("SELECT * FROM tasks WHERE id=?", (cursor.lastrowid,)).fetchone()
            task = serialize_task(row_dict(row))
            timing = f" в {parsed.start_time}" if parsed.start_time else ""
            board = "в раздел «Задачи»" if scope == "tasks" else "в недельный планер"
            return jsonify({
                "ok": True,
                "action": "create_task",
                "task": task,
                "reply": f"Добавила задачу «{text_value}» {board}, колонка «{section}», на {assistant_date_label(task_date)}{timing}.",
            }), 201
        if parsed.intent in {"complete_task", "reschedule_task"}:
            task = find_assistant_task(parsed.query, parsed.scope)
            if task is None:
                if assistant_settings_payload()["gemini_enabled"]:
                    return assistant_harness_command(text)
                return jsonify({"ok": True, "action": "not_found", "reply": "Не нашла такую активную задачу. Назови её точнее."})
            db = get_db()
            if parsed.intent == "complete_task":
                db.execute("UPDATE tasks SET done=1,updated_at=? WHERE id=?", (now_iso(), task["id"]))
                db.commit()
                return jsonify({"ok": True, "action": "complete_task", "task_id": task["id"], "reply": f"Готово. Задача «{task['text']}» отмечена выполненной."})
            task_date = validate_date(parsed.task_date or date.today().isoformat())
            db.execute("UPDATE tasks SET task_date=?,updated_at=? WHERE id=?", (task_date, now_iso(), task["id"]))
            db.commit()
            return jsonify({"ok": True, "action": "reschedule_task", "task_id": task["id"], "date": task_date, "reply": f"Перенесла задачу «{task['text']}» на {assistant_date_label(task_date)}."})
        if parsed.intent == "unknown":
            return assistant_harness_command(text)
        return jsonify({"ok": True, "action": "unsupported", "reply": "Я могу поддержать разговор, управлять задачами, финансами и коммуналкой, открыть папку или приложение из меню Пуск, сайт и поиск. Некоторые действия с компьютером попрошу подтвердить. Произвольные команды терминала и скрипты я не запускаю."})
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/assistant/commands")
def api_assistant_commands():
    return jsonify({"ok": True, "catalog": COMMAND_CATALOG, "commands": list_commands(get_db())})


@app.post("/api/assistant/commands")
def api_assistant_command_create():
    try:
        return jsonify({"ok": True, "command": save_command(get_db(), body())}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.patch("/api/assistant/commands/<int:command_id>")
def api_assistant_command_update(command_id):
    existing = next((item for item in list_commands(get_db()) if item["id"] == command_id), None)
    if existing is None:
        return json_error("Своя команда не найдена.", 404)
    try:
        fields = {key: value for key, value in existing.items() if key != "id"}
        fields.update(body())
        return jsonify({"ok": True, "command": save_command(get_db(), fields, command_id)})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/assistant/commands/<int:command_id>")
def api_assistant_command_delete(command_id):
    db = get_db()
    cursor = db.execute("DELETE FROM assistant_commands WHERE id=?", (command_id,))
    db.commit()
    return jsonify({"ok": True}) if cursor.rowcount else json_error("Своя команда не найдена.", 404)


@app.get("/api/assistant/commands/export")
def api_assistant_command_export():
    commands = [{key: value for key, value in item.items() if key != "id"} for item in list_commands(get_db())]
    return Response(json.dumps({"version": 1, "commands": commands}, ensure_ascii=False, indent=2), mimetype="application/json", headers={"Content-Disposition": 'attachment; filename="eve-commands.json"'})


@app.post("/api/assistant/commands/import")
def api_assistant_command_import():
    if request.content_length and request.content_length > 128000:
        return json_error("Файл команд слишком большой (максимум 128 КБ).", 413)
    try:
        count = import_commands(get_db(), body())
        return jsonify({"ok": True, "imported": count}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.post("/api/assistant/confirm")
def api_assistant_confirm():
    data = body()
    confirmation_id = optional_text(data.get("confirmation_id"), 80)
    pending = assistant_pending_actions.pop(confirmation_id, None)
    if pending is None:
        proposal = get_db().execute("SELECT id FROM assistant_task_proposals WHERE id=?", (confirmation_id,)).fetchone()
        if proposal is None:
            return json_error("Подтверждение не найдено или уже истекло.", 404)
        try:
            result = confirm_proposal(get_db(), confirmation_id, bool(parse_bool(data.get("approved"))))
            record_assistant_message("user", "Подтверждаю изменения задач." if parse_bool(data.get("approved")) else "Отменяю изменения задач.")
            record_assistant_message("assistant", result["reply"])
            return jsonify(result)
        except ValueError as exc:
            return json_error(str(exc), 409)
    if datetime.now().timestamp() - float(pending.get("created_at", 0)) > 600:
        return json_error("Подтверждение истекло. Повтори команду.", 410)
    if not parse_bool(data.get("approved")):
        return jsonify({"ok": True, "action": "cancelled", "reply": "Команда отменена."})
    try:
        result = execute_pending_action(pending)
        return jsonify({"ok": True, "action": result.get("action", "confirmed"), **result})
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return json_error(str(exc))


@app.get("/api/tasks")
def api_tasks_list():
    try:
        start = validate_date(request.args.get("start"), "Начало периода") if request.args.get("start") else "0000-01-01"
        end = validate_date(request.args.get("end"), "Конец периода") if request.args.get("end") else "9999-12-31"
        scope = request.args.get("scope")
        if scope not in (None, "", "all"):
            scope = task_scope(scope)
        query = "SELECT * FROM tasks WHERE task_date BETWEEN ? AND ?"
        params: list[Any] = [start, end]
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        query += " ORDER BY task_date, start_time IS NULL, start_time, id"
        rows = get_db().execute(
            query,
            tuple(params),
        ).fetchall()
        return jsonify({"ok": True, "tasks": [serialize_task(item) for item in rows_dict(rows)]})
    except ValueError as exc:
        return json_error(str(exc))


@app.post("/api/tasks")
def api_tasks_create():
    try:
        data = body()
        task_date = validate_date(data.get("task_date"))
        text = require_text(data.get("text"), "Название")
        section = section_name(data.get("section"))
        scope = task_scope(data.get("scope"), "planner")
        start_time = validate_time(data.get("start_time"), "Начало")
        end_time = validate_time(data.get("end_time"), "Окончание")
        if start_time and end_time and end_time < start_time:
            raise ValueError("Время окончания не может быть раньше времени начала.")
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO tasks (task_date,text,section,scope,start_time,end_time,done,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (task_date, text, section, scope, start_time, end_time, 0, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "task": serialize_task(row_dict(row))}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.patch("/api/tasks/<int:task_id>")
def api_tasks_update(task_id: int):
    data = body()
    db = get_db()
    current = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if current is None:
        return json_error("Задача не найдена.", 404)
    try:
        task_date = validate_date(data.get("task_date", current["task_date"]))
        text = require_text(data.get("text", current["text"]), "Название")
        section = section_name(data.get("section", current["section"]))
        scope = task_scope(data.get("scope", current["scope"]), "planner")
        start_time = validate_time(data.get("start_time", current["start_time"]), "Начало")
        end_time = validate_time(data.get("end_time", current["end_time"]), "Окончание")
        if start_time and end_time and end_time < start_time:
            raise ValueError("Время окончания не может быть раньше времени начала.")
        done = parse_bool(data.get("done", current["done"]))
        db.execute(
            "UPDATE tasks SET task_date=?,text=?,section=?,scope=?,start_time=?,end_time=?,done=?,updated_at=? WHERE id=?",
            (task_date, text, section, scope, start_time, end_time, done, now_iso(), task_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return jsonify({"ok": True, "task": serialize_task(row_dict(row))})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/tasks/<int:task_id>")
def api_tasks_delete(task_id: int):
    db = get_db()
    cursor = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Задача не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/notifications")
def api_notifications_list():
    today = date.today().isoformat()
    rows = get_db().execute(
        "SELECT * FROM tasks WHERE scope='planner' AND done=0 AND task_date < ? ORDER BY task_date, start_time IS NULL, start_time, id",
        (today,),
    ).fetchall()
    notifications = [serialize_task(item) for item in rows_dict(rows)]
    return jsonify({"ok": True, "count": len(notifications), "notifications": notifications})


@app.get("/api/mood/today")
def api_mood_today():
    row = get_db().execute(
        "SELECT * FROM mood_entries WHERE entry_date=?", (date.today().isoformat(),)
    ).fetchone()
    return jsonify({"ok": True, "entry": serialize_mood(row_dict(row))})


@app.get("/api/mood")
def api_mood_list():
    try:
        start = validate_date(request.args.get("start"), "Начало периода") if request.args.get("start") else "0000-01-01"
        end = validate_date(request.args.get("end"), "Конец периода") if request.args.get("end") else "9999-12-31"
        if end < start:
            raise ValueError("Конец периода не может быть раньше начала.")
        rows = get_db().execute(
            "SELECT * FROM mood_entries WHERE entry_date BETWEEN ? AND ? ORDER BY entry_date",
            (start, end),
        ).fetchall()
        return jsonify({"ok": True, **mood_summary(rows, start, end)})
    except ValueError as exc:
        return json_error(str(exc))


@app.put("/api/mood/<entry_date>")
def api_mood_put(entry_date: str):
    try:
        entry_date = validate_date(entry_date)
        data = body()
        score = parse_mood_score(data.get("score"))
        note = optional_text(data.get("note"), 240)
        timestamp = now_iso()
        db = get_db()
        db.execute(
            "INSERT INTO mood_entries(entry_date,score,label,note,created_at,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(entry_date) DO UPDATE SET score=excluded.score,label=excluded.label,note=excluded.note,updated_at=excluded.updated_at",
            (entry_date, score, MOOD_LABELS[score], note, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM mood_entries WHERE entry_date=?", (entry_date,)).fetchone()
        return jsonify({"ok": True, "entry": serialize_mood(row_dict(row))})
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/sections")
def api_sections_list():
    rows = get_db().execute(
        "SELECT * FROM sections WHERE archived = 0 ORDER BY id"
    ).fetchall()
    return jsonify({"ok": True, "sections": rows_dict(rows)})


@app.post("/api/sections")
def api_sections_create():
    try:
        data = body()
        name = require_text(data.get("name"), "Название раздела", 48)
        color = validate_color(data.get("color"))
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO sections(name,color,created_at,updated_at) VALUES(?,?,?,?)",
            (name, color, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM sections WHERE id=?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "section": row_dict(row)}), 201
    except sqlite3.IntegrityError:
        return json_error("Раздел с таким названием уже существует.")
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/month/priorities")
def api_month_priorities_list():
    try:
        month = validate_month(request.args.get("month"))
        rows = get_db().execute(
            "SELECT * FROM monthly_priorities WHERE month=? ORDER BY sort_order, id",
            (month,),
        ).fetchall()
        return jsonify({"ok": True, "priorities": rows_dict(rows)})
    except ValueError as exc:
        return json_error(str(exc))


@app.post("/api/month/priorities")
def api_month_priority_create():
    try:
        data = body()
        month = validate_month(data.get("month"))
        text = require_text(data.get("text"), "Приоритет", 180)
        progress = parse_progress(data.get("progress", 0))
        sort_order = max(0, int(data.get("sort_order", 0)))
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO monthly_priorities(month,text,progress,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (month, text, progress, sort_order, timestamp, timestamp),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM monthly_priorities WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
        return jsonify({"ok": True, "priority": row_dict(row)}), 201
    except (TypeError, ValueError) as exc:
        return json_error(str(exc))


@app.patch("/api/month/priorities/<int:priority_id>")
def api_month_priority_update(priority_id: int):
    db = get_db()
    current = db.execute(
        "SELECT * FROM monthly_priorities WHERE id=?", (priority_id,)
    ).fetchone()
    if current is None:
        return json_error("Приоритет не найден.", 404)
    try:
        data = body()
        month = validate_month(data.get("month", current["month"]))
        text = require_text(data.get("text", current["text"]), "Приоритет", 180)
        progress = parse_progress(data.get("progress", current["progress"]))
        sort_order = max(0, int(data.get("sort_order", current["sort_order"])))
        db.execute(
            "UPDATE monthly_priorities SET month=?,text=?,progress=?,sort_order=?,updated_at=? WHERE id=?",
            (month, text, progress, sort_order, now_iso(), priority_id),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM monthly_priorities WHERE id=?", (priority_id,)
        ).fetchone()
        return jsonify({"ok": True, "priority": row_dict(row)})
    except (TypeError, ValueError) as exc:
        return json_error(str(exc))


@app.delete("/api/month/priorities/<int:priority_id>")
def api_month_priority_delete(priority_id: int):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM monthly_priorities WHERE id=?", (priority_id,)
    )
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Приоритет не найден.", 404)
    return jsonify({"ok": True})


@app.get("/api/goals/<week_monday>")
def api_goal_get(week_monday: str):
    try:
        week_monday = validate_date(week_monday, "Неделя")
    except ValueError as exc:
        return json_error(str(exc))
    row = get_db().execute("SELECT * FROM weekly_goals WHERE week_monday = ?", (week_monday,)).fetchone()
    return jsonify({"ok": True, "goal": row_dict(row) or {"week_monday": week_monday, "text": ""}})


@app.put("/api/goals/<week_monday>")
def api_goal_put(week_monday: str):
    try:
        week_monday = validate_date(week_monday, "Неделя")
        text = optional_text(body().get("text"), 240)
        db = get_db()
        db.execute(
            "INSERT INTO weekly_goals(week_monday,text,updated_at) VALUES(?,?,?) ON CONFLICT(week_monday) DO UPDATE SET text=excluded.text,updated_at=excluded.updated_at",
            (week_monday, text, now_iso()),
        )
        db.commit()
        row = db.execute("SELECT * FROM weekly_goals WHERE week_monday = ?", (week_monday,)).fetchone()
        return jsonify({"ok": True, "goal": row_dict(row)})
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/notes")
def api_notes_list():
    rows = get_db().execute("SELECT * FROM notes ORDER BY pinned DESC, id DESC").fetchall()
    return jsonify({"ok": True, "notes": rows_dict(rows)})


@app.post("/api/notes")
def api_notes_create():
    try:
        data = body()
        text = require_text(data.get("text"), "Заметка", 240)
        note_date = validate_date(data.get("note_date") or date.today().isoformat())
        pinned = parse_bool(data.get("pinned", False))
        db = get_db()
        cursor = db.execute("INSERT INTO notes(text,note_date,pinned,created_at) VALUES(?,?,?,?)", (text, note_date, pinned, now_iso()))
        db.commit()
        row = db.execute("SELECT * FROM notes WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "note": row_dict(row)}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.patch("/api/notes/<int:note_id>")
def api_notes_update(note_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    if current is None:
        return json_error("Заметка не найдена.", 404)
    try:
        data = body()
        text = require_text(data.get("text", current["text"]), "Заметка", 240)
        note_date = validate_date(data.get("note_date", current["note_date"]))
        pinned = parse_bool(data.get("pinned", current["pinned"]))
        db.execute(
            "UPDATE notes SET text=?,note_date=?,pinned=? WHERE id=?",
            (text, note_date, pinned, note_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return jsonify({"ok": True, "note": row_dict(row)})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/notes/<int:note_id>")
def api_notes_delete(note_id: int):
    db = get_db()
    cursor = db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Заметка не найдена.", 404)
    return jsonify({"ok": True})


def finance_query(month: str | None):
    if month:
        validate_month(month)
        return get_db().execute(
            "SELECT * FROM transactions WHERE substr(transaction_date,1,7)=? ORDER BY transaction_date DESC, id DESC",
            (month,),
        ).fetchall()
    return get_db().execute("SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC").fetchall()


@app.get("/api/finance/transactions")
def api_finance_list():
    try:
        rows = finance_query(request.args.get("month"))
        return jsonify({"ok": True, "transactions": [serialize_transaction(item) for item in rows_dict(rows)]})
    except ValueError as exc:
        return json_error(str(exc))


@app.post("/api/finance/transactions")
def api_finance_create():
    try:
        data = body()
        kind = data.get("kind")
        if kind not in ("income", "expense"):
            raise ValueError("Выберите тип операции.")
        amount_minor = parse_amount(data.get("amount_minor", data.get("amount")))
        category = require_text(data.get("category"), "Категория", 80)
        transaction_date = validate_date(data.get("transaction_date") or date.today().isoformat())
        comment = optional_text(data.get("comment"), 240)
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO transactions(kind,amount_minor,category,transaction_date,comment,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (kind, amount_minor, category, transaction_date, comment, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM transactions WHERE id=?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "transaction": serialize_transaction(row_dict(row))}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.patch("/api/finance/transactions/<int:transaction_id>")
def api_finance_update(transaction_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
    if current is None:
        return json_error("Операция не найдена.", 404)
    try:
        data = body()
        kind = data.get("kind", current["kind"])
        if kind not in ("income", "expense"):
            raise ValueError("Выберите тип операции.")
        amount_minor = parse_amount(data.get("amount_minor", current["amount_minor"]))
        category = require_text(data.get("category", current["category"]), "Категория", 80)
        transaction_date = validate_date(data.get("transaction_date", current["transaction_date"]))
        comment = optional_text(data.get("comment", current["comment"]), 240)
        db.execute(
            "UPDATE transactions SET kind=?,amount_minor=?,category=?,transaction_date=?,comment=?,updated_at=? WHERE id=?",
            (kind, amount_minor, category, transaction_date, comment, now_iso(), transaction_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
        return jsonify({"ok": True, "transaction": serialize_transaction(row_dict(row))})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/finance/transactions/<int:transaction_id>")
def api_finance_delete(transaction_id: int):
    db = get_db()
    cursor = db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Операция не найдена.", 404)
    return jsonify({"ok": True})


def savings_categories_query(include_archived: bool = False) -> list[dict[str, Any]]:
    where = "" if include_archived else "WHERE c.archived=0"
    rows = get_db().execute(
        f"""
        SELECT c.*,
          COALESCE((SELECT SUM(CASE WHEN o.kind IN ('initial','deposit') THEN o.amount_minor ELSE -o.amount_minor END)
                    FROM savings_operations o WHERE o.category_id=c.id), 0) AS balance_minor,
          COALESCE(p.amount_minor, 0) AS planned_amount_minor,
          COALESCE(p.enabled, 0) AS plan_enabled,
          p.day_of_month AS plan_day
        FROM savings_categories c
        LEFT JOIN savings_plans p ON p.category_id=c.id
        {where}
        ORDER BY c.archived, c.id
        """,
    ).fetchall()
    return [serialize_savings_category(item) for item in rows_dict(rows)]


def savings_category(category_id: int, include_archived: bool = False) -> sqlite3.Row | None:
    query = "SELECT * FROM savings_categories WHERE id=?"
    params: list[Any] = [category_id]
    if not include_archived:
        query += " AND archived=0"
    return get_db().execute(query, tuple(params)).fetchone()


def savings_balance(category_id: int) -> int:
    row = get_db().execute(
        "SELECT COALESCE(SUM(CASE WHEN kind IN ('initial','deposit') THEN amount_minor ELSE -amount_minor END),0) AS balance FROM savings_operations WHERE category_id=?",
        (category_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def nonnegative_amount(value: Any, label: str = "Сумма") -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        amount = value
    else:
        normalized = str(value).replace(" ", "").replace(",", ".")
        try:
            amount = round(float(normalized) * 100)
        except ValueError as exc:
            raise ValueError(f"Введите корректное значение поля «{label}».") from exc
    if amount < 0:
        raise ValueError(f"Поле «{label}» не может быть отрицательным.")
    return int(amount)


@app.get("/api/finance/savings/categories")
def api_savings_categories_list():
    include_archived = parse_bool(request.args.get("include_archived"))
    return jsonify({"ok": True, "categories": savings_categories_query(include_archived)})


@app.post("/api/finance/savings/categories")
def api_savings_category_create():
    try:
        data = body()
        name = require_text(data.get("name"), "Название категории", 80)
        goal_minor = nonnegative_amount(data.get("goal_minor"), "Цель")
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO savings_categories(name,goal_minor,created_at,updated_at) VALUES(?,?,?,?)",
            (name, goal_minor, timestamp, timestamp),
        )
        db.commit()
        result = next(item for item in savings_categories_query(True) if item["id"] == cursor.lastrowid)
        return jsonify({"ok": True, "category": result}), 201
    except (ValueError, sqlite3.IntegrityError) as exc:
        message = "Такая категория уже существует." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.patch("/api/finance/savings/categories/<int:category_id>")
def api_savings_category_update(category_id: int):
    current = savings_category(category_id, True)
    if current is None:
        return json_error("Категория сбережений не найдена.", 404)
    try:
        data = body()
        name = require_text(data.get("name", current["name"]), "Название категории", 80)
        goal_minor = nonnegative_amount(data.get("goal_minor", current["goal_minor"]), "Цель")
        archived = parse_bool(data.get("archived", current["archived"]))
        db = get_db()
        db.execute(
            "UPDATE savings_categories SET name=?,goal_minor=?,archived=?,updated_at=? WHERE id=?",
            (name, goal_minor, archived, now_iso(), category_id),
        )
        db.commit()
        result = next(item for item in savings_categories_query(True) if item["id"] == category_id)
        return jsonify({"ok": True, "category": result})
    except (ValueError, sqlite3.IntegrityError) as exc:
        message = "Такая категория уже существует." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.delete("/api/finance/savings/categories/<int:category_id>")
def api_savings_category_archive(category_id: int):
    db = get_db()
    cursor = db.execute("UPDATE savings_categories SET archived=1,updated_at=? WHERE id=?", (now_iso(), category_id))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Категория сбережений не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/finance/savings/operations")
def api_savings_operations_list():
    try:
        category_id = int(request.args["category_id"]) if request.args.get("category_id") else None
    except (TypeError, ValueError):
        return json_error("Некорректная категория сбережений.")
    sql = "SELECT o.*, c.name AS category_name FROM savings_operations o JOIN savings_categories c ON c.id=o.category_id"
    params: list[Any] = []
    if category_id:
        sql += " WHERE o.category_id=?"
        params.append(category_id)
    sql += " ORDER BY o.operation_date DESC, o.id DESC LIMIT 2000"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return jsonify({"ok": True, "operations": [serialize_savings_operation(item) for item in rows_dict(rows)]})


@app.post("/api/finance/savings/operations")
def api_savings_operation_create():
    try:
        data = body()
        category_id = int(data.get("category_id"))
        category = savings_category(category_id)
        if category is None:
            raise ValueError("Выберите активную категорию сбережений.")
        kind = str(data.get("kind") or "deposit").strip().lower()
        if kind not in {"initial", "deposit", "withdrawal"}:
            raise ValueError("Некорректный тип операции сбережений.")
        amount_minor = parse_amount(data.get("amount_minor", data.get("amount")))
        if kind == "withdrawal" and amount_minor > savings_balance(category_id):
            raise ValueError("Нельзя снять больше, чем накоплено в этой категории.")
        operation_date = validate_date(data.get("operation_date") or date.today().isoformat())
        comment = optional_text(data.get("comment"), 240)
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO savings_operations(category_id,kind,amount_minor,operation_date,comment,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (category_id, kind, amount_minor, operation_date, comment, timestamp, timestamp),
        )
        db.commit()
        row = db.execute(
            "SELECT o.*, c.name AS category_name FROM savings_operations o JOIN savings_categories c ON c.id=o.category_id WHERE o.id=?",
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify({"ok": True, "operation": serialize_savings_operation(row_dict(row))}), 201
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.patch("/api/finance/savings/operations/<int:operation_id>")
def api_savings_operation_update(operation_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM savings_operations WHERE id=?", (operation_id,)).fetchone()
    if current is None:
        return json_error("Операция сбережений не найдена.", 404)
    try:
        data = body()
        category_id = int(data.get("category_id", current["category_id"]))
        if savings_category(category_id) is None:
            raise ValueError("Выберите активную категорию сбережений.")
        kind = str(data.get("kind", current["kind"])).lower()
        if kind not in {"initial", "deposit", "withdrawal"}:
            raise ValueError("Некорректный тип операции сбережений.")
        amount_minor = parse_amount(data.get("amount_minor", current["amount_minor"]))
        operation_date = validate_date(data.get("operation_date", current["operation_date"]))
        comment = optional_text(data.get("comment", current["comment"]), 240)
        balance_without_current = savings_balance(category_id)
        if category_id == int(current["category_id"]):
            if current["kind"] in {"initial", "deposit"}:
                balance_without_current -= int(current["amount_minor"])
            else:
                balance_without_current += int(current["amount_minor"])
        if kind == "withdrawal" and amount_minor > balance_without_current:
            raise ValueError("Нельзя снять больше, чем накоплено в этой категории.")
        db.execute(
            "UPDATE savings_operations SET category_id=?,kind=?,amount_minor=?,operation_date=?,comment=?,updated_at=? WHERE id=?",
            (category_id, kind, amount_minor, operation_date, comment, now_iso(), operation_id),
        )
        db.commit()
        row = db.execute(
            "SELECT o.*, c.name AS category_name FROM savings_operations o JOIN savings_categories c ON c.id=o.category_id WHERE o.id=?",
            (operation_id,),
        ).fetchone()
        return jsonify({"ok": True, "operation": serialize_savings_operation(row_dict(row))})
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.delete("/api/finance/savings/operations/<int:operation_id>")
def api_savings_operation_delete(operation_id: int):
    db = get_db()
    cursor = db.execute("DELETE FROM savings_operations WHERE id=?", (operation_id,))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Операция сбережений не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/finance/savings/summary")
def api_savings_summary():
    categories = savings_categories_query(False)
    total_saved = sum(item["balance_minor"] for item in categories)
    db = get_db()
    cash = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE -amount_minor END),0) AS balance FROM transactions"
    ).fetchone()["balance"]
    return jsonify({
        "ok": True,
        "categories": categories,
        "total_saved_minor": total_saved,
        "available_balance_minor": int(cash or 0) - total_saved,
    })


@app.get("/api/finance/savings/plans")
def api_savings_plans_list():
    rows = get_db().execute(
        "SELECT p.*, c.name AS category_name FROM savings_plans p JOIN savings_categories c ON c.id=p.category_id WHERE c.archived=0 ORDER BY c.id"
    ).fetchall()
    result = rows_dict(rows)
    for item in result:
        item["amount_minor"] = int(item["amount_minor"])
        item["enabled"] = bool(item["enabled"])
    return jsonify({"ok": True, "plans": result})


@app.patch("/api/finance/savings/categories/<int:category_id>/plan")
def api_savings_plan_update(category_id: int):
    try:
        if savings_category(category_id) is None:
            raise ValueError("Выберите активную категорию сбережений.")
        data = body()
        enabled = parse_bool(data.get("enabled", True))
        if not enabled:
            get_db().execute("DELETE FROM savings_plans WHERE category_id=?", (category_id,))
            get_db().commit()
            return jsonify({"ok": True, "plan": None})
        amount_minor = parse_amount(data.get("amount_minor", data.get("amount")))
        day = int(data.get("day_of_month", 1))
        if not 1 <= day <= 31:
            raise ValueError("День пополнения должен быть от 1 до 31.")
        timestamp = now_iso()
        db = get_db()
        db.execute(
            "INSERT INTO savings_plans(category_id,amount_minor,day_of_month,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(category_id) DO UPDATE SET amount_minor=excluded.amount_minor,day_of_month=excluded.day_of_month,enabled=excluded.enabled,updated_at=excluded.updated_at",
            (category_id, amount_minor, day, enabled, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM savings_plans WHERE category_id=?", (category_id,)).fetchone()
        result = row_dict(row)
        result["amount_minor"] = int(result["amount_minor"])
        result["enabled"] = bool(result["enabled"])
        return jsonify({"ok": True, "plan": result})
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.get("/api/utilities/accounts")
def api_utility_accounts_list():
    rows = get_db().execute("SELECT * FROM utility_accounts WHERE archived=0 ORDER BY id").fetchall()
    return jsonify({"ok": True, "accounts": rows_dict(rows)})


@app.post("/api/utilities/accounts")
def api_utility_account_create():
    try:
        data = body()
        name = require_text(data.get("name"), "Название квартиры", 100)
        address = optional_text(data.get("address"), 180)
        provider = optional_text(data.get("provider"), 120)
        account_number = optional_text(data.get("account_number"), 80)
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO utility_accounts(name,address,provider,account_number,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (name, address, provider, account_number, timestamp, timestamp),
        )
        seed_utility_services(db)
        db.commit()
        row = db.execute("SELECT * FROM utility_accounts WHERE id=?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "account": row_dict(row)}), 201
    except ValueError as exc:
        return json_error(str(exc))


@app.patch("/api/utilities/accounts/<int:account_id>")
def api_utility_account_update(account_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM utility_accounts WHERE id=?", (account_id,)).fetchone()
    if current is None:
        return json_error("Квартира не найдена.", 404)
    try:
        data = body()
        name = require_text(data.get("name", current["name"]), "Название квартиры", 100)
        address = optional_text(data.get("address", current["address"]), 180)
        provider = optional_text(data.get("provider", current["provider"]), 120)
        account_number = optional_text(data.get("account_number", current["account_number"]), 80)
        db.execute(
            "UPDATE utility_accounts SET name=?,address=?,provider=?,account_number=?,updated_at=? WHERE id=?",
            (name, address, provider, account_number, now_iso(), account_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM utility_accounts WHERE id=?", (account_id,)).fetchone()
        return jsonify({"ok": True, "account": row_dict(row)})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/utilities/accounts/<int:account_id>")
def api_utility_account_delete(account_id: int):
    db = get_db()
    cursor = db.execute("UPDATE utility_accounts SET archived=1,updated_at=? WHERE id=?", (now_iso(), account_id))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Квартира не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/utilities/accounts/<int:account_id>/services")
def api_utility_services_list(account_id: int):
    account = get_db().execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone()
    if account is None:
        return json_error("Квартира не найдена.", 404)
    seed_utility_services(get_db())
    rows = get_db().execute(
        "SELECT * FROM utility_services WHERE account_id=? AND archived=0 ORDER BY id",
        (account_id,),
    ).fetchall()
    return jsonify({"ok": True, "services": [serialize_utility_service(item) for item in rows_dict(rows)]})


@app.post("/api/utilities/accounts/<int:account_id>/services")
def api_utility_service_create(account_id: int):
    try:
        data = body()
        if get_db().execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone() is None:
            return json_error("Квартира не найдена.", 404)
        name = require_text(data.get("name"), "Название услуги", 80)
        unit = optional_text(data.get("unit"), 24)
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO utility_services(account_id,name,unit,created_at,updated_at) VALUES(?,?,?,?,?)",
            (account_id, name, unit, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM utility_services WHERE id=?", (cursor.lastrowid,)).fetchone()
        return jsonify({"ok": True, "service": serialize_utility_service(row_dict(row))}), 201
    except (ValueError, sqlite3.IntegrityError) as exc:
        message = "Такая услуга уже добавлена." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.patch("/api/utilities/services/<int:service_id>")
def api_utility_service_update(service_id: int):
    current = get_db().execute("SELECT * FROM utility_services WHERE id=?", (service_id,)).fetchone()
    if current is None:
        return json_error("Услуга не найдена.", 404)
    try:
        data = body()
        name = require_text(data.get("name", current["name"]), "Название услуги", 80)
        unit = optional_text(data.get("unit", current["unit"]), 24)
        archived = parse_bool(data.get("archived", current["archived"]))
        db = get_db()
        db.execute("UPDATE utility_services SET name=?,unit=?,archived=?,updated_at=? WHERE id=?", (name, unit, archived, now_iso(), service_id))
        db.commit()
        row = db.execute("SELECT * FROM utility_services WHERE id=?", (service_id,)).fetchone()
        return jsonify({"ok": True, "service": serialize_utility_service(row_dict(row))})
    except (ValueError, sqlite3.IntegrityError) as exc:
        message = "Такая услуга уже добавлена." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.delete("/api/utilities/services/<int:service_id>")
def api_utility_service_delete(service_id: int):
    db = get_db()
    cursor = db.execute("UPDATE utility_services SET archived=1,updated_at=? WHERE id=?", (now_iso(), service_id))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Услуга не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/utilities/accounts/<int:account_id>/readings")
def api_utility_readings_list(account_id: int):
    try:
        if get_db().execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone() is None:
            return json_error("Квартира не найдена.", 404)
        rows = get_db().execute(
            "SELECT r.*, s.name AS service_name, s.unit FROM utility_meter_readings r JOIN utility_services s ON s.id=r.service_id WHERE r.account_id=? ORDER BY r.reading_date DESC, r.id DESC LIMIT 500",
            (account_id,),
        ).fetchall()
        return jsonify({"ok": True, "readings": [serialize_meter_reading(item) for item in rows_dict(rows)]})
    except ValueError as exc:
        return json_error(str(exc))


@app.post("/api/utilities/accounts/<int:account_id>/readings")
def api_utility_reading_create(account_id: int):
    try:
        data = body()
        db = get_db()
        if db.execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone() is None:
            return json_error("Квартира не найдена.", 404)
        service_id = int(data.get("service_id"))
        service = db.execute("SELECT id FROM utility_services WHERE id=? AND account_id=? AND archived=0", (service_id, account_id)).fetchone()
        if service is None:
            raise ValueError("Выберите услугу этой квартиры.")
        reading_value = parse_decimal(data.get("reading_value"))
        reading_date = validate_date(data.get("reading_date") or date.today().isoformat())
        note = optional_text(data.get("note"), 180)
        timestamp = now_iso()
        db.execute(
            "INSERT INTO utility_meter_readings(account_id,service_id,reading_value,reading_date,note,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(service_id,reading_date) DO UPDATE SET reading_value=excluded.reading_value,note=excluded.note,created_at=excluded.created_at",
            (account_id, service_id, reading_value, reading_date, note, timestamp),
        )
        db.commit()
        row = db.execute(
            "SELECT r.*, s.name AS service_name, s.unit FROM utility_meter_readings r JOIN utility_services s ON s.id=r.service_id WHERE r.service_id=? AND r.reading_date=?",
            (service_id, reading_date),
        ).fetchone()
        return jsonify({"ok": True, "reading": serialize_meter_reading(row_dict(row))}), 201
    except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
        return json_error(str(exc))


@app.post("/api/utilities/accounts/<int:account_id>/meter-submission")
def api_utility_meter_submission(account_id: int):
    try:
        data = body()
        db = get_db()
        if db.execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone() is None:
            return json_error("Квартира не найдена.", 404)
        submission_month = validate_month(data.get("submission_month") or date.today().strftime("%Y-%m"))
        submitted = parse_bool(data.get("submitted", True))
        if submitted:
            db.execute(
                "INSERT INTO utility_meter_submissions(account_id,submission_month,submitted_at) VALUES(?,?,?) ON CONFLICT(account_id,submission_month) DO UPDATE SET submitted_at=excluded.submitted_at",
                (account_id, submission_month, now_iso()),
            )
        else:
            db.execute("DELETE FROM utility_meter_submissions WHERE account_id=? AND submission_month=?", (account_id, submission_month))
        db.commit()
        row = db.execute("SELECT * FROM utility_meter_submissions WHERE account_id=? AND submission_month=?", (account_id, submission_month)).fetchone()
        return jsonify({"ok": True, "submitted": bool(row), "submission": row_dict(row)})
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.get("/api/utilities/reminders/status")
def api_utility_reminders_status():
    try:
        requested_month = validate_month(request.args.get("month") or date.today().strftime("%Y-%m"))
        current_date = date.today()
        active_window = 15 <= current_date.day <= 26 and requested_month == current_date.strftime("%Y-%m")
        db = get_db()
        accounts = db.execute("SELECT * FROM utility_accounts WHERE archived=0 ORDER BY id").fetchall()
        reminders = []
        for account in accounts:
            submitted = db.execute(
                "SELECT id,submitted_at FROM utility_meter_submissions WHERE account_id=? AND submission_month=?",
                (account["id"], requested_month),
            ).fetchone()
            if active_window and submitted is None:
                reminders.append({"account_id": account["id"], "account_name": account["name"], "address": account["address"], "month": requested_month})
        settings = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM utility_settings").fetchall()}
        system_notification_sent = False
        if request.args.get("notify") == "1":
            system_notification_sent = maybe_send_utility_reminder_notification(db, reminders, settings)
        return jsonify({
            "ok": True,
            "month": requested_month,
            "active_window": active_window,
            "reminders": reminders,
            "system_notification_sent": system_notification_sent,
            "settings": {"reminder_time": settings.get("reminder_time", "09:00"), "notifications_enabled": bool(parse_bool(settings.get("notifications_enabled", "1")))},
        })
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/utilities/reminders/settings")
def api_utility_reminder_settings_get():
    rows = get_db().execute("SELECT key,value FROM utility_settings").fetchall()
    raw = {row["key"]: row["value"] for row in rows}
    return jsonify({"ok": True, "settings": {"reminder_time": raw.get("reminder_time", "09:00"), "notifications_enabled": bool(parse_bool(raw.get("notifications_enabled", "1")))}})


@app.patch("/api/utilities/reminders/settings")
def api_utility_reminder_settings_patch():
    try:
        data = body()
        reminder_time = validate_time(data.get("reminder_time", "09:00"), "Время напоминания") or "09:00"
        notifications_enabled = parse_bool(data.get("notifications_enabled", True))
        db = get_db()
        timestamp = now_iso()
        db.executemany(
            "INSERT INTO utility_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            [("reminder_time", reminder_time, timestamp), ("notifications_enabled", str(notifications_enabled), timestamp)],
        )
        db.commit()
        return jsonify({"ok": True, "settings": {"reminder_time": reminder_time, "notifications_enabled": bool(notifications_enabled)}})
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/utilities/summary")
def api_utility_summary():
    try:
        month = validate_month(request.args.get("month") or date.today().strftime("%Y-%m"))
        rows = get_db().execute(
            "SELECT * FROM utility_payments WHERE billing_month=?",
            (month,),
        ).fetchall()
        payments = [serialize_payment(row_dict(row)) for row in rows]
        accrued = sum(item["amount_minor"] for item in payments)
        paid = sum(item["amount_minor"] for item in payments if item["status"] == "paid")
        remaining = accrued - paid
        return jsonify({
            "ok": True,
            "month": month,
            "accrued_minor": accrued,
            "due_minor": remaining,
            "remaining_minor": remaining,
            "paid_minor": paid,
            "overdue_minor": sum(item["amount_minor"] for item in payments if item["status"] == "overdue"),
            "overdue_count": sum(1 for item in payments if item["status"] == "overdue"),
        })
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/utilities/payments")
def api_utility_payments_list():
    try:
        month = validate_month(request.args.get("month")) if request.args.get("month") else None
        sql = "SELECT p.*, a.name AS account_name, a.address, a.provider, a.account_number FROM utility_payments p JOIN utility_accounts a ON a.id=p.account_id AND a.archived=0"
        params: list[Any] = []
        conditions = []
        if month:
            conditions.append("p.billing_month=?")
            params.append(month)
        if request.args.get("account_id"):
            try:
                conditions.append("p.account_id=?")
                params.append(int(request.args["account_id"]))
            except (TypeError, ValueError):
                return json_error("Некорректная квартира.")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY p.due_date, p.id"
        rows = get_db().execute(sql, tuple(params)).fetchall()
        payments = [serialize_payment(item) for item in rows_dict(rows)]
        for payment in payments:
            payment["items"] = utility_payment_items(payment["id"])
        return jsonify({"ok": True, "payments": payments})
    except ValueError as exc:
        return json_error(str(exc))


def normalize_payment_items(raw_items: Any, account_id: int) -> list[dict[str, Any]]:
    if raw_items in (None, ""):
        return []
    if not isinstance(raw_items, list):
        raise ValueError("Детализация платежа должна быть списком услуг.")
    db = get_db()
    services = {
        int(row["id"]): row
        for row in db.execute("SELECT * FROM utility_services WHERE account_id=? AND archived=0", (account_id,)).fetchall()
    }
    result = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        service_id = int(raw["service_id"]) if raw.get("service_id") not in (None, "") else None
        service = services.get(service_id) if service_id else None
        service_name = require_text(raw.get("service_name") or (service["name"] if service else "Услуга"), "Услуга", 80)
        raw_amount = raw.get("amount_minor", raw.get("amount"))
        tariff_minor = nonnegative_amount(raw.get("tariff_minor"), "Тариф") if raw.get("tariff_minor") not in (None, "") else None
        previous = parse_decimal(raw["previous_reading"], "Предыдущее показание") if raw.get("previous_reading") not in (None, "") else None
        current = parse_decimal(raw["current_reading"], "Текущее показание") if raw.get("current_reading") not in (None, "") else None
        if raw_amount not in (None, "", 0, "0"):
            amount_minor = parse_amount(raw_amount)
        elif tariff_minor is not None and previous is not None and current is not None:
            if current < previous:
                raise ValueError(f"Текущее показание услуги «{service_name}» не может быть меньше предыдущего.")
            amount_minor = round((current - previous) * tariff_minor)
            if amount_minor <= 0:
                raise ValueError(f"Расход по услуге «{service_name}» должен быть больше нуля.")
        else:
            raise ValueError(f"Укажи сумму услуги «{service_name}» или тариф с двумя показаниями.")
        result.append({
            "service_id": service_id if service else None,
            "service_name": service_name,
            "tariff_minor": tariff_minor,
            "previous_reading": previous,
            "current_reading": current,
            "amount_minor": amount_minor,
            "note": optional_text(raw.get("note"), 180),
        })
    return result


def save_payment_items(db: sqlite3.Connection, payment_id: int, items: list[dict[str, Any]]) -> None:
    db.execute("DELETE FROM utility_payment_items WHERE payment_id=?", (payment_id,))
    db.executemany(
        "INSERT INTO utility_payment_items(payment_id,service_id,service_name,tariff_minor,previous_reading,current_reading,amount_minor,note) VALUES(?,?,?,?,?,?,?,?)",
        [
            (payment_id, item["service_id"], item["service_name"], item["tariff_minor"], item["previous_reading"], item["current_reading"], item["amount_minor"], item["note"])
            for item in items
        ],
    )


@app.post("/api/utilities/payments")
def api_utility_payment_create():
    try:
        data = body()
        account_id = int(data.get("account_id"))
        billing_month = validate_month(data.get("billing_month"))
        due_date = validate_date(data.get("due_date"), "Срок оплаты")
        items = normalize_payment_items(data.get("items"), account_id)
        raw_amount = data.get("amount_minor", data.get("amount"))
        amount_minor = parse_amount(raw_amount) if raw_amount not in (None, "", 0, "0") else sum(item["amount_minor"] for item in items)
        if amount_minor <= 0:
            raise ValueError("Введите сумму или добавьте услуги в детализацию.")
        status = data.get("status", "pending")
        if status not in ("pending", "paid"):
            raise ValueError("Некорректный статус платежа.")
        note = optional_text(data.get("note"), 240)
        paid_date = validate_date(data.get("paid_date") or date.today().isoformat(), "Дата оплаты") if status == "paid" else None
        db = get_db()
        account = db.execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone()
        if account is None:
            raise ValueError("Выберите существующую квартиру.")
        timestamp = now_iso()
        paid_at = timestamp if status == "paid" else None
        cursor = db.execute(
            "INSERT INTO utility_payments(account_id,billing_month,due_date,amount_minor,status,note,paid_at,paid_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (account_id, billing_month, due_date, amount_minor, status, note, paid_at, paid_date, timestamp, timestamp),
        )
        save_payment_items(db, cursor.lastrowid, items)
        db.commit()
        row = db.execute(
            "SELECT p.*, a.name AS account_name, a.address, a.provider, a.account_number FROM utility_payments p JOIN utility_accounts a ON a.id=p.account_id WHERE p.id=?",
            (cursor.lastrowid,),
        ).fetchone()
        payment = serialize_payment(row_dict(row))
        payment["items"] = utility_payment_items(payment["id"])
        return jsonify({"ok": True, "payment": payment}), 201
    except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
        message = "Платёж за этот месяц уже существует." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.patch("/api/utilities/payments/<int:payment_id>")
def api_utility_payment_update(payment_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM utility_payments WHERE id=?", (payment_id,)).fetchone()
    if current is None:
        return json_error("Платёж не найден.", 404)
    try:
        data = body()
        account_id = int(data.get("account_id", current["account_id"]))
        billing_month = validate_month(data.get("billing_month", current["billing_month"]))
        due_date = validate_date(data.get("due_date", current["due_date"]), "Срок оплаты")
        items_provided = "items" in data
        items = normalize_payment_items(data.get("items"), account_id) if items_provided else []
        raw_amount = data.get("amount_minor", data.get("amount", current["amount_minor"]))
        amount_minor = parse_amount(raw_amount) if raw_amount not in (None, "", 0, "0") else sum(item["amount_minor"] for item in items)
        if amount_minor <= 0:
            raise ValueError("Введите сумму или добавьте услуги в детализацию.")
        status = data.get("status", current["status"])
        if status == "overdue":
            status = "pending"
        if status not in ("pending", "paid"):
            raise ValueError("Некорректный статус платежа.")
        note = optional_text(data.get("note", current["note"]), 240)
        paid_date = validate_date(
            data.get("paid_date", current["paid_date"] or date.today().isoformat()),
            "Дата оплаты",
        ) if status == "paid" else None
        account = db.execute("SELECT id FROM utility_accounts WHERE id=? AND archived=0", (account_id,)).fetchone()
        if account is None:
            raise ValueError("Выберите существующую квартиру.")
        timestamp = now_iso()
        paid_at = current["paid_at"]
        if status == "paid" and not paid_at:
            paid_at = timestamp
        if status == "pending":
            paid_at = None
        db.execute(
            "UPDATE utility_payments SET account_id=?,billing_month=?,due_date=?,amount_minor=?,status=?,note=?,paid_at=?,paid_date=?,updated_at=? WHERE id=?",
            (account_id, billing_month, due_date, amount_minor, status, note, paid_at, paid_date, timestamp, payment_id),
        )
        if items_provided:
            save_payment_items(db, payment_id, items)
        elif account_id != int(current["account_id"]):
            save_payment_items(db, payment_id, [])
        db.commit()
        row = db.execute(
            "SELECT p.*, a.name AS account_name, a.address, a.provider, a.account_number FROM utility_payments p JOIN utility_accounts a ON a.id=p.account_id WHERE p.id=?",
            (payment_id,),
        ).fetchone()
        payment = serialize_payment(row_dict(row))
        payment["items"] = utility_payment_items(payment["id"])
        return jsonify({"ok": True, "payment": payment})
    except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
        message = "Платёж за этот месяц уже существует." if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        return json_error(message)


@app.delete("/api/utilities/payments/<int:payment_id>")
def api_utility_payment_delete(payment_id: int):
    db = get_db()
    cursor = db.execute("DELETE FROM utility_payments WHERE id=?", (payment_id,))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Платёж не найден.", 404)
    return jsonify({"ok": True})


def normalize_schedule(value: Any, frequency: str) -> str:
    if frequency == "daily":
        return "0,1,2,3,4,5,6"
    raw = value if isinstance(value, list) else str(value or "").split(",")
    days = sorted({int(item) for item in raw if str(item).strip().isdigit() and 0 <= int(item) <= 6})
    return ",".join(str(item) for item in days) or "0,1,2,3,4,5,6"


@app.get("/api/habits")
def api_habits_list():
    rows = get_db().execute("SELECT * FROM habits WHERE archived=0 ORDER BY id").fetchall()
    result = rows_dict(rows)
    for item in result:
        item["schedule_days"] = [int(x) for x in item["schedule_days"].split(",") if x]
    return jsonify({"ok": True, "habits": result})


@app.post("/api/habits")
def api_habits_create():
    try:
        data = body()
        name = require_text(data.get("name"), "Название привычки", 100)
        frequency = data.get("frequency", "daily")
        if frequency not in ("daily", "weekly"):
            raise ValueError("Некорректная частота привычки.")
        schedule_days = normalize_schedule(data.get("schedule_days"), frequency)
        target_per_week = max(1, min(7, int(data.get("target_per_week", 7))))
        color = optional_text(data.get("color") or "#ff2290", 20)
        timestamp = now_iso()
        db = get_db()
        cursor = db.execute(
            "INSERT INTO habits(name,frequency,schedule_days,target_per_week,color,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (name, frequency, schedule_days, target_per_week, color, timestamp, timestamp),
        )
        db.commit()
        row = db.execute("SELECT * FROM habits WHERE id=?", (cursor.lastrowid,)).fetchone()
        item = row_dict(row)
        item["schedule_days"] = [int(x) for x in item["schedule_days"].split(",") if x]
        return jsonify({"ok": True, "habit": item}), 201
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.patch("/api/habits/<int:habit_id>")
def api_habits_update(habit_id: int):
    db = get_db()
    current = db.execute("SELECT * FROM habits WHERE id=?", (habit_id,)).fetchone()
    if current is None:
        return json_error("Привычка не найдена.", 404)
    try:
        data = body()
        name = require_text(data.get("name", current["name"]), "Название привычки", 100)
        frequency = data.get("frequency", current["frequency"])
        if frequency not in ("daily", "weekly"):
            raise ValueError("Некорректная частота привычки.")
        schedule_days = normalize_schedule(data.get("schedule_days", current["schedule_days"]), frequency)
        target_per_week = max(1, min(7, int(data.get("target_per_week", current["target_per_week"]))))
        color = optional_text(data.get("color", current["color"]) or "#ff2290", 20)
        db.execute(
            "UPDATE habits SET name=?,frequency=?,schedule_days=?,target_per_week=?,color=?,updated_at=? WHERE id=?",
            (name, frequency, schedule_days, target_per_week, color, now_iso(), habit_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM habits WHERE id=?", (habit_id,)).fetchone()
        item = row_dict(row)
        item["schedule_days"] = [int(x) for x in item["schedule_days"].split(",") if x]
        return jsonify({"ok": True, "habit": item})
    except (ValueError, TypeError) as exc:
        return json_error(str(exc))


@app.delete("/api/habits/<int:habit_id>")
def api_habits_delete(habit_id: int):
    db = get_db()
    cursor = db.execute("UPDATE habits SET archived=1,updated_at=? WHERE id=?", (now_iso(), habit_id))
    db.commit()
    if cursor.rowcount == 0:
        return json_error("Привычка не найдена.", 404)
    return jsonify({"ok": True})


@app.get("/api/habits/entries")
def api_habit_entries_list():
    try:
        start = validate_date(request.args.get("start"), "Начало периода")
        end = validate_date(request.args.get("end"), "Конец периода")
        rows = get_db().execute(
            "SELECT habit_id,entry_date,done FROM habit_entries WHERE entry_date BETWEEN ? AND ? ORDER BY entry_date",
            (start, end),
        ).fetchall()
        result = rows_dict(rows)
        for item in result:
            item["done"] = bool(item["done"])
        return jsonify({"ok": True, "entries": result})
    except ValueError as exc:
        return json_error(str(exc))


@app.put("/api/habits/<int:habit_id>/entries/<entry_date>")
def api_habit_entry_put(habit_id: int, entry_date: str):
    try:
        entry_date = validate_date(entry_date)
        done = parse_bool(body().get("done", True))
        db = get_db()
        habit = db.execute("SELECT id FROM habits WHERE id=? AND archived=0", (habit_id,)).fetchone()
        if habit is None:
            return json_error("Привычка не найдена.", 404)
        db.execute(
            "INSERT INTO habit_entries(habit_id,entry_date,done) VALUES(?,?,?) ON CONFLICT(habit_id,entry_date) DO UPDATE SET done=excluded.done",
            (habit_id, entry_date, done),
        )
        db.commit()
        return jsonify({"ok": True, "habit_id": habit_id, "entry_date": entry_date, "done": bool(done)})
    except ValueError as exc:
        return json_error(str(exc))


@app.delete("/api/habits/<int:habit_id>/entries/<entry_date>")
def api_habit_entry_delete(habit_id: int, entry_date: str):
    try:
        entry_date = validate_date(entry_date)
    except ValueError as exc:
        return json_error(str(exc))
    db = get_db()
    db.execute("DELETE FROM habit_entries WHERE habit_id=? AND entry_date=?", (habit_id, entry_date))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/migrate")
def api_migrate():
    payload = body()
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    goals = payload.get("goals") if isinstance(payload.get("goals"), list) else []
    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    db = get_db()
    imported = {"tasks": 0, "goals": 0, "notes": 0}
    try:
        db.execute("BEGIN")
        for item in tasks:
            task_date = validate_date(item.get("task_date"))
            text = require_text(item.get("text"), "Название")
            start_time = validate_time(item.get("start_time"), "Начало")
            end_time = validate_time(item.get("end_time"), "Окончание")
            exists = db.execute(
                "SELECT id FROM tasks WHERE task_date=? AND text=? AND COALESCE(start_time,'')=COALESCE(?, '') AND COALESCE(end_time,'')=COALESCE(?, '')",
                (task_date, text, start_time, end_time),
            ).fetchone()
            if exists:
                continue
            timestamp = now_iso()
            db.execute(
                "INSERT INTO tasks(task_date,text,scope,start_time,end_time,done,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (task_date, text, "planner", start_time, end_time, parse_bool(item.get("done")), timestamp, timestamp),
            )
            imported["tasks"] += 1
        for item in goals:
            week_monday = validate_date(item.get("week_monday"))
            text = optional_text(item.get("text"), 240)
            db.execute(
                "INSERT INTO weekly_goals(week_monday,text,updated_at) VALUES(?,?,?) ON CONFLICT(week_monday) DO UPDATE SET text=excluded.text,updated_at=excluded.updated_at",
                (week_monday, text, now_iso()),
            )
            imported["goals"] += 1
        for item in notes:
            text = require_text(item.get("text"), "Заметка", 240)
            note_date = validate_date(item.get("note_date") or date.today().isoformat())
            exists = db.execute("SELECT id FROM notes WHERE text=? AND note_date=?", (text, note_date)).fetchone()
            if exists:
                continue
            db.execute("INSERT INTO notes(text,note_date,created_at) VALUES(?,?,?)", (text, note_date, now_iso()))
            imported["notes"] += 1
        db.commit()
    except (ValueError, sqlite3.Error) as exc:
        db.rollback()
        return json_error(f"Миграция не выполнена: {exc}", 400)
    return jsonify({"ok": True, "imported": imported})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
