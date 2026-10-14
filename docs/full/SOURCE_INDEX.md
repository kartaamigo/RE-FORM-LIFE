# ������ ���������� � ��������

����������� ������ `299d311`. � ������� ����������� ��������������� ������� � ������; ��������� ������ � JavaScript callbacks �� �������������. ������� ��������� �� ������ ����������.

| ���� | ����� | ���������� �� ���� |
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

| ������ | ��� | ������ |
| --- | --- | --- |
| `is_duplicate_voice_command` | ������� | 80 |
| `default_data_dir` | ������� | 100 |
| `now_iso` | ������� | 350 |
| `maybe_send_utility_reminder_notification` | ������� | 354 |
| `get_db` | ������� | 408 |
| `ensure_legacy_columns` | ������� | 430 |
| `seed_sections` | ������� | 447 |
| `ensure_assistant_settings` | ������� | 461 |
| `ensure_utility_settings` | ������� | 470 |
| `seed_savings_categories` | ������� | 479 |
| `seed_utility_services` | ������� | 488 |
| `close_db` | ������� | 500 |
| `record_assistant_message` | ������� | 506 |
| `record_assistant_chat_message` | ������� | 524 |
| `assistant_memories` | ������� | 542 |
| `find_assistant_memory` | ������� | 549 |
| `persist_assistant_exchange` | ������� | 569 |
| `row_dict` | ������� | 586 |
| `rows_dict` | ������� | 590 |
| `json_error` | ������� | 594 |
| `body` | ������� | 598 |
| `require_text` | ������� | 602 |
| `optional_text` | ������� | 611 |
| `validate_date` | ������� | 615 |
| `validate_month` | ������� | 626 |
| `validate_time` | ������� | 637 |
| `parse_amount` | ������� | 646 |
| `parse_bool` | ������� | 660 |
| `parse_progress` | ������� | 664 |
| `parse_mood_score` | ������� | 674 |
| `validate_color` | ������� | 684 |
| `section_name` | ������� | 691 |
| `serialize_task` | ������� | 704 |
| `task_scope` | ������� | 710 |
| `serialize_transaction` | ������� | 717 |
| `serialize_payment` | ������� | 722 |
| `parse_decimal` | ������� | 729 |
| `serialize_savings_category` | ������� | 739 |
| `serialize_savings_operation` | ������� | 748 |
| `serialize_utility_service` | ������� | 753 |
| `serialize_meter_reading` | ������� | 758 |
| `utility_payment_items` | ������� | 763 |
| `serialize_mood` | ������� | 776 |
| `assistant_settings_payload` | ������� | 784 |
| `assistant_date_label` | ������� | 812 |
| `assistant_task_word` | ������� | 819 |
| `current_weather` | ������� | 829 |
| `find_assistant_task` | ������� | 856 |
| `find_savings_category_by_text` | ������� | 879 |
| `savings_amount_from_text` | ������� | 905 |
| `find_utility_account_by_text` | ������� | 913 |
| `find_utility_service_by_text` | ������� | 929 |
| `confirmed_action_path` | ������� | 944 |
| `execute_pending_action` | ������� | 962 |
| `assistant_day_summary` | ������� | 1048 |
| `mood_summary` | ������� | 1061 |
| `inject_app_name` | ������� | 1081 |
| `index` | ������� | 1086 |
| `page_week` | ������� | 1091 |
| `page_tasks` | ������� | 1096 |
| `page_assistant` | ������� | 1101 |
| `page_month` | ������� | 1106 |
| `page_finance` | ������� | 1111 |
| `page_utilities` | ������� | 1116 |
| `page_habits` | ������� | 1121 |
| `api_health` | ������� | 1126 |
| `api_assistant_status` | ������� | 1132 |
| `api_assistant_tts` | ������� | 1167 |
| `api_assistant_transcribe` | ������� | 1196 |
| `api_assistant_settings_get` | ������� | 1210 |
| `api_assistant_settings_patch` | ������� | 1215 |
| `api_assistant_history_get` | ������� | 1285 |
| `api_assistant_history_delete` | ������� | 1298 |
| `api_assistant_chat_history_get` | ������� | 1307 |
| `api_assistant_chat_history_delete` | ������� | 1320 |
| `api_assistant_chat` | ������� | 1328 |
| `assistant_harness_reply` | ������� | 1353 |
| `assistant_harness_command` | ������� | 1369 |
| `api_assistant_pending_proposal` | ������� | 1383 |
| `api_assistant_memories_get` | ������� | 1388 |
| `api_assistant_memories_delete` | ������� | 1393 |
| `api_assistant_command` | ������� | 1401 |
| `api_assistant_commands` | ������� | 1697 |
| `api_assistant_command_create` | ������� | 1702 |
| `api_assistant_command_update` | ������� | 1710 |
| `api_assistant_command_delete` | ������� | 1723 |
| `api_assistant_command_export` | ������� | 1731 |
| `api_assistant_command_import` | ������� | 1737 |
| `api_assistant_confirm` | ������� | 1748 |
| `api_tasks_list` | ������� | 1775 |
| `api_tasks_create` | ������� | 1798 |
| `api_tasks_update` | ������� | 1823 |
| `api_tasks_delete` | ������� | 1851 |
| `api_notifications_list` | ������� | 1861 |
| `api_mood_today` | ������� | 1872 |
| `api_mood_list` | ������� | 1880 |
| `api_mood_put` | ������� | 1896 |
| `api_sections_list` | ������� | 1917 |
| `api_sections_create` | ������� | 1925 |
| `api_month_priorities_list` | ������� | 1946 |
| `api_month_priority_create` | ������� | 1959 |
| `api_month_priority_update` | ������� | 1982 |
| `api_month_priority_delete` | ������� | 2009 |
| `api_goal_get` | ������� | 2021 |
| `api_goal_put` | ������� | 2031 |
| `api_notes_list` | ������� | 2048 |
| `api_notes_create` | ������� | 2054 |
| `api_notes_update` | ������� | 2070 |
| `api_notes_delete` | ������� | 2092 |
| `finance_query` | ������� | 2101 |
| `api_finance_list` | ������� | 2112 |
| `api_finance_create` | ������� | 2121 |
| `api_finance_update` | ������� | 2145 |
| `api_finance_delete` | ������� | 2171 |
| `savings_categories_query` | ������� | 2180 |
| `savings_category` | ������� | 2199 |
| `savings_balance` | ������� | 2207 |
| `nonnegative_amount` | ������� | 2215 |
| `api_savings_categories_list` | ������� | 2232 |
| `api_savings_category_create` | ������� | 2238 |
| `api_savings_category_update` | ������� | 2258 |
| `api_savings_category_archive` | ������� | 2281 |
| `api_savings_operations_list` | ������� | 2291 |
| `api_savings_operation_create` | ������� | 2307 |
| `api_savings_operation_update` | ������� | 2339 |
| `api_savings_operation_delete` | ������� | 2378 |
| `api_savings_summary` | ������� | 2388 |
| `api_savings_plans_list` | ������� | 2404 |
| `api_savings_plan_update` | ������� | 2416 |
| `api_utility_accounts_list` | ������� | 2447 |
| `api_utility_account_create` | ������� | 2453 |
| `api_utility_account_update` | ������� | 2475 |
| `api_utility_account_delete` | ������� | 2498 |
| `api_utility_services_list` | ������� | 2508 |
| `api_utility_service_create` | ������� | 2521 |
| `api_utility_service_update` | ������� | 2543 |
| `api_utility_service_delete` | ������� | 2563 |
| `api_utility_readings_list` | ������� | 2573 |
| `api_utility_reading_create` | ������� | 2587 |
| `api_utility_meter_submission` | ������� | 2616 |
| `api_utility_reminders_status` | ������� | 2639 |
| `api_utility_reminder_settings_get` | ������� | 2671 |
| `api_utility_reminder_settings_patch` | ������� | 2678 |
| `api_utility_summary` | ������� | 2696 |
| `api_utility_payments_list` | ������� | 2722 |
| `normalize_payment_items` | ������� | 2749 |
| `save_payment_items` | ������� | 2792 |
| `api_utility_payment_create` | ������� | 2804 |
| `api_utility_payment_update` | ������� | 2845 |
| `api_utility_payment_delete` | ������� | 2902 |
| `normalize_schedule` | ������� | 2911 |
| `api_habits_list` | ������� | 2920 |
| `api_habits_create` | ������� | 2929 |
| `api_habits_update` | ������� | 2955 |
| `api_habits_delete` | ������� | 2983 |
| `api_habit_entries_list` | ������� | 2993 |
| `api_habit_entry_put` | ������� | 3010 |
| `api_habit_entry_delete` | ������� | 3029 |
| `api_migrate` | ������� | 3041 |

