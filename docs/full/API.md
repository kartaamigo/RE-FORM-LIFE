# ������ ������ ������� � API

������ ����������: `299d311`, 14 ������� 2026 ����. ������� ����������� �������� ����������� `app.py`; ��� �� OpenAPI � �� �������� ������� �������. �������������� ������� Flask `/static/<path:filename>` � ������� �� ������.

| ����� | ���� | ���������� | ������ |
| --- | --- | --- | --- |
| GET | `/` | `index` | 1086 |
| GET | `/week` | `page_week` | 1091 |
| GET | `/tasks` | `page_tasks` | 1096 |
| GET | `/assistant` | `page_assistant` | 1101 |
| GET | `/month` | `page_month` | 1106 |
| GET | `/finance` | `page_finance` | 1111 |
| GET | `/utilities` | `page_utilities` | 1116 |
| GET | `/habits` | `page_habits` | 1121 |
| GET | `/api/health` | `api_health` | 1126 |
| GET | `/api/assistant/status` | `api_assistant_status` | 1132 |
| POST | `/api/assistant/tts` | `api_assistant_tts` | 1167 |
| POST | `/api/assistant/transcribe` | `api_assistant_transcribe` | 1196 |
| GET | `/api/assistant/settings` | `api_assistant_settings_get` | 1210 |
| PATCH | `/api/assistant/settings` | `api_assistant_settings_patch` | 1215 |
| GET | `/api/assistant/history` | `api_assistant_history_get` | 1285 |
| DELETE | `/api/assistant/history` | `api_assistant_history_delete` | 1298 |
| GET | `/api/assistant/chat/history` | `api_assistant_chat_history_get` | 1307 |
| DELETE | `/api/assistant/chat/history` | `api_assistant_chat_history_delete` | 1320 |
| POST | `/api/assistant/chat` | `api_assistant_chat` | 1328 |
| GET | `/api/assistant/proposals/pending` | `api_assistant_pending_proposal` | 1383 |
| GET | `/api/assistant/memories` | `api_assistant_memories_get` | 1388 |
| DELETE | `/api/assistant/memories` | `api_assistant_memories_delete` | 1393 |
| POST | `/api/assistant/command` | `api_assistant_command` | 1401 |
| GET | `/api/assistant/commands` | `api_assistant_commands` | 1697 |
| POST | `/api/assistant/commands` | `api_assistant_command_create` | 1702 |
| PATCH | `/api/assistant/commands/<int:command_id>` | `api_assistant_command_update` | 1710 |
| DELETE | `/api/assistant/commands/<int:command_id>` | `api_assistant_command_delete` | 1723 |
| GET | `/api/assistant/commands/export` | `api_assistant_command_export` | 1731 |
| POST | `/api/assistant/commands/import` | `api_assistant_command_import` | 1737 |
| POST | `/api/assistant/confirm` | `api_assistant_confirm` | 1748 |
| GET | `/api/tasks` | `api_tasks_list` | 1775 |
| POST | `/api/tasks` | `api_tasks_create` | 1798 |
| PATCH | `/api/tasks/<int:task_id>` | `api_tasks_update` | 1823 |
| DELETE | `/api/tasks/<int:task_id>` | `api_tasks_delete` | 1851 |
| GET | `/api/notifications` | `api_notifications_list` | 1861 |
| GET | `/api/mood/today` | `api_mood_today` | 1872 |
| GET | `/api/mood` | `api_mood_list` | 1880 |
| PUT | `/api/mood/<entry_date>` | `api_mood_put` | 1896 |
| GET | `/api/sections` | `api_sections_list` | 1917 |
| POST | `/api/sections` | `api_sections_create` | 1925 |
| GET | `/api/month/priorities` | `api_month_priorities_list` | 1946 |
| POST | `/api/month/priorities` | `api_month_priority_create` | 1959 |
| PATCH | `/api/month/priorities/<int:priority_id>` | `api_month_priority_update` | 1982 |
| DELETE | `/api/month/priorities/<int:priority_id>` | `api_month_priority_delete` | 2009 |
| GET | `/api/goals/<week_monday>` | `api_goal_get` | 2021 |
| PUT | `/api/goals/<week_monday>` | `api_goal_put` | 2031 |
| GET | `/api/notes` | `api_notes_list` | 2048 |
| POST | `/api/notes` | `api_notes_create` | 2054 |
| PATCH | `/api/notes/<int:note_id>` | `api_notes_update` | 2070 |
| DELETE | `/api/notes/<int:note_id>` | `api_notes_delete` | 2092 |
| GET | `/api/finance/transactions` | `api_finance_list` | 2112 |
| POST | `/api/finance/transactions` | `api_finance_create` | 2121 |
| PATCH | `/api/finance/transactions/<int:transaction_id>` | `api_finance_update` | 2145 |
| DELETE | `/api/finance/transactions/<int:transaction_id>` | `api_finance_delete` | 2171 |
| GET | `/api/finance/savings/categories` | `api_savings_categories_list` | 2232 |
| POST | `/api/finance/savings/categories` | `api_savings_category_create` | 2238 |
| PATCH | `/api/finance/savings/categories/<int:category_id>` | `api_savings_category_update` | 2258 |
| DELETE | `/api/finance/savings/categories/<int:category_id>` | `api_savings_category_archive` | 2281 |
| GET | `/api/finance/savings/operations` | `api_savings_operations_list` | 2291 |
| POST | `/api/finance/savings/operations` | `api_savings_operation_create` | 2307 |
| PATCH | `/api/finance/savings/operations/<int:operation_id>` | `api_savings_operation_update` | 2339 |
| DELETE | `/api/finance/savings/operations/<int:operation_id>` | `api_savings_operation_delete` | 2378 |
| GET | `/api/finance/savings/summary` | `api_savings_summary` | 2388 |
| GET | `/api/finance/savings/plans` | `api_savings_plans_list` | 2404 |
| PATCH | `/api/finance/savings/categories/<int:category_id>/plan` | `api_savings_plan_update` | 2416 |
| GET | `/api/utilities/accounts` | `api_utility_accounts_list` | 2447 |
| POST | `/api/utilities/accounts` | `api_utility_account_create` | 2453 |
| PATCH | `/api/utilities/accounts/<int:account_id>` | `api_utility_account_update` | 2475 |
| DELETE | `/api/utilities/accounts/<int:account_id>` | `api_utility_account_delete` | 2498 |
| GET | `/api/utilities/accounts/<int:account_id>/services` | `api_utility_services_list` | 2508 |
| POST | `/api/utilities/accounts/<int:account_id>/services` | `api_utility_service_create` | 2521 |
| PATCH | `/api/utilities/services/<int:service_id>` | `api_utility_service_update` | 2543 |
| DELETE | `/api/utilities/services/<int:service_id>` | `api_utility_service_delete` | 2563 |
| GET | `/api/utilities/accounts/<int:account_id>/readings` | `api_utility_readings_list` | 2573 |
| POST | `/api/utilities/accounts/<int:account_id>/readings` | `api_utility_reading_create` | 2587 |
| POST | `/api/utilities/accounts/<int:account_id>/meter-submission` | `api_utility_meter_submission` | 2616 |
| GET | `/api/utilities/reminders/status` | `api_utility_reminders_status` | 2639 |
| GET | `/api/utilities/reminders/settings` | `api_utility_reminder_settings_get` | 2671 |
| PATCH | `/api/utilities/reminders/settings` | `api_utility_reminder_settings_patch` | 2678 |
| GET | `/api/utilities/summary` | `api_utility_summary` | 2696 |
| GET | `/api/utilities/payments` | `api_utility_payments_list` | 2722 |
| POST | `/api/utilities/payments` | `api_utility_payment_create` | 2804 |
| PATCH | `/api/utilities/payments/<int:payment_id>` | `api_utility_payment_update` | 2845 |
| DELETE | `/api/utilities/payments/<int:payment_id>` | `api_utility_payment_delete` | 2902 |
| GET | `/api/habits` | `api_habits_list` | 2920 |
| POST | `/api/habits` | `api_habits_create` | 2929 |
| PATCH | `/api/habits/<int:habit_id>` | `api_habits_update` | 2955 |
| DELETE | `/api/habits/<int:habit_id>` | `api_habits_delete` | 2983 |
| GET | `/api/habits/entries` | `api_habit_entries_list` | 2993 |
| PUT | `/api/habits/<int:habit_id>/entries/<entry_date>` | `api_habit_entry_put` | 3010 |
| DELETE | `/api/habits/<int:habit_id>/entries/<entry_date>` | `api_habit_entry_delete` | 3029 |
| POST | `/api/migrate` | `api_migrate` | 3041 |

## �������� � �����������

- JSON-�������� ���������� ����������� �������� �����. ������ ������� �� ��������� ��� ���� ������� � �� �������� ����������.
- ����������� HTTP HEAD/OPTIONS, ������������� ����������� Flask, ����� �� �����������.
- `/api/assistant/chat` ���������� ����������� ������ ������; `/api/assistant/command` ���������� ��������� ������� � harness � ������������� ���������.
- ������������� ������ �������� ����� `/api/assistant/confirm`; ����������� ����������������� ����� `/api/assistant/proposals/pending`.
- ����, ��������� Flask � ������ ����� ��������� � ���������� ������. ����� ��������� ���� ������ ������� �����������.
- ������� �������� � ������� ������ ������� � [����������� �����������](CODE.md).
