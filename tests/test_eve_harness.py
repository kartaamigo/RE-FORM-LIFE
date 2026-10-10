from __future__ import annotations

import copy
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app as app_module
from eve_harness import ConfirmationRequired, EveHarness, confirm_proposal, relevant_memories, tool_declarations
from eve_local import LocalProviderError, generate_gemini_reply


def model_reply(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def model_calls(*calls):
    return {"candidates": [{"content": {"parts": [
        {"functionCall": {"name": name, "args": args}, "thoughtSignature": "provider-signature"}
        for name, args in calls
    ]}}]}


class ToolLoopTests(unittest.TestCase):
    def test_reads_results_then_answers_and_preserves_signature(self):
        requests = []
        replies = iter([model_calls(("list_tasks", {"done": False})), model_reply("На сегодня две задачи.")])

        def provider(*args, **kwargs):
            requests.append(copy.deepcopy(kwargs["payload"]))
            return next(replies)

        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", side_effect=provider):
            result = generate_gemini_reply("Помоги с планами", context="Сегодня 2026-10-10", tools=tool_declarations(False), execute_tool=lambda name, args: {"ok": True, "tasks": ["работа", "прогулка"]})
        self.assertIn("две задачи", result)
        contents = requests[-1]["contents"]
        self.assertEqual(contents[-2]["parts"][0]["thoughtSignature"], "provider-signature")
        self.assertEqual(contents[-1]["parts"][0]["functionResponse"]["response"]["tasks"], ["работа", "прогулка"])
        self.assertIn("2026-10-10", requests[0]["systemInstruction"]["parts"][0]["text"])

    def test_unknown_or_malformed_tool_never_executes(self):
        for name, args in [("exec", {"command": "whoami"}), (["list_tasks"], {}), ("list_tasks", [])]:
            with self.subTest(name=name), patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", return_value=model_calls((name, args))), patch("eve_harness.EveHarness.execute") as execute:
                with self.assertRaises(LocalProviderError):
                    generate_gemini_reply("привет", tools=tool_declarations(False), execute_tool=execute)
                execute.assert_not_called()

    def test_tools_are_not_available_to_plain_provider_call(self):
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", return_value=model_calls(("list_tasks", {}))):
            with self.assertRaises(LocalProviderError):
                generate_gemini_reply("привет")

    def test_tool_validation_error_goes_back_to_model(self):
        requests = []
        replies = iter([model_calls(("list_tasks", {"start": "bad"})), model_reply("На какую дату нужен план?")])

        def provider(*args, **kwargs):
            requests.append(copy.deepcopy(kwargs["payload"]))
            return next(replies)

        def execute(*args):
            raise ValueError("Некорректная дата")

        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", side_effect=provider):
            self.assertIn("дату", generate_gemini_reply("планы", tools=tool_declarations(False), execute_tool=execute))
        self.assertFalse(requests[-1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["ok"])

    def test_run_and_call_limits_stop_loop(self):
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", return_value=model_calls(("list_tasks", {}))) as provider, patch("eve_harness.EveHarness.execute", return_value={"ok": True}) as execute:
            with self.assertRaises(LocalProviderError):
                generate_gemini_reply("планы", tools=tool_declarations(False), execute_tool=execute)
            self.assertEqual(provider.call_count, 4)
            self.assertEqual(execute.call_count, 3)
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", return_value=model_calls(*[("list_tasks", {})] * 9)), patch("eve_harness.EveHarness.execute") as execute:
            with self.assertRaises(LocalProviderError):
                generate_gemini_reply("планы", tools=tool_declarations(False), execute_tool=execute)
            execute.assert_not_called()

    def test_deadline_stops_before_request(self):
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local.time.monotonic", side_effect=[0, 61]), patch("eve_local._json_request") as provider:
            with self.assertRaises(LocalProviderError):
                generate_gemini_reply("привет")
            provider.assert_not_called()

    def test_relevant_memory_is_bounded(self):
        facts = ["я люблю бегать " + str(i) for i in range(100)] + ["У меня кот Барсик"]
        selected = relevant_memories("Как поживает Барсик?", facts, budget=100)
        self.assertEqual(selected[0], "У меня кот Барсик")
        self.assertLessEqual(sum(map(len, selected)), 100)


class HarnessApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_database = app_module.app.config["DATABASE"]
        self.previous_testing = app_module.app.config.get("TESTING")
        app_module.app.config.update(DATABASE=str(Path(self.temp.name) / "eve.sqlite3"), TESTING=True)
        app_module.assistant_pending_actions.clear()
        app_module._recent_voice_commands.clear()
        self.client = app_module.app.test_client()
        self.today = date.today().isoformat()
        self.tomorrow = (date.today() + timedelta(days=1)).isoformat()

    def tearDown(self):
        app_module.app.config.update(DATABASE=self.previous_database, TESTING=self.previous_testing)
        self.temp.cleanup()

    def task(self, text="Купить молоко"):
        result = self.client.post("/api/tasks", json={"text": text, "task_date": self.today}).get_json()
        return result["task"]

    def proposal(self, changes):
        with app_module.app.app_context():
            harness = EveHarness(app_module.get_db(), [], allow_changes=True)
            harness.execute("list_tasks", {})
            with self.assertRaises(ConfirmationRequired) as raised:
                harness.execute("propose_task_changes", {"changes": changes})
            return raised.exception.payload

    def test_free_request_reads_tasks_and_stores_exchange(self):
        task = self.task()
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", side_effect=[model_calls(("list_tasks", {"done": False})), model_reply("Сегодня нужно купить молоко.")]):
            response = self.client.post("/api/assistant/command", json={"text": "Помоги разобраться с моими делами"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("молоко", response.get_json()["reply"])
        self.assertEqual(self.client.get("/api/tasks").get_json()["tasks"][0]["id"], task["id"])
        history = self.client.get("/api/assistant/history").get_json()["messages"]
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])

    def test_model_proposal_stops_before_final_reply_and_does_not_write(self):
        task = self.task()
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", side_effect=[model_calls(("list_tasks", {})), model_calls(("propose_task_changes", {"changes": [{"operation": "update", "task_id": task["id"], "task_date": self.tomorrow}]}))]) as provider:
            response = self.client.post("/api/assistant/command", json={"text": "Помоги разгрузить мой день"})
        payload = response.get_json()
        self.assertEqual(payload["action"], "needs_confirmation")
        self.assertEqual(provider.call_count, 2)
        self.assertIn(self.tomorrow, payload["confirmation_label"])
        self.assertEqual(self.client.get("/api/tasks").get_json()["tasks"][0]["task_date"], self.today)
        confirmed = self.client.post("/api/assistant/confirm", json={"confirmation_id": payload["confirmation_id"], "approved": True})
        self.assertEqual(confirmed.get_json()["action"], "task_changes")
        self.assertEqual(self.client.get("/api/tasks").get_json()["tasks"][0]["task_date"], self.tomorrow)

    def test_proposal_survives_new_connection_and_applies_once(self):
        task = self.task()
        proposal = self.proposal([{"operation": "update", "task_id": task["id"], "done": True}, {"operation": "create", "text": "Прогулка", "task_date": self.tomorrow}])
        restored = self.client.get("/api/assistant/proposals/pending").get_json()["proposal"]
        self.assertEqual(restored["id"], proposal["confirmation_id"])
        first = self.client.post("/api/assistant/confirm", json={"confirmation_id": restored["id"], "approved": True})
        second = self.client.post("/api/assistant/confirm", json={"confirmation_id": restored["id"], "approved": True})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        tasks = self.client.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(next(item for item in tasks if item["id"] == task["id"])["done"])

    def test_stale_batch_applies_nothing(self):
        first, second = self.task("Первое дело"), self.task("Второе дело")
        proposal = self.proposal([{"operation": "update", "task_id": first["id"], "done": True}, {"operation": "update", "task_id": second["id"], "done": True}, {"operation": "create", "text": "Новое дело", "task_date": self.today}])
        self.client.patch(f"/api/tasks/{second['id']}", json={"text": "Уже изменено"})
        result = self.client.post("/api/assistant/confirm", json={"confirmation_id": proposal["confirmation_id"], "approved": True})
        self.assertEqual(result.status_code, 409)
        tasks = self.client.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(not task["done"] for task in tasks))

    def test_cancellation_expiry_and_superseded_proposals(self):
        changes = [{"operation": "create", "text": "Новое дело", "task_date": self.today}]
        old = self.proposal(changes)
        current = self.proposal(changes)
        self.assertEqual(self.client.post("/api/assistant/confirm", json={"confirmation_id": old["confirmation_id"], "approved": True}).status_code, 409)
        cancelled = self.client.post("/api/assistant/confirm", json={"confirmation_id": current["confirmation_id"], "approved": False})
        self.assertEqual(cancelled.get_json()["action"], "cancelled")
        expired = self.proposal(changes)
        with app_module.app.app_context():
            db = app_module.get_db()
            db.execute("UPDATE assistant_task_proposals SET created_at=? WHERE id=?", (time.time() - 601, expired["confirmation_id"]))
            db.commit()
        self.assertEqual(self.client.post("/api/assistant/confirm", json={"confirmation_id": expired["confirmation_id"], "approved": True}).status_code, 409)
        self.assertEqual(self.client.get("/api/tasks").get_json()["tasks"], [])

    def test_read_only_chat_cannot_propose_changes(self):
        with patch("eve_local._gemini_api_key", return_value="test"), patch("eve_local._json_request", return_value=model_calls(("propose_task_changes", {"changes": [{"operation": "create", "text": "Дело", "task_date": self.today}]}))):
            result = self.client.post("/api/assistant/chat", json={"text": "Помоги с делами"})
        self.assertEqual(result.status_code, 503)
        self.assertIsNone(self.client.get("/api/assistant/proposals/pending").get_json()["proposal"])

    def test_disabled_ai_keeps_commands_local(self):
        self.client.patch("/api/assistant/settings", json={"gemini_enabled": False})
        with patch.object(app_module, "generate_gemini_reply") as provider:
            result = self.client.post("/api/assistant/command", json={"text": "добавь задачу купить хлеб на завтра"})
            self.assertEqual(result.get_json()["action"], "create_task")
            self.client.post("/api/assistant/command", json={"text": "Помоги подумать"})
            provider.assert_not_called()

    def test_disabled_personalization_hides_memory_from_tools(self):
        self.client.post("/api/assistant/command", json={"text": "запомни что я люблю прогулки"})
        self.client.patch("/api/assistant/settings", json={"personalization_enabled": False})

        def provider(text, model, history, memories, **kwargs):
            self.assertEqual(memories, [])
            self.assertEqual(kwargs["execute_tool"]("search_memories", {"query": "прогулки"})["facts"], [])
            return "Какие занятия тебе нравятся?"

        with patch.object(app_module, "generate_gemini_reply", side_effect=provider):
            self.assertEqual(self.client.post("/api/assistant/command", json={"text": "Помоги выбрать занятие"}).status_code, 200)

    def test_task_lookup_is_case_insensitive_and_validates_inputs(self):
        task = self.task()
        with app_module.app.app_context():
            harness = EveHarness(app_module.get_db(), [], True)
            self.assertEqual(harness.execute("list_tasks", {"query": "МОЛОКО"})["tasks"][0]["id"], task["id"])
            for args in [{"scope": []}, {"done": "true"}, {"offset": -1}, {"start": "2026-02-30"}, {"sql": "DROP TABLE tasks"}]:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    harness.execute("list_tasks", args)
            fresh = EveHarness(app_module.get_db(), [], True)
            with self.assertRaises(ValueError):
                fresh.execute("propose_task_changes", {"changes": [{"operation": "update", "task_id": task["id"], "done": True}]})

    def test_finance_and_utility_tools_return_real_data_without_identifiers(self):
        with app_module.app.app_context():
            db = app_module.get_db()
            stamp = "2026-10-10T12:00:00"
            for kind, amount in [("income", 10000), ("expense", 2500)]:
                db.execute("INSERT INTO transactions(kind,amount_minor,category,transaction_date,created_at,updated_at) VALUES(?,?,?,?,?,?)", (kind, amount, "Личное", "2026-10-10", stamp, stamp))
            account = db.execute("INSERT INTO utility_accounts(name,address,account_number,created_at,updated_at) VALUES(?,?,?,?,?)", ("Дом", "Секретный адрес", "SECRET", stamp, stamp)).lastrowid
            db.execute("INSERT INTO utility_payments(account_id,billing_month,due_date,amount_minor,created_at,updated_at) VALUES(?,?,?,?,?,?)", (account, "2026-10", "2026-10-20", 15000, stamp, stamp))
            db.commit()
            harness = EveHarness(db, [])
            self.assertEqual(harness.execute("finance_summary", {"month": "2026-10"})["balance_minor"], 7500)
            result = harness.execute("utility_payments", {"month": "2026-10"})
            self.assertEqual(result["payments"][0]["amount_minor"], 15000)
            self.assertNotIn("SECRET", str(result))
            self.assertNotIn("Секретный адрес", str(result))

    def test_clear_history_cancels_pending_proposal(self):
        self.proposal([{"operation": "create", "text": "Дело", "task_date": self.today}])
        self.client.delete("/api/assistant/history")
        self.assertIsNone(self.client.get("/api/assistant/proposals/pending").get_json()["proposal"])

    def test_voice_confirmation_uses_durable_proposal(self):
        self.proposal([{"operation": "create", "text": "Дело", "task_date": self.today}])
        response = self.client.post("/api/assistant/command", json={"text": "подтверждаю"})
        self.assertEqual(response.get_json()["action"], "task_changes")

    def test_overlapping_model_runs_are_rejected_and_lock_is_released(self):
        app_module._assistant_harness_lock.acquire()
        try:
            with patch.object(app_module, "generate_gemini_reply") as provider:
                result = self.client.post("/api/assistant/chat", json={"text": "привет"})
                self.assertEqual(result.status_code, 503)
                provider.assert_not_called()
        finally:
            app_module._assistant_harness_lock.release()
        with patch.object(app_module, "generate_gemini_reply", side_effect=LocalProviderError("сбой")):
            self.client.post("/api/assistant/chat", json={"text": "привет"})
        self.assertFalse(app_module._assistant_harness_lock.locked())

    def test_ambiguous_task_command_does_not_pick_first_match(self):
        self.task("Купить молоко")
        self.task("Купить молоко и хлеб")
        with patch.object(app_module, "generate_gemini_reply", return_value="Какую из двух задач отметить?") as provider:
            result = self.client.post("/api/assistant/command", json={"text": "отметь задачу купить выполненной"})
        self.assertEqual(result.get_json()["action"], "gemini_reply")
        provider.assert_called_once()
        self.assertTrue(all(not task["done"] for task in self.client.get("/api/tasks").get_json()["tasks"]))

    def test_bulk_command_can_use_harness(self):
        self.task()
        with patch.object(app_module, "generate_gemini_reply", return_value="Проверяю задачи.") as provider:
            self.client.post("/api/assistant/command", json={"text": "перенеси все незавершённые задачи на завтра"})
        provider.assert_called_once()

    def test_habit_tool_reads_saved_completion(self):
        with app_module.app.app_context():
            db = app_module.get_db()
            habit = db.execute("INSERT INTO habits(name,created_at,updated_at) VALUES(?,?,?)", ("Прогулка", self.today, self.today)).lastrowid
            db.execute("INSERT INTO habit_entries(habit_id,entry_date,done) VALUES(?,?,1)", (habit, self.today))
            db.commit()
            result = EveHarness(db, []).execute("list_habits", {"date": self.today})
            self.assertEqual(result["habits"][0]["done"], 1)

    def test_database_failure_rolls_back_whole_batch(self):
        proposal = self.proposal([{"operation": "create", "text": "Первое дело", "task_date": self.today}, {"operation": "create", "text": "Второе дело", "task_date": self.today}])
        with app_module.app.app_context():
            db = app_module.get_db()
            db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON tasks WHEN NEW.text='Второе дело' BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
            db.commit()
            with self.assertRaises(Exception):
                confirm_proposal(db, proposal["confirmation_id"], True)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM assistant_task_proposals WHERE id=?", (proposal["confirmation_id"],)).fetchone()[0], "pending")


if __name__ == "__main__":
    unittest.main()