## eve_agent.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `_run_osascript` | ������� | 96 |
| `_wifi_device` | ������� | 111 |
| `_run_networksetup` | ������� | 130 |
| `_safe_location` | ������� | 147 |
| `_windows_start_menu_shortcut` | ������� | 167 |
| `_windows_start_app` | ������� | 199 |
| `_browser_executable` | ������� | 246 |
| `_open_web_target` | ������� | 267 |
| `_send_file_to_trash` | ������� | 287 |
| `_windows_audio_endpoint` | ������� | 324 |
| `_windows_brightness` | ������� | 336 |
| `_windows_wifi_adapter` | ������� | 357 |
| `_windows_wifi_status` | ������� | 373 |
| `_set_windows_wifi` | ������� | 390 |
| `_windows_active_window` | ������� | 409 |
| `perform_external_action` | ������� | 425 |
| `data_dir` | ������� | 622 |
| `model_path` | ������� | 633 |
| `native_agent_status` | ������� | 655 |
| `input_devices` | ������� | 681 |
| `_shared_vosk_model` | ������� | 708 |
| `transcribe_pcm` | ������� | 714 |
| `application_command` | ������� | 727 |
| `configure_autostart` | ������� | 736 |
| `_post_command` | ������� | 772 |
| `_speak` | ������� | 784 |
| `run_native_agent` | ������� | 823 |

