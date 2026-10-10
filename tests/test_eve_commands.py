from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from eve_assistant import parse_command
from eve_commands import CATALOG, SUPPORTED_INTENTS


class UserCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = app_module.app.config["DATABASE"]
        self.previous_testing = app_module.app.config["TESTING"]
        app_module.app.config.update(DATABASE=str(Path(self.temp.name) / "test.sqlite3"), TESTING=True)
        app_module.assistant_pending_actions.clear()
        app_module._recent_voice_commands.clear()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.app.config.update(DATABASE=self.previous_db, TESTING=self.previous_testing)
        self.temp.cleanup()

    def definition(self, **fields):
        return {"name": "Мой план", "phrase": "Старт дня", "template": "покажи план на сегодня", "mode": "command", "enabled": True, **fields}

    def create(self, **fields):
        result = self.client.post("/api/assistant/commands", json=self.definition(**fields))
        self.assertEqual(result.status_code, 201, result.get_json())
        return result.get_json()["command"]

    def test_catalog_examples_are_supported_and_editor_is_rendered(self):
        result = self.client.get("/api/assistant/commands").get_json()
        self.assertEqual(len(result["catalog"]), len(CATALOG))
        for item in CATALOG:
            if not item["requires_ai"]:
                self.assertIn(parse_command(item["text"]).intent, SUPPORTED_INTENTS)
        html = self.client.get("/assistant").get_data(as_text=True)
        self.assertIn('id="assistantCustomCommandForm"', html)
        self.assertIn('js/eve-commands.js', html)

    def test_custom_phrase_works_offline_and_preserves_original_history(self):
        self.create()
        self.client.patch("/api/assistant/settings", json={"gemini_enabled": False})
        with patch.object(app_module, "generate_gemini_reply") as model:
            result = self.client.post("/api/assistant/command", json={"text": "Эва, СТАРТ ДНЯ!"})
        self.assertEqual(result.get_json()["action"], "list_day")
        model.assert_not_called()
        history = self.client.get("/api/assistant/history").get_json()["messages"]
        self.assertEqual(history[-2]["text"], "Эва, СТАРТ ДНЯ!")

    def test_parameterized_phrase_preserves_task_text(self):
        self.create(name="Быстрое дело", phrase="Быстрое дело", template="добавь задачу {text} на завтра")
        result = self.client.post("/api/assistant/command", json={"text": "Эва, быстрое дело Купить Молоко"}).get_json()
        self.assertEqual(result["action"], "create_task")
        self.assertEqual(result["task"]["text"].casefold(), "купить молоко")
        missing = self.client.post("/api/assistant/command", json={"text": "быстрое дело"})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(len(self.client.get("/api/tasks").get_json()["tasks"]), 1)

    def test_edit_disable_and_delete(self):
        command = self.create()
        command_id = command["id"]
        saved = self.client.patch(f"/api/assistant/commands/{command_id}", json={"template": "покажи план на завтра", "enabled": False})
        self.assertFalse(saved.get_json()["command"]["enabled"])
        with patch.object(app_module, "generate_gemini_reply", return_value="Команда выключена."):
            self.assertEqual(self.client.post("/api/assistant/command", json={"text": "старт дня"}).get_json()["action"], "gemini_reply")
        self.client.patch(f"/api/assistant/commands/{command_id}", json={"enabled": True})
        self.assertEqual(self.client.post("/api/assistant/command", json={"text": "старт дня"}).get_json()["action"], "list_day")
        self.assertEqual(self.client.delete(f"/api/assistant/commands/{command_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/assistant/commands").get_json()["commands"], [])

    def test_prompt_uses_harness_and_respects_ai_setting(self):
        self.create(template="Помоги составить план завтра по моим задачам", mode="prompt")
        with patch.object(app_module, "generate_gemini_reply", return_value="Вот твой план.") as model:
            result = self.client.post("/api/assistant/command", json={"text": "старт дня"})
        self.assertEqual(result.get_json()["action"], "gemini_reply")
        self.assertIn("Помоги", model.call_args.args[0])
        self.assertIn("tools", model.call_args.kwargs)
        self.client.patch("/api/assistant/settings", json={"gemini_enabled": False})
        with patch.object(app_module, "generate_gemini_reply") as model:
            result = self.client.post("/api/assistant/command", json={"text": "старт дня"})
        self.assertEqual(result.get_json()["action"], "gemini_unavailable")
        model.assert_not_called()

    def test_existing_confirmations_are_not_bypassed(self):
        self.create(template="создай папку Documents/Команды EVE")
        with patch.object(app_module, "execute_pending_action") as execute:
            result = self.client.post("/api/assistant/command", json={"text": "старт дня"}).get_json()
        self.assertEqual(result["action"], "needs_confirmation")
        execute.assert_not_called()

    def test_reserved_phrases_shell_and_unknown_fields_are_rejected(self):
        definitions = [self.definition(phrase="да"), self.definition(phrase="покажи план на сегодня"), self.definition(phrase="Эва мой план"), self.definition(template="выполни команду whoami"), self.definition(template="делай произвольный скрипт"), self.definition(template="покажи {date}"), self.definition(template="{text} {text}"), self.definition(enabled="false"), self.definition(phrase="."), self.definition(script="whoami")]
        with patch.object(app_module.subprocess, "run") as execute:
            for definition in definitions:
                with self.subTest(definition=definition):
                    self.assertEqual(self.client.post("/api/assistant/commands", json=definition).status_code, 400)
            execute.assert_not_called()
        self.assertEqual(self.client.get("/api/assistant/commands").get_json()["commands"], [])

    def test_duplicate_phrase_is_rejected_case_insensitively(self):
        self.create()
        result = self.client.post("/api/assistant/commands", json=self.definition(phrase="СТАРТ   ДНЯ"))
        self.assertEqual(result.status_code, 400)
        self.assertEqual(len(self.client.get("/api/assistant/commands").get_json()["commands"]), 1)

    def test_export_import_roundtrip_and_atomic_conflict(self):
        command = self.create()
        exported = self.client.get("/api/assistant/commands/export").get_json()
        self.assertNotIn("id", exported["commands"][0])
        self.client.delete(f"/api/assistant/commands/{command['id']}")
        self.assertEqual(self.client.post("/api/assistant/commands/import", json=exported).status_code, 201)
        conflict = {"version": 1, "commands": [self.definition(phrase="Вечерний итог"), self.definition()]}
        self.assertEqual(self.client.post("/api/assistant/commands/import", json=conflict).status_code, 400)
        self.assertEqual(len(self.client.get("/api/assistant/commands").get_json()["commands"]), 1)

    def test_import_validates_entire_pack_without_running_commands(self):
        payload = {"version": 1, "commands": [self.definition(), self.definition(phrase="Новая фраза", template="выполни команду whoami")]}
        with patch.object(app_module.subprocess, "run") as execute:
            self.assertEqual(self.client.post("/api/assistant/commands/import", json=payload).status_code, 400)
            execute.assert_not_called()
        self.assertEqual(self.client.get("/api/assistant/commands").get_json()["commands"], [])

    def test_voice_still_requires_wake_word(self):
        self.create()
        ignored = self.client.post("/api/assistant/command", json={"text": "старт дня", "source": "browser_voice"})
        self.assertEqual(ignored.get_json()["action"], "ignored")
        active = self.client.post("/api/assistant/command", json={"text": "Эва старт дня", "source": "browser_voice"})
        self.assertEqual(active.get_json()["action"], "list_day")

    def test_parameter_does_not_match_prefix_of_word(self):
        self.create(phrase="Быстрое", template="добавь задачу {text} на завтра")
        with patch.object(app_module, "generate_gemini_reply", return_value="Расскажи подробнее."):
            result = self.client.post("/api/assistant/command", json={"text": "быстроеходное судно"})
        self.assertEqual(result.get_json()["action"], "gemini_reply")

    def test_local_alias_does_not_send_missing_task_to_model(self):
        self.create(template="отметь задачу купить молоко выполненной")
        with patch.object(app_module, "generate_gemini_reply") as model:
            result = self.client.post("/api/assistant/command", json={"text": "старт дня"})
        self.assertEqual(result.get_json()["action"], "not_found")
        model.assert_not_called()

    def test_starter_pack_import_and_empty_export(self):
        empty = self.client.get("/api/assistant/commands/export").get_json()
        self.assertEqual(self.client.post("/api/assistant/commands/import", json=empty).get_json()["imported"], 0)
        path = Path(__file__).resolve().parents[1] / "docs" / "examples" / "eve-commands.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        result = self.client.post("/api/assistant/commands/import", json=data)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.get_json()["imported"], 3)


if __name__ == "__main__":
    unittest.main()
