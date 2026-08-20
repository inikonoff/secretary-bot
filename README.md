# secretary-bot

Telegram-бот «Секретарь»: принимает клиента, проводит короткое AI-интервью и
формирует структурированное техническое задание для администратора.

Полная спецификация: [`docs/TZ_telegram_bot_zayavki_v1.1.md`](docs/TZ_telegram_bot_zayavki_v1.1.md)
и [`docs/AI_Specification_v1.1.md`](docs/AI_Specification_v1.1.md).

## Стек

Python 3.12 · aiogram 3.x (webhook на aiohttp) · asyncpg + PostgreSQL (Supabase) ·
Groq (`gpt-oss-20b` интервью / `gpt-oss-120b` финальное ТЗ, Whisper STT) ·
OpenRouter как fallback-провайдер · Render.com (Web Service, free tier) · UptimeRobot.

## Архитектура

```
app/
  config.py          — настройки из env (pydantic-settings)
  constants.py        — состояния State Machine, статусы, словари
  main.py              — aiohttp-приложение, webhook-эндпоинт, health-check
  db/
    schema.sql          — DDL (идемпотентно, безопасно перезапускать)
    pool.py, repo.py     — asyncpg-пул и репозитории по сущностям
  ai/
    schemas.py            — pydantic-контракты ответов LLM
    prompts.py              — системные промпты и сборка user-промптов
    clients.py                — HTTP-клиенты Groq/OpenRouter/Whisper
    orchestrator.py            — retry → repair → fallback поверх LLM-вызовов
  services/
    application_flow.py — состояние заявки + вызовы AI Orchestrator
    tz_generator.py       — генерация финального ТЗ + проверка качества
    debounce.py, locks.py, rate_limiter.py — защита от гонок/спама
    telegraph.py, reminders.py, tz_quality.py
  bot/
    keyboards.py, texts.py, middlewares.py, router.py
    handlers/            — start/new/help/interview/confirmation/admin
```

## Локальный запуск

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить реальными значениями
python -m scripts.apply_schema   # применить схему БД (идемпотентно)
python -m app.main
```

Бот поднимает aiohttp-сервер на `PORT` (по умолчанию 8080) с вебхуком на
`WEBHOOK_PATH` и health-check на `/health`. Локально вебхук Telegram не
достучится без публичного URL — для локальной отладки проще всего
прогнать функции сервисного слоя напрямую (см. `scripts/apply_schema.py`
как пример) либо пробросить порт через ngrok/cloudflared и указать этот
адрес в `WEBHOOK_BASE_URL`.

## Деплой на Render (free tier)

Free tier Render не даёт Background Worker, поэтому бот работает как
**Web Service на вебхуках** (не long polling), а UptimeRobot пингует
`/health`, чтобы сервис не засыпал.

1. Создать Web Service на Render, подключить репозиторий (см. `render.yaml`).
2. Build command: `pip install -r requirements.txt`, start command:
   `python -m app.main`.
3. Проставить все переменные окружения из `.env.example` (см. ниже).
4. `WEBHOOK_BASE_URL` — публичный URL сервиса, который выдаст Render
   (`https://<service>.onrender.com`), без хвостового слэша.
5. При старте бот сам вызывает `setWebhook` и применяет схему БД — ничего
   вручную дополнительно накатывать не нужно (но `scripts/apply_schema.py`
   доступен для ручного прогона/миграций).
6. Настроить в UptimeRobot HTTP(s)-монитор на `https://<service>.onrender.com/health`.

### Два независимых "не засыпающих" механизма

Тут на самом деле спят по разным причинам две разные вещи, и решения не связаны:

- **Render засыпает от отсутствия HTTP-трафика.** Решается пунктом 6 выше —
  внешний пинг `/health` каждые несколько минут не даёт free-tier инстансу
  уйти в сон.
- **Supabase приостанавливает free-tier проект примерно после 7 дней без
  обращений к БД** — даже если сам бот исправно отвечает на вебхуки, но
  клиенты им не пользуются. Это лечится не снаружи (UptimeRobot не видит
  БД), а изнутри: `app/services/supabase_keepalive.py` — фоновый цикл,
  который раз в `SUPABASE_KEEPALIVE_INTERVAL_SECONDS` (по умолчанию 6 часов)
  делает `select 1` через тот же asyncpg-пул, что и всё остальное. Ничего
  дополнительно настраивать не нужно — таск стартует вместе с ботом
  (`on_startup` в `app/main.py`) и живёт, пока жив процесс.

  Тот же приём (независимый фоновый пинг Supabase) используется в других
  ботах на этом стеке — там, где подключение к Supabase идёт через
  `supabase-py`, пингуют через REST-клиент; здесь БД — обычный Postgres
  через `asyncpg`, поэтому проще и надёжнее пинговать напрямую SQL-запросом,
  без лишней зависимости.

