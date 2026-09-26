from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app as app_module
from eve_assistant import choose_command_candidate, parse_command
from eve_local import LocalProviderError, _write_pcm_wav, available_tts_voices, build_profile, generate_local_reply, strip_reasoning


class EveParserTests(unittest.TestCase):
    def test_local_reasoning_markup_is_not_shown_to_user(self):
        self.assertEqual(strip_reasoning("<think>внутренний план</think>Готово."), "Готово.")
        self.assertEqual(strip_reasoning("<think>незавершённое рассуждение"), "")

    def test_local_chat_request_includes_recent_conversation_context(self):
        with patch(
            "eve_local._json_request",
            return_value={"message": {"content": "Помню, ты говорила про поездку."}},
        ) as request:
            reply = generate_local_reply(
                "а что я говорила?",
                history=[{"role": "user", "text": "Я планирую поездку."}, {"role": "assistant", "text": "Куда хочешь поехать?"}],
            )
        payload = request.call_args.kwargs["payload"]
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertEqual(payload["messages"][-3]["content"], "Я планирую поездку.")
        self.assertEqual(payload["messages"][-2]["content"], "Куда хочешь поехать?")
        self.assertEqual(payload["messages"][-1]["content"], "а что я говорила?")
        self.assertIn("Помню", reply)

    def test_personal_voice_profile_has_female_samples_and_valid_wav(self):
        self.assertEqual(build_profile(), "personal")
        self.assertEqual([voice["id"] for voice in available_tts_voices()], ["eve-suit", "xenia", "kseniya", "baya"])
        payload = _write_pcm_wav([0.0, 0.25, -0.25], 48000)
        import wave
        import io

        with wave.open(io.BytesIO(payload), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 48000)
            self.assertEqual(wav_file.getnframes(), 3)
            self.assertEqual(wav_file.getsampwidth(), 2)

    def test_wav_serializer_rejects_non_finite_audio(self):
        with self.assertRaises(LocalProviderError):
            _write_pcm_wav([0.0, float("nan"), 0.1], 48000)

    def test_commercial_profile_exposes_only_qwen_voice(self):
        with patch("eve_local.build_profile", return_value="commercial"):
            self.assertEqual([voice["id"] for voice in available_tts_voices()], ["qwen-design"])

    def test_voice_command_keeps_time_and_resolves_relative_date(self):
        parsed = parse_command(
            "Эва, добавь задачу купить молоко на завтра в 19:30",
            date(2026, 9, 25),
        )
        self.assertEqual(parsed.intent, "create_task")
        self.assertEqual(parsed.task_text, "купить молоко")
        self.assertEqual(parsed.task_date, "2026-09-26")
        self.assertEqual(parsed.start_time, "19:30")

    def test_week_and_generic_completion_commands(self):
        week = parse_command("покажи план на следующую неделю", date(2026, 9, 25))
        self.assertEqual(week.intent, "open_planner")
        self.assertEqual(week.task_date, "2026-10-02")
        complete = parse_command("отметь задачу выполненной", date(2026, 9, 25))
        self.assertEqual(complete.intent, "complete_task")
        self.assertEqual(complete.query, "")

    def test_task_board_and_column_are_parsed(self):
        parsed = parse_command(
            "добавь задачу в раздел задачи доделать дз в стол учеба",
            date(2026, 9, 25),
        )
        self.assertEqual(parsed.intent, "create_task")
        self.assertEqual(parsed.task_text, "доделать дз")
        self.assertEqual(parsed.scope, "tasks")
        self.assertEqual(parsed.section, "учеба")

    def test_safe_external_commands_are_parsed(self):
        explorer = parse_command("Эва, открой проводник в загрузки")
        self.assertEqual(explorer.intent, "open_explorer")
        self.assertEqual(explorer.target, "загрузки")
        browser = parse_command("запусти браузер")
        self.assertEqual(browser.intent, "open_browser")
        url = parse_command("открой https://example.com")
        self.assertEqual(url.intent, "open_url")
        self.assertEqual(url.target, "https://example.com")
        finance = parse_command("добавь расход 500 на продукты")
        self.assertEqual(finance.intent, "finance_transaction")
        self.assertEqual(finance.finance_kind, "expense")
        self.assertEqual(parse_command("поставь громкость на 40").intent, "set_volume")
        self.assertEqual(parse_command("выключи Wi-Fi").intent, "toggle_wifi")
        self.assertEqual(parse_command("выключи компьютер на Mac").intent, "shutdown")

    def test_display_audio_and_file_creation_commands_are_parsed(self):
        quieter = parse_command("убавь громкость на 10")
        self.assertEqual((quieter.intent, quieter.target), ("adjust_volume", "-10"))
        brighter = parse_command("увеличь яркость на 15")
        self.assertEqual((brighter.intent, brighter.target), ("adjust_brightness", "15"))
        brightness = parse_command("поставь яркость на 60")
        self.assertEqual((brightness.intent, brightness.target), ("set_brightness", "60"))
        created = parse_command("создай файл Documents/заметка.txt с текстом купить молоко")
        self.assertEqual(created.intent, "create_file")
        self.assertEqual(created.target, "Documents/заметка.txt")
        self.assertEqual(created.content, "купить молоко")

    def test_voice_typos_and_recognition_alternatives_resolve_to_commands(self):
        typo = parse_command("аткрой ютуб")
        self.assertEqual(typo.intent, "open_url")
        self.assertEqual(typo.target, "https://www.youtube.com")
        selected = choose_command_candidate("неразборчивая фраза", ["открой ютуб", "открой видео"])
        self.assertEqual(selected, "открой ютуб")

    def test_weather_search_sites_and_named_browsers_are_parsed(self):
        weather = parse_command("Какая погода в Москве")
        self.assertEqual(weather.intent, "weather")
        self.assertEqual(weather.target, "москве")

        search = parse_command("Найди в Яндексе интересные места рядом")
        self.assertEqual(search.intent, "search_web")
        self.assertEqual(search.target, "интересные места рядом")
        self.assertEqual(search.search_engine, "yandex")

        browser_search = parse_command("Найди погоду через Google Chrome браузер")
        self.assertEqual(browser_search.intent, "search_web")
        self.assertEqual(browser_search.target, "погоду")
        self.assertEqual(browser_search.browser, "chrome")

        site = parse_command("Открой YouTube в Яндекс Браузере")
        self.assertEqual(site.intent, "open_url")
        self.assertEqual(site.target, "https://www.youtube.com")
        self.assertEqual(site.browser, "yandex")

        browser = parse_command("Открой Google Chrome браузер")
        self.assertEqual(browser.intent, "open_browser")
        self.assertEqual(browser.browser, "chrome")

        spotify = parse_command("Открой Спотифай в браузере")
        self.assertEqual(spotify.intent, "open_url")
        self.assertEqual(spotify.target, "https://open.spotify.com")

    def test_personal_memory_commands_are_parsed(self):
        remember = parse_command("Запомни, что я люблю прогулки вечером")
        self.assertEqual(remember.intent, "remember_fact")
        self.assertEqual(remember.target, "я люблю прогулки вечером")
        self.assertEqual(parse_command("Что ты помнишь обо мне").intent, "list_memories")
        forget = parse_command("Забудь, что я люблю прогулки вечером")
        self.assertEqual(forget.intent, "forget_fact")


class PlannerAndUtilitiesApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_database = app_module.app.config["DATABASE"]
        app_module.app.config["TESTING"] = True
        app_module.app.config["DATABASE"] = str(Path(self.temp_dir.name) / "test.sqlite3")
        app_module.assistant_pending_actions.clear()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.app.config["DATABASE"] = self.previous_database
        self.temp_dir.cleanup()

    def test_planner_voice_create_and_complete(self):
        tomorrow = date.today() + timedelta(days=1)
        created = self.client.post(
            "/api/assistant/command",
            json={"text": "Эва, добавь задачу купить молоко на завтра в 19:30"},
        )
        self.assertEqual(created.status_code, 201)
        task = created.get_json()["task"]
        self.assertEqual(task["task_date"], tomorrow.isoformat())
        self.assertEqual(task["start_time"], "19:30")

        completed = self.client.post(
            "/api/assistant/command",
            json={"text": "Эва, отметь задачу купить молоко выполненной"},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.get_json()["action"], "complete_task")

        listed = self.client.get(f"/api/tasks?scope=planner&start={tomorrow}&end={tomorrow}")
        self.assertTrue(listed.get_json()["tasks"][0]["done"])

    def test_assistant_can_create_task_in_tasks_board_and_column(self):
        created = self.client.post(
            "/api/assistant/command",
            json={"text": "добавь задачу в раздел задачи доделать дз в стол учеба"},
        )
        self.assertEqual(created.status_code, 201)
        payload = created.get_json()
        self.assertEqual(payload["task"]["scope"], "tasks")
        self.assertEqual(payload["task"]["section"], "Учёба")
        self.assertIn("раздел «Задачи»", payload["reply"])
        listed = self.client.get("/api/tasks?scope=tasks").get_json()["tasks"]
        self.assertEqual(listed[0]["text"], "доделать дз")

        completed = self.client.post(
            "/api/assistant/command",
            json={"text": "отметь задачу доделать дз выполненной"},
        )
        self.assertEqual(completed.get_json()["action"], "complete_task")
        self.assertTrue(self.client.get("/api/tasks?scope=tasks").get_json()["tasks"][0]["done"])

    def test_assistant_external_command_uses_safe_adapter(self):
        with patch.object(
            app_module,
            "perform_external_action",
            return_value={"location": "downloads", "path": "/tmp/Downloads"},
        ) as open_action:
            response = self.client.post(
                "/api/assistant/command",
                json={"text": "Эва, открой проводник в загрузки"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "open_explorer")
        self.assertIn("Загрузки", response.get_json()["reply"])
        open_action.assert_called_once_with("open_explorer", "загрузки")

    def test_assistant_uses_voice_alternative_and_requested_browser(self):
        with patch.object(
            app_module,
            "perform_external_action",
            return_value={"location": "browser", "path": "https://www.youtube.com", "reply": "Открываю сайт."},
        ) as open_action:
            response = self.client.post(
                "/api/assistant/command",
                json={
                    "text": "неразборчивая фраза",
                    "alternatives": ["открой YouTube в Яндекс Браузере"],
                    "source": "browser_voice",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "open_url")
        open_action.assert_called_once_with(
            "open_url",
            "https://www.youtube.com",
            browser="yandex",
            search_engine="",
        )

    def test_assistant_history_is_stored_in_database(self):
        response = self.client.post(
            "/api/assistant/command",
            json={"text": "покажи план на сегодня"},
        )
        self.assertEqual(response.status_code, 200)
        history = self.client.get("/api/assistant/history").get_json()["messages"]
        self.assertEqual([item["role"] for item in history[-2:]], ["user", "assistant"])
        self.assertEqual(history[-2]["text"], "покажи план на сегодня")
        self.assertTrue("План на" in history[-1]["text"] or "свободен" in history[-1]["text"])

        cleared = self.client.delete("/api/assistant/history")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(self.client.get("/api/assistant/history").get_json()["messages"], [])

    def test_separate_chat_never_executes_commands(self):
        with patch.object(app_module, "generate_local_reply", return_value="Привет! У меня всё хорошо."), patch.object(
            app_module, "perform_external_action"
        ) as external:
            response = self.client.post("/api/assistant/chat", json={"text": "Открой Ютуб и расскажи, как дела"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "conversation_reply")
        external.assert_not_called()
        history = self.client.get("/api/assistant/chat/history").get_json()["messages"]
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])

    def test_brightness_volume_and_file_request_use_safe_paths(self):
        with patch.object(app_module, "perform_external_action", return_value={"location": "display", "path": "60", "reply": "Яркость установлена."}) as external:
            response = self.client.post("/api/assistant/command", json={"text": "поставь яркость на 60"})
        self.assertEqual(response.get_json()["action"], "set_brightness")
        external.assert_called_once_with("set_brightness", "60")

        request = self.client.post(
            "/api/assistant/command",
            json={"text": "создай файл Documents/заметка.txt с текстом купить молоко"},
        ).get_json()
        self.assertEqual(request["action"], "needs_confirmation")
        pending = app_module.assistant_pending_actions[request["confirmation_id"]]
        self.assertEqual(pending["content"], "купить молоко")

    def test_weather_returns_spoken_answer_without_opening_browser(self):
        with patch.object(app_module, "current_weather", return_value="Сейчас в Москве плюс 12 градусов, ясно."), patch.object(
            app_module, "perform_external_action"
        ) as external:
            response = self.client.post("/api/assistant/command", json={"text": "какая погода в Москве"})
        self.assertEqual(response.get_json()["action"], "weather")
        self.assertIn("плюс 12", response.get_json()["reply"])
        external.assert_not_called()

    def test_eve_remembers_lists_forgets_and_uses_personal_facts(self):
        remembered = self.client.post(
            "/api/assistant/command",
            json={"text": "Запомни, что я люблю прогулки вечером"},
        )
        self.assertEqual(remembered.get_json()["action"], "remember_fact")
        listed = self.client.post(
            "/api/assistant/command",
            json={"text": "Что ты помнишь обо мне"},
        ).get_json()
        self.assertIn("я люблю прогулки вечером", listed["reply"])

        with patch.object(app_module, "generate_local_reply", return_value="Тогда предложу вечернюю прогулку.") as generate:
            response = self.client.post("/api/assistant/command", json={"text": "Чем заняться?"})
        self.assertEqual(response.get_json()["action"], "local_llm_reply")
        self.assertEqual(generate.call_args.args[3], ["я люблю прогулки вечером"])

        forgotten = self.client.post(
            "/api/assistant/command",
            json={"text": "Забудь, что я люблю прогулки вечером"},
        )
        self.assertEqual(forgotten.get_json()["action"], "forget_fact")
        self.assertEqual(self.client.get("/api/assistant/memories").get_json()["memories"], [])

    def test_multiple_apartments_and_paid_date(self):
        first = self.client.post(
            "/api/utilities/accounts",
            json={"name": "Дом", "address": "ул. Первая, 1"},
        ).get_json()["account"]
        second = self.client.post(
            "/api/utilities/accounts",
            json={"name": "Квартира", "address": "ул. Вторая, 2"},
        ).get_json()["account"]
        self.assertNotEqual(first["id"], second["id"])

        month = date.today().strftime("%Y-%m")
        paid_date = (date.today() - timedelta(days=2)).isoformat()
        payment = self.client.post(
            "/api/utilities/payments",
            json={
                "account_id": first["id"],
                "billing_month": month,
                "due_date": date.today().isoformat(),
                "amount_minor": 125000,
                "status": "paid",
                "paid_date": paid_date,
            },
        )
        self.assertEqual(payment.status_code, 201)
        self.assertEqual(payment.get_json()["payment"]["paid_date"], paid_date)

        second_payment = self.client.post(
            "/api/utilities/payments",
            json={
                "account_id": second["id"],
                "billing_month": month,
                "due_date": date.today().isoformat(),
                "amount_minor": 99000,
            },
        )
        self.assertEqual(second_payment.status_code, 201)
        payments = self.client.get(f"/api/utilities/payments?month={month}").get_json()["payments"]
        self.assertEqual({item["address"] for item in payments}, {"ул. Первая, 1", "ул. Вторая, 2"})

    def test_savings_categories_operations_goals_and_archive(self):
        listed = self.client.get("/api/finance/savings/categories").get_json()["categories"]
        self.assertEqual({item["name"] for item in listed}, {"Личное", "За квартиру", "За парковку"})
        personal = next(item for item in listed if item["name"] == "Личное")

        deposit = self.client.post(
            "/api/finance/savings/operations",
            json={"category_id": personal["id"], "kind": "deposit", "amount_minor": 500000},
        )
        self.assertEqual(deposit.status_code, 201)
        too_large = self.client.post(
            "/api/finance/savings/operations",
            json={"category_id": personal["id"], "kind": "withdrawal", "amount_minor": 500001},
        )
        self.assertEqual(too_large.status_code, 400)

        withdrawal = self.client.post(
            "/api/finance/savings/operations",
            json={"category_id": personal["id"], "kind": "withdrawal", "amount_minor": 125000},
        )
        self.assertEqual(withdrawal.status_code, 201)
        summary = self.client.get("/api/finance/savings/summary").get_json()
        personal_summary = next(item for item in summary["categories"] if item["id"] == personal["id"])
        self.assertEqual(personal_summary["balance_minor"], 375000)

        planned = self.client.patch(
            f"/api/finance/savings/categories/{personal['id']}/plan",
            json={"amount_minor": 250000, "day_of_month": 15, "enabled": True},
        )
        self.assertEqual(planned.status_code, 200)
        self.assertEqual(planned.get_json()["plan"]["day_of_month"], 15)

        custom = self.client.post(
            "/api/finance/savings/categories",
            json={"name": "Путешествие", "goal_minor": 1000000},
        )
        self.assertEqual(custom.status_code, 201)
        custom_id = custom.get_json()["category"]["id"]
        archived = self.client.patch(
            f"/api/finance/savings/categories/{custom_id}",
            json={"archived": True},
        )
        self.assertEqual(archived.status_code, 200)
        active_names = {item["name"] for item in self.client.get("/api/finance/savings/categories").get_json()["categories"]}
        self.assertNotIn("Путешествие", active_names)
        all_names = {item["name"] for item in self.client.get("/api/finance/savings/categories?include_archived=1").get_json()["categories"]}
        self.assertIn("Путешествие", all_names)

    def test_savings_eve_commands_require_confirmation_and_resolve_cases(self):
        summary = self.client.post(
            "/api/assistant/command",
            json={"text": "сколько накоплено в личном"},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.get_json()["action"], "savings_summary")
        self.assertIn("Личное", summary.get_json()["reply"])

        requested = self.client.post(
            "/api/assistant/command",
            json={"text": "пополни личное на 5000"},
        )
        self.assertEqual(requested.get_json()["action"], "needs_confirmation")
        confirmation_id = requested.get_json()["confirmation_id"]
        cancelled = self.client.post(
            "/api/assistant/confirm",
            json={"confirmation_id": confirmation_id, "approved": False},
        )
        self.assertEqual(cancelled.get_json()["action"], "cancelled")

        requested = self.client.post(
            "/api/assistant/command",
            json={"text": "пополни личное на 5000"},
        )
        confirmed = self.client.post(
            "/api/assistant/confirm",
            json={"confirmation_id": requested.get_json()["confirmation_id"], "approved": True},
        )
        self.assertEqual(confirmed.get_json()["action"], "savings_operation")
        categories = self.client.get("/api/finance/savings/categories").get_json()["categories"]
        self.assertEqual(next(item for item in categories if item["name"] == "Личное")["balance_minor"], 500000)

    def test_eve_finance_commands_and_voice_confirmation(self):
        created = self.client.post(
            "/api/assistant/command",
            json={"text": "добавь расход 500 на продукты"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["action"], "finance_transaction")
        summary = self.client.post(
            "/api/assistant/command",
            json={"text": "покажи баланс"},
        )
        self.assertEqual(summary.get_json()["expense_minor"], 50000)

        requested = self.client.post(
            "/api/assistant/command",
            json={"text": "создай папку EVE test"},
        )
        self.assertEqual(requested.get_json()["action"], "needs_confirmation")
        with patch.object(
            app_module,
            "execute_pending_action",
            return_value={"action": "create_folder", "reply": "Папка создана.", "path": "/tmp/eve-test"},
        ) as execute:
            confirmed_by_voice = self.client.post(
                "/api/assistant/command",
                json={"text": "подтверждаю", "source": "background"},
            )
        execute.assert_called_once()
        self.assertEqual(confirmed_by_voice.status_code, 200)
        self.assertEqual(confirmed_by_voice.get_json()["action"], "create_folder")

    def test_utilities_services_readings_calculated_payment_and_summary(self):
        account = self.client.post(
            "/api/utilities/accounts",
            json={"name": "Дом", "address": "ул. Тестовая, 5"},
        ).get_json()["account"]
        services = self.client.get(f"/api/utilities/accounts/{account['id']}/services").get_json()["services"]
        self.assertEqual({item["name"] for item in services}, {"Электричество", "Холодная вода", "Горячая вода", "Газ"})
        custom = self.client.post(
            f"/api/utilities/accounts/{account['id']}/services",
            json={"name": "Отопление", "unit": "Гкал"},
        )
        self.assertEqual(custom.status_code, 201)
        electricity = next(item for item in services if item["name"] == "Электричество")
        reading_date = "2026-09-25"
        first_reading = self.client.post(
            f"/api/utilities/accounts/{account['id']}/readings",
            json={"service_id": electricity["id"], "reading_value": "100,000", "reading_date": reading_date},
        )
        self.assertEqual(first_reading.status_code, 201)
        updated_reading = self.client.post(
            f"/api/utilities/accounts/{account['id']}/readings",
            json={"service_id": electricity["id"], "reading_value": "101,250", "reading_date": reading_date},
        )
        self.assertEqual(updated_reading.status_code, 201)
        self.assertEqual(updated_reading.get_json()["reading"]["reading_value"], 101.25)
        readings = self.client.get(f"/api/utilities/accounts/{account['id']}/readings").get_json()["readings"]
        self.assertEqual(len([item for item in readings if item["service_id"] == electricity["id"] and item["reading_date"] == reading_date]), 1)

        month = "2026-09"
        payment = self.client.post(
            "/api/utilities/payments",
            json={
                "account_id": account["id"],
                "billing_month": month,
                "due_date": "2026-09-30",
                "items": [{"service_id": electricity["id"], "tariff_minor": 250, "previous_reading": 100, "current_reading": 102}],
            },
        )
        self.assertEqual(payment.status_code, 201)
        payment_payload = payment.get_json()["payment"]
        self.assertEqual(payment_payload["amount_minor"], 500)
        self.assertEqual(payment_payload["items"][0]["amount_minor"], 500)
        summary = self.client.get(f"/api/utilities/summary?month={month}").get_json()
        self.assertEqual(summary["accrued_minor"], 500)
        self.assertEqual(summary["remaining_minor"], 500)

    def test_utility_meter_reminder_window_and_submission_reset(self):
        account = self.client.post(
            "/api/utilities/accounts",
            json={"name": "Напоминание", "address": "ул. Сроковая, 1"},
        ).get_json()["account"]
        real_date = app_module.date

        class FrozenDate(real_date):
            @classmethod
            def today(cls):
                return real_date(2026, 9, 20)

        with patch.object(app_module, "date", FrozenDate):
            status = self.client.get("/api/utilities/reminders/status?month=2026-09").get_json()
            self.assertTrue(status["active_window"])
            self.assertEqual([item["account_id"] for item in status["reminders"]], [account["id"]])
            submitted = self.client.post(
                f"/api/utilities/accounts/{account['id']}/meter-submission",
                json={"submission_month": "2026-09", "submitted": True},
            )
            self.assertTrue(submitted.get_json()["submitted"])
            after_submission = self.client.get("/api/utilities/reminders/status?month=2026-09").get_json()
            self.assertEqual(after_submission["reminders"], [])
            reset = self.client.post(
                f"/api/utilities/accounts/{account['id']}/meter-submission",
                json={"submission_month": "2026-09", "submitted": False},
            )
            self.assertFalse(reset.get_json()["submitted"])

    def test_assistant_status_exposes_native_capability(self):
        with patch.object(
            app_module,
            "local_providers_status",
            return_value={
                "llm": {"ready": True, "model": "deepseek-r1:8b"},
                "tts": {"ready": True, "backend": "piper"},
            },
        ):
            response = self.client.get("/api/assistant/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["assistant"]
        self.assertEqual(payload["display_name"], "EVE · Эва")
        self.assertIn("native", payload)
        self.assertIn("model_path", payload["native"])
        self.assertTrue(payload["local"]["llm"]["ready"])
        self.assertTrue(payload["local"]["tts"]["ready"])

    def test_cloud_mode_is_explicit_and_terminal_requests_are_not_executed(self):
        settings = self.client.get("/api/assistant/settings").get_json()["settings"]
        self.assertEqual(settings["assistant_provider"], "local")
        saved = self.client.patch("/api/assistant/settings", json={"assistant_provider": "cloud"})
        self.assertEqual(saved.get_json()["settings"]["assistant_provider"], "cloud")
        with patch.object(app_module, "generate_cloud_reply", return_value="Привет, я на связи.") as generate:
            chat = self.client.post("/api/assistant/command", json={"text": "как дела?"})
        self.assertEqual(chat.get_json()["action"], "cloud_llm_reply")
        self.assertEqual(chat.get_json()["provider"], "openai-compatible")
        self.assertEqual(generate.call_args.args[0], "как дела?")
        with patch.object(app_module.subprocess, "run") as run:
            response = self.client.post(
                "/api/assistant/command",
                json={"text": "выполни команду whoami"},
            )
        self.assertEqual(response.get_json()["action"], "unsupported")
        run.assert_not_called()

    def test_unknown_command_uses_local_model_without_executing_action(self):
        with patch.object(app_module, "generate_local_reply", return_value="Я рядом и готова помочь.") as generate:
            response = self.client.post(
                "/api/assistant/command",
                json={"text": "Расскажи мне что-нибудь интересное"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["action"], "local_llm_reply")
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["reply"], "Я рядом и готова помочь.")
        generate.assert_called_once()

    def test_local_tts_endpoint_returns_wav(self):
        wav_payload = b"RIFF\x00\x00\x00\x00WAVE"
        with patch.object(app_module, "synthesize_speech", return_value=wav_payload) as synthesize:
            response = self.client.post("/api/assistant/tts", json={"text": "Проверка голоса"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "audio/wav")
        self.assertEqual(response.data, wav_payload)
        synthesize.assert_called_once_with("Проверка голоса", "eve-suit")


if __name__ == "__main__":
    unittest.main()
