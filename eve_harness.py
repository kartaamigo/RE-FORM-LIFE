"""Application-owned tools and durable, atomic confirmation of task proposals."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS assistant_task_proposals (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


class ConfirmationRequired(Exception):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload["reply"])
        self.payload = payload


def relevant_memories(text: str, memories: list[str], budget: int = 3500) -> list[str]:
    words = set(re.findall(r"\w{3,}", text.casefold()))
    ranked = sorted(enumerate(memories), key=lambda item: (
        len(words & set(re.findall(r"\w{3,}", item[1].casefold()))), item[0]
    ), reverse=True)
    selected = []
    for _, fact in ranked:
        fact = fact[:300]
        if len(fact) <= budget:
            selected.append(fact)
            budget -= len(fact)
        if len(selected) >= 20:
            break
    return selected


def _date(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Дата должна иметь формат YYYY-MM-DD.")
    date.fromisoformat(value)
    return value


def _text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Укажи непустой текст допустимой длины.")
    return value.strip()


def _properties(args: dict, allowed: set[str]) -> None:
    if set(args) - allowed:
        raise ValueError("Переданы неподдерживаемые параметры инструмента.")


TASK_FIELDS = {"text", "task_date", "start_time", "scope", "section", "done"}


def describe_fields(fields: dict) -> str:
    labels = {"text": "название", "task_date": "дата", "start_time": "время", "scope": "раздел", "section": "колонка", "done": "выполнение"}
    parts = []
    for key, value in fields.items():
        if key == "done":
            value = "выполнена" if value else "не выполнена"
        elif key == "scope":
            value = "планер" if value == "planner" else "доска задач"
        elif key == "start_time" and value is None:
            value = "без времени"
        parts.append(f"{labels[key]}: {value}")
    return "; ".join(parts)


def _fields(db, args: dict) -> dict:
    _properties(args, TASK_FIELDS)
    result = {}
    for key, value in args.items():
        if key == "text":
            result[key] = _text(value)
        elif key == "task_date":
            result[key] = _date(value)
        elif key == "start_time":
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)):
                raise ValueError("Время должно иметь формат HH:MM или null.")
            result[key] = value
        elif key == "scope":
            if value not in {"planner", "tasks"}:
                raise ValueError("Раздел должен быть planner или tasks.")
            result[key] = value
        elif key == "section":
            row = db.execute("SELECT name FROM sections WHERE archived=0 AND name=? COLLATE NOCASE", (_text(value, 48),)).fetchone()
            if row is None:
                raise ValueError("Выбери существующую колонку задач.")
            result[key] = row["name"]
        elif key == "done":
            if type(value) is not bool:
                raise ValueError("done должен быть true или false.")
            result[key] = int(value)
    return result


def tool_declarations(allow_changes: bool) -> list[dict]:
    string = {"type": "STRING"}
    tools = [{
        "name": "list_tasks", "description": "Получить задачи из приложения, включая ID. Для переноса/выполнения сначала прочитай задачи. Фильтры необязательны, до 50 результатов со смещением offset.",
        "parameters": {"type": "OBJECT", "properties": {
            "start": string, "end": string, "query": string,
            "scope": {"type": "STRING", "enum": ["planner", "tasks"]},
            "done": {"type": "BOOLEAN"}, "offset": {"type": "INTEGER"},
        }},
    }, {
        "name": "list_habits", "description": "Получить активные привычки и отметки на указанную дату.",
        "parameters": {"type": "OBJECT", "properties": {"date": string}},
    }, {
        "name": "search_memories", "description": "Найти явно сохранённые пользователем факты. Учитывает выключение персональной памяти.",
        "parameters": {"type": "OBJECT", "properties": {"query": string}, "required": ["query"]},
    }]
    if allow_changes:
        fields = {"text": string, "task_date": string, "section": string,
                  "scope": {"type": "STRING", "enum": ["planner", "tasks"]},
                  "start_time": {"type": "STRING", "nullable": True}, "done": {"type": "BOOLEAN"}}
        tools.append({
            "name": "propose_task_changes",
            "description": "Предложить создание или изменение до 20 задач одним пакетом. Не исполняет изменения: пользователь подтверждает точный список. Для update используй только ID задач, прочитанных через list_tasks в этом запросе. Если выбор неоднозначен, задай вопрос.",
            "parameters": {"type": "OBJECT", "properties": {"changes": {
                "type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                    "operation": {"type": "STRING", "enum": ["create", "update"]},
                    "task_id": {"type": "INTEGER"}, **fields,
                }, "required": ["operation"]},
            }}, "required": ["changes"]},
        })
    return tools


class EveHarness:
    def __init__(self, db, memories: list[str], allow_changes: bool = False):
        self.db = db
        self.memories = memories
        self.allow_changes = allow_changes
        self.observed: dict[int, dict] = {}

    def context(self) -> str:
        sections = [row["name"] for row in self.db.execute("SELECT name FROM sections WHERE archived=0 ORDER BY id LIMIT 50")]
        return (
            f"Текущая локальная дата приложения: {date.today().isoformat()}; "
            f"завтра: {(date.today() + timedelta(days=1)).isoformat()}. "
            f"Доступные колонки задач (данные): {json.dumps(sections, ensure_ascii=False)}. "
            "planner — недельный планер; tasks — доска задач. "
            "Доступны чтение задач, привычек и сохранённой памяти. "
            + ("Изменения задач требуют подтверждения. " if self.allow_changes else "В этом режиме изменение данных недоступно. ")
            + "Не обещай напоминания и фоновые действия: таких инструментов нет. "
            "При недоступном действии объясни ограничение и предложи доступный шаг."
        )

    def execute(self, name: str, args: dict) -> dict:
        if name == "list_tasks":
            _properties(args, {"start", "end", "query", "scope", "done", "offset"})
            clauses, params = [], []
            for key, operator in (("start", ">="), ("end", "<=")):
                if key in args:
                    clauses.append(f"task_date {operator} ?")
                    params.append(_date(args[key]))
            if "start" in args and "end" in args and args["start"] > args["end"]:
                raise ValueError("Начало периода позже конца.")
            for key in ("scope", "done"):
                if key in args:
                    value = _fields(self.db, {key: args[key]})[key]
                    clauses.append(f"{key}=?")
                    params.append(value)
            if "query" in args:
                clauses.append("instr(lower(text), lower(?)) > 0")
                params.append(_text(args["query"]))
            offset = args.get("offset", 0)
            if type(offset) is not int or not 0 <= offset <= 10000:
                raise ValueError("Некорректное смещение списка.")
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = self.db.execute("SELECT COUNT(*) FROM tasks" + where, params).fetchone()[0]
            rows = self.db.execute("SELECT * FROM tasks" + where + " ORDER BY task_date,start_time IS NULL,start_time,id LIMIT 50 OFFSET ?", [*params, offset]).fetchall()
            tasks = [dict(row) for row in rows]
            self.observed.update({task["id"]: task for task in tasks})
            return {"ok": True, "tasks": tasks, "total": total, "next_offset": offset + len(tasks) if offset + len(tasks) < total else None}
        if name == "list_habits":
            _properties(args, {"date"})
            day = _date(args.get("date", date.today().isoformat()))
            rows = self.db.execute("SELECT h.id,h.name,h.frequency,h.schedule_days,h.target_per_week,COALESCE(e.done,0) AS done FROM habits h LEFT JOIN habit_entries e ON e.habit_id=h.id AND e.entry_date=? WHERE h.archived=0 ORDER BY h.id LIMIT 50", (day,)).fetchall()
            return {"ok": True, "date": day, "habits": [dict(row) for row in rows]}
        if name == "search_memories":
            _properties(args, {"query"})
            query = _text(args.get("query"))
            return {"ok": True, "facts": relevant_memories(query, [fact for fact in self.memories if set(re.findall(r"\w{3,}", query.casefold())) & set(re.findall(r"\w{3,}", fact.casefold()))])}
        if name != "propose_task_changes" or not self.allow_changes:
            raise ValueError("Этот инструмент недоступен.")
        _properties(args, {"changes"})
        changes = args.get("changes")
        if not isinstance(changes, list) or not 1 <= len(changes) <= 20:
            raise ValueError("В предложении должно быть от 1 до 20 изменений.")
        plan, labels, seen = [], [], set()
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("Некорректное изменение задачи.")
            _properties(change, TASK_FIELDS | {"operation", "task_id"})
            operation = change.get("operation")
            fields = _fields(self.db, {key: value for key, value in change.items() if key in TASK_FIELDS})
            if operation == "create":
                if "task_id" in change or not {"text", "task_date"} <= fields.keys():
                    raise ValueError("Для новой задачи нужны название и дата, без task_id.")
                fields = {"scope": "planner", "section": "Личное", "start_time": None, "done": 0, **fields}
                fields = _fields(self.db, {**fields, "done": bool(fields["done"])})
                plan.append({"operation": operation, "fields": fields})
                labels.append(f"Создать «{fields['text']}»: " + describe_fields(fields))
            elif operation == "update":
                task_id = change.get("task_id")
                if type(task_id) is not int or task_id not in self.observed or task_id in seen or not fields:
                    raise ValueError("Сначала прочитай нужную задачу; укажи её ID и изменения один раз.")
                seen.add(task_id)
                snapshot = self.observed[task_id]
                plan.append({"operation": operation, "task_id": task_id, "before": snapshot, "fields": fields})
                labels.append(f"Изменить «{snapshot['text']}» (#{task_id}): " + describe_fields(fields))
            else:
                raise ValueError("Поддерживаются только create и update.")
        proposal_id = uuid.uuid4().hex
        self.db.execute("INSERT INTO assistant_task_proposals(id,payload,created_at) VALUES(?,?,?)", (proposal_id, json.dumps(plan, ensure_ascii=False), time.time()))
        self.db.commit()
        # Stop before another model/tool step; no model-generated success claim.
        preview = "\n".join(labels)
        raise ConfirmationRequired({"ok": True, "action": "needs_confirmation", "confirmation_id": proposal_id,
                                    "confirmation_label": preview, "reply": "Предлагаю изменения:\n" + preview + "\nПодтверди или отмени этот список. Пока ничего не изменено."})


def confirm_proposal(db, proposal_id: str, approved: bool) -> dict:
    """Claim once and apply the complete proposal in one SQLite transaction."""
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM assistant_task_proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None or row["status"] != "pending":
            raise ValueError("Подтверждение не найдено или уже обработано.")
        if time.time() - row["created_at"] > 600:
            raise ValueError("Подтверждение истекло. Повтори запрос.")
        if not approved:
            db.execute("UPDATE assistant_task_proposals SET status='cancelled' WHERE id=?", (proposal_id,))
            db.commit()
            return {"ok": True, "action": "cancelled", "reply": "Изменения отменены."}
        plan = json.loads(row["payload"])
        for change in plan:
            if change["operation"] == "update":
                current = db.execute("SELECT * FROM tasks WHERE id=?", (change["task_id"],)).fetchone()
                if current is None or dict(current) != change["before"]:
                    raise ValueError("Задача изменилась после предложения. Ничего не применено; повтори запрос.")
            _fields(db, {**change["fields"], "done": bool(change["fields"]["done"])} if "done" in change["fields"] else change["fields"])
        ids = []
        timestamp = datetime.now().isoformat(timespec="microseconds")
        for change in plan:
            fields = change["fields"]
            if change["operation"] == "create":
                cursor = db.execute("INSERT INTO tasks(task_date,text,section,scope,start_time,done,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (fields["task_date"], fields["text"], fields["section"], fields["scope"], fields["start_time"], fields["done"], timestamp, timestamp))
                ids.append(cursor.lastrowid)
            else:
                task_id = change["task_id"]
                db.execute("UPDATE tasks SET " + ",".join(f"{key}=?" for key in fields) + ",updated_at=? WHERE id=?", [*fields.values(), timestamp, task_id])
                ids.append(task_id)
        db.execute("UPDATE assistant_task_proposals SET status='applied' WHERE id=?", (proposal_id,))
        db.commit()
        return {"ok": True, "action": "task_changes", "task_ids": ids, "reply": f"Готово. Применено изменений задач: {len(plan)}."}
    except Exception:
        db.rollback()
        raise