## Переменные окружения

См. `.env.example` — полный список с комментариями. Ключевые:

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен бота от @BotFather |
| `ADMIN_ID` | Telegram ID администратора (доступ к `/admin`) |
| `DATABASE_URL` | Postgres connection string (Supabase → Project Settings → Database) |
| `GROQ_API_KEY` | платный тариф Groq, доступ к `gpt-oss-20b`/`gpt-oss-120b`/Whisper |
| `OPENROUTER_API_KEY` | fallback-провайдер |
| `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET` | публичный адрес сервиса и секрет для проверки заголовка Telegram |
| `TELEGRAPH_HELP_URL` | можно оставить пустым — страница `/help` создаётся автоматически при первом старте |

## Заметки по реализации относительно ТЗ v1.1

Часть пунктов ТЗ оставлена «на усмотрение реализации» (п. 65) — решения,
принятые в коде:

- **Срок запуска (п.16)** — состояние `WAITING_DEADLINE` вставлено между
  адаптивным интервью и экраном подтверждения: вопрос задаётся один раз,
  сразу как только AI-интервью решает, что информации достаточно
  (`action=understanding`), следующий ответ пользователя сохраняется как есть.
- **Напоминание о незавершённой сессии (п.55)** — фоновый цикл раз в 15
  минут проверяет заявки без активности дольше `INCOMPLETE_SESSION_REMINDER_HOURS`
  и без отправленного напоминания; текст/таймаут — на усмотрение, можно
  поменять в `app/services/reminders.py`.
- **Порог «хулиганства» (п.20.3)** — если тема уточняющего вопроса не
  меняется 3 раза подряд (`SAME_TOPIC_ABANDON_THRESHOLD`), заявка помечается
  `flagged_as_abuse` и закрывается с просьбой создать новую через `/new`.
- **Debounce/rate limit/lock** — реализованы в памяти процесса (не Redis):
  достаточно для одного инстанса Render free tier; при горизонтальном
  масштабировании потребуется вынести в Redis.

## v1.2 — правки после завершения заявки

Отдельный лёгкий AI-контур поверх уже завершённой (`status=completed`) заявки —
таблица `revisions` со своим независимым статусом (🆕/👀/🔧/✅), без цикла
«Добавить информацию», без quality-gate и без отдельного `.md`-файла (см.
`docs/TZ_telegram_bot_zayavki_v1.1.md` п.67-68 и `docs/AI_Specification_v1.1.md` §33).

Решения, принятые в коде там, где ТЗ оставляет implementation-детали открытыми:

- **Черновик правки — в памяти, не в БД.** Пока клиент не нажал «✅ Верно»,
  описание правки и «Как я понял» существуют только в
  `RevisionDraftRegistry` (`app/services/revision_drafts.py`). Строка в
  `revisions` появляется только при подтверждении — сам флоу задуман как
  однопроходный и не требует переживания рестарта на полпути (в отличие от
  основного интервью, где `project_context`/`state` персистентны).
- **Нет кнопки отмены на этапе «Как я понял».** ТЗ п.68.2 явно оставляет
  только «✅ Верно». Если клиент вместо этого присылает новое сообщение —
  оно трактуется как переформулировка правки, анализ прогоняется заново.
- **Точка входа для клиента — экран `/start`.** Кнопка «✏️ Предложить
  правку» показывается только для последней завершённой заявки клиента —
  выбора среди нескольких прошлых заявок в интерфейсе нет (ТЗ п.64), так что
  давать её для более старых завершённых заявок было бы противоречиво.
- **Автопереход 🆕→👀 у правок** — по аналогии с автопереходом статуса
  заявки при открытии карточки (п.43), хотя для правок это явно не
  прописано; выбрано для единообразия админ-интерфейса.

## Что дальше

- Прогнать сценарии из ТЗ п.66 (Acceptance Criteria) и AI Specification §31
  на реальном боте после того, как заведены все ключи из `.env.example`.
- При желании — заменить дефолтный текст Bot Description (`app/bot/texts.py`)
  и содержимое страницы `/help` (`app/services/telegraph.py`) на финальные
  маркетинговые формулировки.
