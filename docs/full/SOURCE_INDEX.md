# Реестр исходников и символов

Статический снимок `299d311`. Верхнеуровневые функции и классы; вложенные методы не перечислены.

| Файл | Строк | Тип |
| --- | --- | --- |
| `.github/workflows/release-portable.yml` | 126 | .yml |
| `ReFormLife.mac.spec` | 104 | .spec |
| `ReFormLife.spec` | 188 | .spec |
| `app.py` | 3091 | .py |
| `build-profiles/commercial.json` | 14 | .json |
| `build-profiles/personal.json` | 8 | .json |
| `docs/examples/eve-commands.json` | 26 | .json |
| `eve_agent.py` | 941 | .py |
| `eve_assistant.py` | 559 | .py |
| `eve_commands.py` | 160 | .py |
| `eve_harness.py` | 306 | .py |
| `eve_local.py` | 823 | .py |
| `eve_speechkit.py` | 117 | .py |
| `launcher.py` | 83 | .py |
| `static/css/eve-orbit.css` | 114 | .css |
| `static/css/reference.css` | 3494 | .css |
| `static/css/style.css` | 524 | .css |
| `static/css/week-legacy.css` | 917 | .css |
| `static/js/app.js` | 2182 | .js |
| `static/js/eve-commands.js` | 95 | .js |
| `templates/assistant.html` | 127 | .html |
| `templates/base.html` | 204 | .html |
| `templates/finance.html` | 39 | .html |
| `templates/habits.html` | 11 | .html |
| `templates/month.html` | 77 | .html |
| `templates/tasks.html` | 20 | .html |
| `templates/utilities.html` | 20 | .html |
| `templates/week.html` | 83 | .html |
| `tests/test_eve_and_utilities.py` | 797 | .py |
| `tests/test_eve_commands.py` | 160 | .py |
| `tests/test_eve_harness.py` | 299 | .py |