## eve_assistant.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `ParsedCommand` | ����� | 44 |
| `normalize_text` | ������� | 104 |
| `normalize_command_text` | ������� | 109 |
| `choose_command_candidate` | ������� | 124 |
| `_browser_from_text` | ������� | 136 |
| `_extract_browser_suffix` | ������� | 144 |
| `strip_wake_word` | ������� | 157 |
| `has_wake_word` | ������� | 162 |
| `clean_assistant_reply` | ������� | 168 |
| `iso_day` | ������� | 177 |
| `date_from_text` | ������� | 181 |
| `week_date_from_text` | ������� | 208 |
| `schedule_from_text` | ������� | 226 |
| `command_scope` | ������� | 264 |
| `external_target` | ������� | 269 |
| `url_target` | ������� | 274 |
| `extract_task_destination` | ������� | 279 |
| `parse_command` | ������� | 305 |

## eve_commands.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `_text` | ������� | 50 |
| `validate_definition` | ������� | 56 |
| `list_commands` | ������� | 80 |
| `save_command` | ������� | 89 |
| `import_commands` | ������� | 112 |
| `resolve_command` | ������� | 137 |

## eve_harness.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `ConfirmationRequired` | ����� | 21 |
| `relevant_memories` | ������� | 27 |
| `_date` | ������� | 43 |
| `_text` | ������� | 50 |
| `_properties` | ������� | 56 |
| `describe_fields` | ������� | 64 |
| `_fields` | ������� | 78 |
| `tool_declarations` | ������� | 106 |
| `EveHarness` | ����� | 147 |
| `pending_proposal` | ������� | 258 |
| `confirm_proposal` | ������� | 270 |

## eve_local.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `_configure_numba_cache` | ������� | 31 |
| `LocalProviderError` | ����� | 127 |
| `strip_reasoning` | ������� | 131 |
| `_json_request` | ������� | 146 |
| `_conversation_messages` | ������� | 184 |
| `_gemini_api_key` | ������� | 220 |
| `_windows_user_environment_value` | ������� | 231 |
| `resolve_gemini_model` | ������� | 246 |
| `gemini_status` | ������� | 257 |
| `generate_gemini_reply` | ������� | 270 |
| `build_profile` | ������� | 382 |
| `available_tts_voices` | ������� | 406 |
| `_qwen_voice_instruction` | ������� | 429 |
| `_profile_model_path` | ������� | 439 |
| `_clone_model_path` | ������� | 473 |
| `_sample_voice_path` | ������� | 496 |
| `_sample_voice_text` | ������� | 512 |
| `_tts_package_status` | ������� | 522 |
| `tts_status` | ������� | 538 |
| `_load_silero_model` | ������� | 584 |
| `_load_qwen_model` | ������� | 607 |
| `_load_clone_prompt` | ������� | 629 |
| `_is_gpu_memory_error` | ������� | 637 |
| `_audio_samples_are_finite` | ������� | 642 |
| `_match_sample_pitch` | ������� | 653 |
| `_write_pcm_wav` | ������� | 677 |
| `_synthesize_profile_speech` | ������� | 701 |
| `synthesize_speech` | ������� | 807 |
| `providers_status` | ������� | 822 |

## eve_speechkit.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `speechkit_status` | ������� | 25 |
| `_credentials` | ������� | 38 |
| `_request` | ������� | 46 |
| `synthesize_speechkit` | ������� | 66 |
| `transcribe_speechkit` | ������� | 94 |

## launcher.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `find_free_port` | ������� | 10 |
| `start_flask` | ������� | 19 |
| `start_eve_agent` | ������� | 23 |
| `wait_for_server` | ������� | 53 |

## tests/test_eve_and_utilities.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `EveParserTests` | ����� | 19 |
| `PlannerAndUtilitiesApiTests` | ����� | 240 |

## tests/test_eve_commands.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `UserCommandTests` | ����� | 14 |

## tests/test_eve_harness.py

| ������ | ��� | ������ |
| --- | --- | --- |
| `model_reply` | ������� | 17 |
| `model_calls` | ������� | 21 |
| `ToolLoopTests` | ����� | 28 |
| `HarnessApiTests` | ����� | 96 |
