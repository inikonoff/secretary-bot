# Бэклог правок — secretary-bot

Дата: 2026-09-03  
Повод: клиент не доходил до конца интервью.

## Симптомы из лога

1. Groq `400 Bad Request` / `json_validate_failed`  
   `max completion tokens reached before generating a valid document`
2. Fallback на OpenRouter → `404 Not Found`  
   `This model is unavailable for free`  
   `openai/gpt-oss-20b:free` снят, предлагают платный `openai/gpt-oss-20b`

Telegram/aiogram тут ни при чём: апдейты обрабатывались за 133–739 мс.

## Что сделано в этом архиве

### 1. Лимит completion-токенов
- `app/ai/clients.py` — в запрос добавлен `max_completion_tokens`
- `app/ai/orchestrator.py` — 4096 на шаг интервью, 12288 на финальное ТЗ
- для моделей `gpt-oss*` на Groq: `reasoning_effort=low`, `include_reasoning=false`
- таймаут HTTP поднят с 30с до 60с
- если `content` пустой, берём `reasoning` (на случай скрытого CoT)

### 2. Замена снятой free-модели OpenRouter
Было:
- `openai/gpt-oss-20b:free` (интервью) — больше не существует
- `openai/gpt-oss-120b` (ТЗ, без `:free`)

Стало:
- интервью: `google/gemma-4-31b-it:free`
- финальное ТЗ: `minimax/minimax-m3:free`

Файлы: `app/config.py`, `.env.example`, `README.md`

На Render обязательно переписать env вручную — дефолты из кода не перебьют уже заданные переменные.

### 3. Ужатие JSON
- `app/ai/prompts.py` — инструкция «пиши компактно»; обрезка history / summary / пунктов; `compact_project_context()`
- `app/ai/schemas.py` — лимиты длины summary, числа пунктов списков, `client_message`

## Как накатить

Скопировать файлы поверх репозитория с сохранением путей:

```
.env.example
README.md
app/config.py
app/ai/clients.py
app/ai/orchestrator.py
app/ai/prompts.py
app/ai/schemas.py
```

Env на проде:

```
OPENROUTER_MODEL_INTERVIEW=google/gemma-4-31b-it:free
OPENROUTER_MODEL_FINAL=minimax/minimax-m3:free
```

Альтернатива для ТЗ, если нужны «мозги» сильнее MiniMax M3:

```
OPENROUTER_MODEL_FINAL=z-ai/glm-5.2:free
```

Не ставить `openrouter/free` — роутер выбирает случайную free-модель, JSON будет нестабилен.

## Ограничения OpenRouter :free

- 20 запросов/мин всегда
- обычно 50 запросов/день без оплаты, 1000/день после разовых $10 на аккаунт
- список `:free` моделей ротируется; перед сменой slug проверять `GET https://openrouter.ai/api/v1/models`

## Что ещё имеет смысл сделать (не сделано)

- [ ] Логировать `usage.completion_tokens` / `finish_reason`, чтобы видеть обрезку
- [ ] На `json_validate_failed` сразу ретраить тот же провайдер с большим `max_completion_tokens`, не прыгая в OpenRouter
- [ ] Не гонять весь `project_context` каждый ход — дельта-обновление полей
- [ ] Для финального ТЗ убрать `response_format=json_object` и отдавать markdown отдельно: 20 разделов в одном JSON — главный риск обрезки
- [ ] Пользователю при `AIUnavailableError` слать понятный текст, а не тишину
- [ ] Прогнать 1 живой диалог до `understanding` + генерацию ТЗ на staging
- [ ] Если Gemma/MiniMax снимут с `:free` — запасные slug: `nvidia/nemotron-3-super-120b-a12b:free`, `z-ai/glm-5.2:free`