## app.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `is_duplicate_voice_command` | функция | 80 |
| `default_data_dir` | функция | 100 |
| `now_iso` | функция | 350 |
| `maybe_send_utility_reminder_notification` | функция | 354 |
| `get_db` | функция | 408 |
| `ensure_legacy_columns` | функция | 430 |
| `seed_sections` | функция | 447 |
| `ensure_assistant_settings` | функция | 461 |
| `ensure_utility_settings` | функция | 470 |
| `seed_savings_categories` | функция | 479 |
| `seed_utility_services` | функция | 488 |
| `close_db` | функция | 500 |
| `record_assistant_message` | функция | 506 |
| `record_assistant_chat_message` | функция | 524 |
| `assistant_memories` | функция | 542 |
| `find_assistant_memory` | функция | 549 |
| `persist_assistant_exchange` | функция | 569 |
| `row_dict` | функция | 586 |
| `rows_dict` | функция | 590 |
| `json_error` | функция | 594 |
| `body` | функция | 598 |
| `require_text` | функция | 602 |
| `optional_text` | функция | 611 |
| `validate_date` | функция | 615 |
| `validate_month` | функция | 626 |
| `validate_time` | функция | 637 |
| `parse_amount` | функция | 646 |
| `parse_bool` | функция | 660 |
| `parse_progress` | функция | 664 |
| `parse_mood_score` | функция | 674 |
| `validate_color` | функция | 684 |
| `section_name` | функция | 691 |
| `serialize_task` | функция | 704 |
| `task_scope` | функция | 710 |
| `serialize_transaction` | функция | 717 |
| `serialize_payment` | функция | 722 |
| `parse_decimal` | функция | 729 |
| `serialize_savings_category` | функция | 739 |
| `serialize_savings_operation` | функция | 748 |
| `serialize_utility_service` | функция | 753 |
| `serialize_meter_reading` | функция | 758 |
| `utility_payment_items` | функция | 763 |
| `serialize_mood` | функция | 776 |
| `assistant_settings_payload` | функция | 784 |
| `assistant_date_label` | функция | 812 |
| `assistant_task_word` | функция | 819 |
| `current_weather` | функция | 829 |
| `find_assistant_task` | функция | 856 |
| `find_savings_category_by_text` | функция | 879 |
| `savings_amount_from_text` | функция | 905 |
| `find_utility_account_by_text` | функция | 913 |
| `find_utility_service_by_text` | функция | 929 |
| `confirmed_action_path` | функция | 944 |
| `execute_pending_action` | функция | 962 |
| `assistant_day_summary` | функция | 1048 |
| `mood_summary` | функция | 1061 |
| `inject_app_name` | функция | 1081 |
| `index` | функция | 1086 |
| `page_week` | функция | 1091 |
| `page_tasks` | функция | 1096 |
| `page_assistant` | функция | 1101 |
| `page_month` | функция | 1106 |
| `page_finance` | функция | 1111 |
| `page_utilities` | функция | 1116 |
| `page_habits` | функция | 1121 |
| `api_health` | функция | 1126 |
| `api_assistant_status` | функция | 1132 |
| `api_assistant_tts` | функция | 1167 |
| `api_assistant_transcribe` | функция | 1196 |
| `api_assistant_settings_get` | функция | 1210 |
| `api_assistant_settings_patch` | функция | 1215 |
| `api_assistant_history_get` | функция | 1285 |
| `api_assistant_history_delete` | функция | 1298 |
| `api_assistant_chat_history_get` | функция | 1307 |
| `api_assistant_chat_history_delete` | функция | 1320 |
| `api_assistant_chat` | функция | 1328 |
| `assistant_harness_reply` | функция | 1353 |
| `assistant_harness_command` | функция | 1369 |
| `api_assistant_pending_proposal` | функция | 1383 |
| `api_assistant_memories_get` | функция | 1388 |
| `api_assistant_memories_delete` | функция | 1393 |
| `api_assistant_command` | функция | 1401 |
| `api_assistant_commands` | функция | 1697 |
| `api_assistant_command_create` | функция | 1702 |
| `api_assistant_command_update` | функция | 1710 |
| `api_assistant_command_delete` | функция | 1723 |
| `api_assistant_command_export` | функция | 1731 |
| `api_assistant_command_import` | функция | 1737 |
| `api_assistant_confirm` | функция | 1748 |
| `api_tasks_list` | функция | 1775 |
| `api_tasks_create` | функция | 1798 |
| `api_tasks_update` | функция | 1823 |
| `api_tasks_delete` | функция | 1851 |
| `api_notifications_list` | функция | 1861 |
| `api_mood_today` | функция | 1872 |
| `api_mood_list` | функция | 1880 |
| `api_mood_put` | функция | 1896 |
| `api_sections_list` | функция | 1917 |
| `api_sections_create` | функция | 1925 |
| `api_month_priorities_list` | функция | 1946 |
| `api_month_priority_create` | функция | 1959 |
| `api_month_priority_update` | функция | 1982 |
| `api_month_priority_delete` | функция | 2009 |
| `api_goal_get` | функция | 2021 |
| `api_goal_put` | функция | 2031 |
| `api_notes_list` | функция | 2048 |
| `api_notes_create` | функция | 2054 |
| `api_notes_update` | функция | 2070 |
| `api_notes_delete` | функция | 2092 |
| `finance_query` | функция | 2101 |
| `api_finance_list` | функция | 2112 |
| `api_finance_create` | функция | 2121 |
| `api_finance_update` | функция | 2145 |
| `api_finance_delete` | функция | 2171 |
| `savings_categories_query` | функция | 2180 |
| `savings_category` | функция | 2199 |
| `savings_balance` | функция | 2207 |
| `nonnegative_amount` | функция | 2215 |
| `api_savings_categories_list` | функция | 2232 |
| `api_savings_category_create` | функция | 2238 |
| `api_savings_category_update` | функция | 2258 |
| `api_savings_category_archive` | функция | 2281 |
| `api_savings_operations_list` | функция | 2291 |
| `api_savings_operation_create` | функция | 2307 |
| `api_savings_operation_update` | функция | 2339 |
| `api_savings_operation_delete` | функция | 2378 |
| `api_savings_summary` | функция | 2388 |
| `api_savings_plans_list` | функция | 2404 |
| `api_savings_plan_update` | функция | 2416 |
| `api_utility_accounts_list` | функция | 2447 |
| `api_utility_account_create` | функция | 2453 |
| `api_utility_account_update` | функция | 2475 |
| `api_utility_account_delete` | функция | 2498 |
| `api_utility_services_list` | функция | 2508 |
| `api_utility_service_create` | функция | 2521 |
| `api_utility_service_update` | функция | 2543 |
| `api_utility_service_delete` | функция | 2563 |
| `api_utility_readings_list` | функция | 2573 |
| `api_utility_reading_create` | функция | 2587 |
| `api_utility_meter_submission` | функция | 2616 |
| `api_utility_reminders_status` | функция | 2639 |
| `api_utility_reminder_settings_get` | функция | 2671 |
| `api_utility_reminder_settings_patch` | функция | 2678 |
| `api_utility_summary` | функция | 2696 |
| `api_utility_payments_list` | функция | 2722 |
| `normalize_payment_items` | функция | 2749 |
| `save_payment_items` | функция | 2792 |
| `api_utility_payment_create` | функция | 2804 |
| `api_utility_payment_update` | функция | 2845 |
| `api_utility_payment_delete` | функция | 2902 |
| `normalize_schedule` | функция | 2911 |
| `api_habits_list` | функция | 2920 |
| `api_habits_create` | функция | 2929 |
| `api_habits_update` | функция | 2955 |
| `api_habits_delete` | функция | 2983 |
| `api_habit_entries_list` | функция | 2993 |
| `api_habit_entry_put` | функция | 3010 |
| `api_habit_entry_delete` | функция | 3029 |
| `api_migrate` | функция | 3041 |

