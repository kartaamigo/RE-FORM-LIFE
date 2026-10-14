# Запуск, данные, сборки и сопровождение

## Windows из исходников

Рекомендуемая точка запуска — launcher.py. В workflow Windows используется Python 3.13; macOS — 3.12. Базовые зависимости не включают весь набор крупных TTS-профилей.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher.py
```

Для Silero устанавливать requirements-tts-personal.txt и отдельно получать корректные веса/исходники модели. Для Qwen — requirements-tts-commercial.txt и полный snapshot модели. Крупные локальные папки моделей исключены из Git; свежий clone не равен полноценной TTS-установке.

Для разговора задаётся GEMINI_API_KEY либо GOOGLE_API_KEY. Не включать настоящий ключ в коммиты, документацию и диагностический вывод. Порядок настройки профилей и образцов подробнее описан в [EVE_LOCAL_SETUP](../../EVE_LOCAL_SETUP.md).

## Основные настройки

| Настройка | Назначение |
| --- | --- |
| REFORM_LIFE_DATA_DIR | Каталог пользовательских данных |
| REFORM_LIFE_DB | Явный путь базы приложения |
| REFORM_LIFE_PORT | Порт launcher |
| GEMINI_API_KEY / GOOGLE_API_KEY | Ключ облачной модели |
| GEMINI_MODEL | Override модели |
| EVE_VOSK_MODEL | Каталог модели распознавания |
| EVE_BUILD_PROFILE | personal/commercial для предусмотренного пути сборки/исходников |
| EVE_BUILD_ONEFILE | Вариант Windows-упаковки |
| EVE_SILERO_MODEL_DIR | Каталог Silero |
| EVE_QWEN_MODEL_DIR | Snapshot Qwen VoiceDesign |
| EVE_QWEN_BASE_MODEL_DIR | Snapshot Qwen Base для образца |
| YANDEX_SPEECHKIT_API_KEY | Ключ SpeechKit |
| YANDEX_SPEECHKIT_FOLDER_ID | Каталог Yandex Cloud |

Другие настройки/системные переменные, включая пути образцов, автозапуск и agent URL — в [ENVIRONMENT](ENVIRONMENT.md) и адаптерах.

Настройки EVE дополнительно сохраняются в SQLite: включение Gemini, модель, персонализация, голос и другие флаги. Параметры окружения и сохранённые значения взаимодействуют через assistant_settings_payload, поэтому не следует считать единственным источником UI или JSON профиля.

## Где данные

Из исходников по умолчанию — instance/reform_life.sqlite3. Frozen-приложение использует предусмотренный пользовательский каталог; в Windows — LOCALAPPDATA/APPDATA и RE-FORM LIFE. Агент имеет собственный выбор каталога для разных ОС. Явные REFORM_LIFE_DATA_DIR/DB нужно задавать согласованно; отдельный DB override не обязательно меняет расположение всех аудио/модельных ресурсов.

Личные данные: задачи, деньги, счета, отметки, настройки, история и память. Каталог instance игнорируется Git. История до удаления базы всё ещё содержит ранний tracked-файл.

Резервная копия: закрыть приложение, определить фактический путь, сохранить SQLite и важные внешние файлы (например WAV образца) отдельно. Встроенный общий backup/restore UI не подтверждён. Не открывать рабочую базу для тестов документации.

## Упаковка

Windows: ReFormLife.spec проверяет профиль и полноту моделей, включает static/templates, Vosk/runtime, профиль и TTS-модель. Для commercial проверяются config/tokenizer/weights; Base-образец опционален при корректной конфигурации. В personal тяжёлые пакеты Qwen исключаются.

macOS: ReFormLife.mac.spec собирает .app с personal/Silero и исключает Qwen-стек. Проверка подписи/notarization текущим сбором не проводилась; наличие .icns не подтверждает доверие Gatekeeper.

Workflow .github/workflows/release-portable.yml:
- Триггеры: v*-тег или workflow_dispatch с release_tag.
- Создаёт GitHub release при отсутствии.
- Windows runner, Python 3.13, personal/Silero, portable directory.
- macos-14, Python 3.12, personal/Silero, архив с именем macOS-Intel.
- Загружает Silero и веса из upstream в ходе сборки.
- Архивы выше заданного порога дробятся на части около 1900 MB.
- Публикует assets через gh release upload.

Наличие workflow и commit d35d303 не подтверждает успешный последний run, доступность всех assets или поддержку Apple Silicon. Указанное Intel — имя архива в workflow, не результат текущего измерения архитектуры.

## Проверки

```powershell
python -B -m unittest discover -s tests -q
node --check static/js/app.js
node --check static/js/eve-commands.js
```

Три тестовых файла охватывают EVE/коммуналку/накопления, harness и свои команды. Тесты используют временные данные и подмены; полный UI и реальные облачные/речевые интеграции ими не подтверждаются.

Для обновления только Markdown достаточно проверки ссылок/точности реестров. Исторические результаты 46/70/84 тестов нельзя переименовывать в новый запуск на 14 октября. Они сохранены в [VALIDATION](../VALIDATION.md).

## Лицензии и передача

- Общая лицензия исходного приложения не объявлена в просмотренных материалах.
- Personal/Silero: ограничения CC BY-NC-SA 4.0 по уведомлениям репозитория.
- Commercial/Qwen: Apache-2.0 для соответствующей модели; отдельные компоненты проверяются по upstream.
- Веса не хранятся в обычном Git-наборе TTS; portable-пакет может включать их.
- На графику, шрифты и исходные образцы нужны собственные подтверждения прав.
- THIRD_PARTY_NOTICES и licenses/Apache-2.0.txt сохраняют уведомления, но не заменяют полный реестр лицензий всего продукта.

Перед выпуском отдельно проверить чистую установку, реальные устройства/звук, доступность API, миграцию с резервной копией, подпись macOS и полный набор уведомлений. Это требования к готовности, а не уже выполненная сертификация.