## eve_agent.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `_run_osascript` | функция | 96 |
| `_wifi_device` | функция | 111 |
| `_run_networksetup` | функция | 130 |
| `_safe_location` | функция | 147 |
| `_windows_start_menu_shortcut` | функция | 167 |
| `_windows_start_app` | функция | 199 |
| `_browser_executable` | функция | 246 |
| `_open_web_target` | функция | 267 |
| `_send_file_to_trash` | функция | 287 |
| `_windows_audio_endpoint` | функция | 324 |
| `_windows_brightness` | функция | 336 |
| `_windows_wifi_adapter` | функция | 357 |
| `_windows_wifi_status` | функция | 373 |
| `_set_windows_wifi` | функция | 390 |
| `_windows_active_window` | функция | 409 |
| `perform_external_action` | функция | 425 |
| `data_dir` | функция | 622 |
| `model_path` | функция | 633 |
| `native_agent_status` | функция | 655 |
| `input_devices` | функция | 681 |
| `_shared_vosk_model` | функция | 708 |
| `transcribe_pcm` | функция | 714 |
| `application_command` | функция | 727 |
| `configure_autostart` | функция | 736 |
| `_post_command` | функция | 772 |
| `_speak` | функция | 784 |
| `run_native_agent` | функция | 823 |

## eve_assistant.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `ParsedCommand` | класс | 44 |
| `normalize_text` | функция | 104 |
| `normalize_command_text` | функция | 109 |
| `choose_command_candidate` | функция | 124 |
| `_browser_from_text` | функция | 136 |
| `_extract_browser_suffix` | функция | 144 |
| `strip_wake_word` | функция | 157 |
| `has_wake_word` | функция | 162 |
| `clean_assistant_reply` | функция | 168 |
| `iso_day` | функция | 177 |
| `date_from_text` | функция | 181 |
| `week_date_from_text` | функция | 208 |
| `schedule_from_text` | функция | 226 |
| `command_scope` | функция | 264 |
| `external_target` | функция | 269 |
| `url_target` | функция | 274 |
| `extract_task_destination` | функция | 279 |
| `parse_command` | функция | 305 |

## eve_commands.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `_text` | функция | 50 |
| `validate_definition` | функция | 56 |
| `list_commands` | функция | 80 |
| `save_command` | функция | 89 |
| `import_commands` | функция | 112 |
| `resolve_command` | функция | 137 |

## eve_harness.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `ConfirmationRequired` | класс | 21 |
| `relevant_memories` | функция | 27 |
| `_date` | функция | 43 |
| `_text` | функция | 50 |
| `_properties` | функция | 56 |
| `describe_fields` | функция | 64 |
| `_fields` | функция | 78 |
| `tool_declarations` | функция | 106 |
| `EveHarness` | класс | 147 |
| `pending_proposal` | функция | 258 |
| `confirm_proposal` | функция | 270 |

## eve_local.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `_configure_numba_cache` | функция | 31 |
| `LocalProviderError` | класс | 127 |
| `strip_reasoning` | функция | 131 |
| `_json_request` | функция | 146 |
| `_conversation_messages` | функция | 184 |
| `_gemini_api_key` | функция | 220 |
| `_windows_user_environment_value` | функция | 231 |
| `resolve_gemini_model` | функция | 246 |
| `gemini_status` | функция | 257 |
| `generate_gemini_reply` | функция | 270 |
| `build_profile` | функция | 382 |
| `available_tts_voices` | функция | 406 |
| `_qwen_voice_instruction` | функция | 429 |
| `_profile_model_path` | функция | 439 |
| `_clone_model_path` | функция | 473 |
| `_sample_voice_path` | функция | 496 |
| `_sample_voice_text` | функция | 512 |
| `_tts_package_status` | функция | 522 |
| `tts_status` | функция | 538 |
| `_load_silero_model` | функция | 584 |
| `_load_qwen_model` | функция | 607 |
| `_load_clone_prompt` | функция | 629 |
| `_is_gpu_memory_error` | функция | 637 |
| `_audio_samples_are_finite` | функция | 642 |
| `_match_sample_pitch` | функция | 653 |
| `_write_pcm_wav` | функция | 677 |
| `_synthesize_profile_speech` | функция | 701 |
| `synthesize_speech` | функция | 807 |
| `providers_status` | функция | 822 |

## eve_speechkit.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `speechkit_status` | функция | 25 |
| `_credentials` | функция | 38 |
| `_request` | функция | 46 |
| `synthesize_speechkit` | функция | 66 |
| `transcribe_speechkit` | функция | 94 |

## launcher.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `find_free_port` | функция | 10 |
| `start_flask` | функция | 19 |
| `start_eve_agent` | функция | 23 |
| `wait_for_server` | функция | 53 |

## tests/test_eve_and_utilities.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `EveParserTests` | класс | 19 |
| `PlannerAndUtilitiesApiTests` | класс | 240 |

## tests/test_eve_commands.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `UserCommandTests` | класс | 14 |

## tests/test_eve_harness.py

| Символ | Тип | Строка |
| --- | --- | --- |
| `model_reply` | функция | 17 |
| `model_calls` | функция | 21 |
| `ToolLoopTests` | класс | 28 |
| `HarnessApiTests` | класс | 96 |
