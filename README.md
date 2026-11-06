# LLM-сервис + Telegram-бот — FastAPI + модерация + admin + feedback (Б4.4)

Сквозной дипломный сервис: **backend на FastAPI** (обёртка над облачным OpenAI) + **Telegram-бот на aiogram 3**, который ходит в backend за всей LLM-логикой.

Бот — **тонкий клиент**: не хранит историю, не знает про LLM, не модерирует. Вся логика (модель, контекст, кеш, модерация, feedback, admin) — в backend.

На этом чекпоинте добавлены:
- **модерация** ввода/вывода (`app/moderation/`),
- **admin-эндпоинты** (`app/admin/`) под `X-Admin-Token`,
- **admin-команды в боте** (`/stats`, `/users`, `/broadcast`),
- **feedback** (`/feedback` + inline 👍/👎),
- **PostgreSQL** для `message_feedback` с volume `pg-data`.

---

## Что нового на этом чекпоинте (Б4.4)

| Что добавилось | Файл | Зачем |
|---|---|---|
| Модерация ввода/вывода | `app/moderation/service.py`, `app/moderation/keywords.yaml` | keyword-слой + опционально OpenAI Moderation |
| Интеграция в `ChatService` | `app/chat/service.py` | `check_input` перед LLM, `check_output` на финале |
| Логирование инцидентов | `app/moderation/service.py` (`_log_incident`) | structlog: `text_hash`, `text_masked`, `categories`, `blocked_by` |
| Admin endpoints | `app/admin/deps.py`, `routes.py`, `schemas.py` | `/chats/admin/stats`, `/users`, `/broadcast` под `X-Admin-Token` |
| Admin-команды в боте | `bot/handlers/admin.py` | `IsAdmin` на уровне роутера + `/stats`, `/users`, `/broadcast` |
| Feedback backend | `app/chat/feedback.py`, `app/db.py` | `POST /feedback` + таблица `message_feedback` с `UNIQUE` |
| Feedback bot | `bot/handlers/feedback.py`, `bot/keyboards/feedback.py` | inline 👍/👎 после ответа, `edit_reply_markup(None)` |
| PostgreSQL | `compose.yaml` (`postgres`, volume `pg-data`) | хранение feedback, `ON CONFLICT DO NOTHING` |
| Init БД | `app/main.py` (`lifespan`) | `init_db()` создаёт таблицу при старте |
| Понятные ошибки | `bot/services/errors.py` | `humanize_backend_error` — `403` → `🚫 ...`, без трейсбека |

---

## Куда смотреть

```
app/
├── core/config.py               # Settings: ADMIN_TOKEN, BOT_ADMIN_IDS, MODERATION_*
├── db.py                        # engine, async_session, init_db()
├── main.py                      # lifespan + init_db, include_router admin/feedback
├── moderation/
│   ├── service.py               # ModerationService: check_input / check_output
│   └── keywords.yaml            # regex-паттерны + категории
├── admin/
│   ├── deps.py                  # require_admin (X-Admin-Token)
│   ├── schemas.py               # StatsOut, UserOut, BroadcastBody, BroadcastResult
│   └── routes.py                # /chats/admin/stats, /users, /broadcast
├── chat/
│   ├── service.py               # ChatService: модерация входа/выхода, стрим
│   ├── feedback.py              # POST /feedback + INSERT ... ON CONFLICT
│   ├── routes.py                # /chats/{id}/messages: check_input до StreamingResponse
│   └── repository.py            # JSONL-хранилище чатов (как в Б4.1)
└── services/notifier.py         # POST {BOT_URL}/notify для broadcast

bot/
├── config.py                    # BOT_TOKEN, BACKEND_URL, ADMIN_TOKEN, BOT_ADMIN_IDS
├── handlers/
│   ├── __init__.py              # порядок: admin → commands → fsm → media → feedback → text
│   ├── admin.py                 # IsAdmin + /stats /users /broadcast
│   ├── feedback.py              # callback fb:<vote>:<message_id> → POST /feedback
│   ├── stream.py                # sendMessageDraft + троттлинг + клавиатура 👍/👎
│   ├── text.py                  # F.text → stream
│   ├── fsm.py                   # /ask → тема → вопрос
│   └── media.py                 # фото/голос/документ → stream
├── keyboards/
│   ├── feedback.py              # feedback_keyboard(message_id)
│   └── inline.py                # topics_kb()
└── services/
    ├── backend_client.py        # SSE + raise_for_status до yield
    └── errors.py                # humanize_backend_error

compose.yaml                     # app + bot + postgres + redis + phoenix
```

---

## Архитектура

```
Telegram ──► bot (aiogram 3) ──HTTP──► app (FastAPI) ──► OpenAI (proxyapi)
              │                            │
              │  POST /chats               │  moderation check_input
              │  POST /chats/{id}/messages │  chat-история (JSONL)
              │  POST /feedback            │  moderation check_output
              │  GET  /chats/admin/stats   │  INSERT INTO message_feedback
              │  GET  /chats/admin/users   │    (PostgreSQL, ON CONFLICT)
              │  POST /chats/admin/broadcast│
              │  POST /notify (от app)     │
              └── стрим в sendMessageDraft ◄── SSE
```

- Бот **не хранит** историю, не модерирует, не ходит в OpenAI.
- `owner_external_id = str(tg_user_id)` — ключ идентификации.
- Модерация — **только в backend**. В боте нет `openai`-импортов.
- Feedback — `(owner_external_id, message_id)` UNIQUE, защита от дубля на уровне БД.
- Admin — только с `X-Admin-Token`; бот-команды — только для `BOT_ADMIN_IDS`.

---

## Быстрый старт

Нужны: [`uv`](https://docs.astral.sh/uv/), Docker Desktop, токен бота из [@BotFather](https://t.me/BotFather), ключ OpenAI/ProxyAPI.

```bash
# 1. Зависимости
uv sync

# 2. Конфиг
cp .env.example .env
# заполнить:
#   LLM_OPENAI_API_KEY=sk-...
#   BOT_TOKEN=123456:ABC...
#   BOT_ADMIN_IDS=443426947
#   ADMIN_TOKEN=123-789-654-102
#   INTERNAL_TOKEN=change-me-long-random-string
#   DATABASE_URL=postgresql+asyncpg://chat:chat@postgres:5432/chat

# 3. Поднять всё (app + bot + postgres + redis + phoenix)
docker compose up --build -d

# 4. Статус
docker compose ps
# ожидаемо: postgres healthy, app healthy, bot Up

# 5. Swagger
# http://localhost:8000/docs
```

Локальный запуск бота без Docker (backend уже поднят):

```bash
uv run python -m bot
```

---

## Конфиг

`.env` (в `.gitignore`). Префикс вложенной секции — через `__`:

```dotenv
# --- LLM / backend ---
LLM_OPENAI_API_KEY=sk-...
LLM_BASE_URL=https://api.proxyapi.ru/openai/v1
LLM_DEFAULT_MODEL=gpt-4o-mini

# --- FastAPI / Redis ---
REDIS_URL=redis://redis:6379/0
INTERNAL_TOKEN=change-me-long-random-string

# --- PostgreSQL для feedback ---
DATABASE_URL=postgresql+asyncpg://chat:chat@postgres:5432/chat

# --- Модерация ---
MODERATION_ENABLED=true
MODERATION_USE_OPENAI=false
MODERATION_THRESHOLD=0.7

# --- Admin ---
ADMIN_TOKEN=123-789-654-102

# --- Telegram-бот ---
BOT_TOKEN=123456:ABC-DEF...
BOT_ADMIN_IDS=443426947
BOT_API_PORT=9000
# BACKEND_URL=http://localhost:8000     # локально без docker
# В docker подставляется из compose.yaml: BACKEND_URL=http://app:8000
```

`BOT_ADMIN_IDS` — список Telegram user_id через запятую **без скобок** (`443426947` или `443426947,123456789`). Валидатор в `bot/config.py` и `app/core/config.py` дополнительно принимает `[443426947]` (со скобками) — на случай копипаста.

---

## Модерация

**Вход:** `check_input` → keyword-слой (`keywords.yaml`) → опционально OpenAI Moderation. При срабатывании — `HTTPException(403, detail={"code": "moderation_blocked", "categories": [...]})`.

**Выход:** `check_output` на накопленном буфере стрима. При срабатывании — SSE-фрейм `{"type": "error", "code": "moderation_blocked"}` вместо `done`; ответ **не сохраняется** в историю.

**Логи:** structlog-событие `moderation_blocked` с `text_hash`, `text_masked`, `categories`, `blocked_by` — **без сырого текста**.

Пример:

```bash
curl.exe -s -o - -w "`nHTTP %{http_code}`n" -X POST `
  "http://127.0.0.1:8000/chats/<chat_id>/messages" `
  --form-string "content=как сварить наркотик" `
  -H "Accept: text/event-stream"
# ожидаемо:
# {"detail":{"code":"moderation_blocked","categories":["illegal"]}}
# HTTP 403
```

В логах `app`:

```
{"text_hash": "2a516a59e7675c8c", "text_masked": "Наркотик", "categories": ["illegal"], "blocked_by": "keywords", "event": "moderation_blocked", ...}
```

---

## Admin

Все эндпоинты защищены `X-Admin-Token` (`ADMIN_TOKEN` из env). Без токена — `422`, неверный — `401`.

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/chats/admin/stats` | `{total_messages_24h, active_users, avg_latency_ms, moderation_block_rate, feedback_up_ratio}` |
| `GET` | `/chats/admin/users?limit=50` | `[{owner_external_id, interface, message_count, last_seen}]` |
| `POST` | `/chats/admin/broadcast` | `{sent, failed}` |

Пример:

```powershell
$token = "123-789-654-102"

# stats
curl.exe -s -H "X-Admin-Token: $token" `
  "http://127.0.0.1:8000/chats/admin/stats"

# broadcast
$body = @{ message = "Тест broadcast"; interface_filter = "telegram" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/chats/admin/broadcast" `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Headers @{ "X-Admin-Token" = $token } `
  -Body ($body | ConvertTo-Json -Compress)
# ожидаемо: {"sent": N, "failed": M} + сообщение в Telegram
```

---

## Admin-команды в боте

Доступны только пользователям из `BOT_ADMIN_IDS`. Фильтр `IsAdmin` — **на уровне роутера** (`admin_router.message.filter(IsAdmin())`), а не внутри handler'а.

| Команда | Что делает |
|---|---|
| `/stats` | `GET /chats/admin/stats` → форматированный ответ |
| `/users` | `GET /chats/admin/users?limit=50` → топ-20 |
| `/broadcast <text>` | `POST /chats/admin/broadcast` с `interface_filter="telegram"` |

Для не-админов команды **молчат** (router-level filter). Ошибки backend → `humanize_backend_error`.

---

## Feedback

**Backend** (`app/chat/feedback.py`):

```http
POST /feedback
Content-Type: application/json

{"message_id": "2378", "owner_external_id": 443426947, "value": 1}
```

`INSERT INTO message_feedback ... ON CONFLICT (owner_external_id, message_id) DO NOTHING` — защита от дубля. Таблица создаётся `init_db()` в `lifespan` при старте `app`.

**Bot** (`bot/handlers/feedback.py`):

- после каждого ответа — inline-клавиатура 👍/👎 (`fb:up:<message_id>` / `fb:down:<message_id>`);
- callback парсит `fb:<vote>:<message_id>`, POST в `/feedback`;
- после сохранения — `edit_reply_markup(None)`, кнопки исчезают;
- `callback.answer("Спасибо!")` — всплывающее подтверждение.

**Проверка:**

```powershell
docker compose exec postgres psql -U chat -d chat -c `
  "SELECT message_id, value, count(*) FROM message_feedback GROUP BY message_id, value;"
```

Ожидаемо: **`count = 1`** у каждого `message_id` — дублей нет.

---

## Полный контракт backend

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `POST` | `/chats` | `{owner_external_id, interface}` | `{chat_id}` |
| `GET` | `/chats/{id}` | — | `Chat` |
| `POST` | `/chats/{id}/messages` | multipart `content` + `media` | SSE: `token` / `done` / `error` |
| `GET` | `/chats/{id}/messages` | — | `[ChatMessage]` |
| `DELETE` | `/chats/{id}/messages` | — | `{status:"ok"}` |
| `POST` | `/chats/{id}/system-message` | `{text, notify}` | `{status:"ok"}` |
| `POST` | `/feedback` | `{message_id, owner_external_id, value}` | `{status:"ok"}` |
| `GET` | `/chats/admin/stats` | — | `StatsOut` |
| `GET` | `/chats/admin/users` | — | `[UserOut]` |
| `POST` | `/chats/admin/broadcast` | `{message, interface_filter}` | `{sent, failed}` |

SSE-формат от `ChatService`:

- `data: {"type": "token", "delta": "..."}` — токен ответа;
- `data: {"type": "done"}` — конец;
- `data: {"type": "error", "code": "moderation_blocked", "categories": [...]}` — выходная модерация.

Бот (`bot/services/backend_client.py`) разбирает `type`, `yield delta` при `token`, `return` на `done`, `raise BackendError` на `error`.

---

## Стриминг в Telegram

`sendMessageDraft` (Bot API 10.0) + троттлинг `MIN_INTERVAL = 0.8` в `bot/handlers/stream.py`, `except TelegramRetryAfter: sleep(retry_after)` — без флуд-контроля. Финальный ответ `send_message` с inline-клавиатурой 👍/👎.

---

## Тесты

```bash
pytest tests/bot -v
```

Ожидаемо — 3+ passed (backend_client, fsm; опционально — feedback callback).

---

## Docker

Два отдельных образа:

### `Dockerfile` (backend)
- builder + runtime, `appuser` (UID 1000);
- `RUN mkdir -p /app/var/chats && chown -R appuser:appuser /app/var`;
- healthcheck `GET /ready`;
- `CMD ["uvicorn", "app.main:app", ...]`.

### `bot/Dockerfile` (бот)
- тот же паттерн, `CMD ["python", "-m", "bot"]`;
- healthcheck PID 1 (`/proc/1/cmdline`).

### `compose.yaml`

| Сервис | Образ | Порты | Зависит от |
|---|---|---|---|
| `phoenix` | `arizephoenix/phoenix:latest` | 6006, 4317 | — |
| `postgres` | `postgres:16-alpine` | 5432 | — |
| `redis` | `redis:7.4-alpine` | — | — |
| `app` | `llm-service:v1` | 8000 | `phoenix`, `redis`, `postgres` (healthy) |
| `bot` | `llm-bot:v1` | 9000 (`/notify` для broadcast) | `app` (healthy) |

Volumes: `phoenix-data`, `redis_data`, `chats-data` (→ `/app/var/chats`), **`pg-data`** (→ `/var/lib/postgresql/data`).

Env в `app`: `ADMIN_TOKEN`, `DATABASE_URL`, `INTERNAL_TOKEN`, `REDIS_URL`, `BOT_URL`, `CHAT_STORAGE_DIR`, `MODERATION_*`.

Env в `bot`: `BACKEND_URL=http://app:8000`, `ADMIN_TOKEN`, `BOT_ADMIN_IDS`, `INTERNAL_TOKEN`, `BOT_API_PORT`.

---

## Критерии проверки Б4.4

| Критерий | Как проверить |
|---|---|
| Backend возвращает `403` с `detail.code == "moderation_blocked"` | `curl ... content=наркотик` → `403 {"detail":{"code":"moderation_blocked",...}}` |
| Бот переводит в понятный текст, не трейсбек | Telegram `наркотик` → `🚫 Сообщение заблокировано модерацией.\nКатегории: illegal` |
| В боте нет `openai.moderation.create` / рейт-лимита | `docker compose exec bot python -c "import sys; print([m for m in sys.modules if 'openai' in m])"` → `[]` |
| Admin-команды только для `BOT_ADMIN_IDS` | `/stats` от не-админа → **тишина**; от админа → `📊 Статистика...` |
| 👍/👎 сохраняются с `UNIQUE (owner_external_id, message_id)` | `SELECT message_id, value, count(*) ... GROUP BY ...` → `count = 1` у каждого |
| `docker compose up` поднимает всё одной командой | `docker compose ps` → все сервисы `Up (healthy)` |
| Volume `pg-data` сохраняет данные | `docker compose down && up` → `SELECT count(*) FROM message_feedback` > 0 |
| `.env` в `.gitignore` | `git check-ignore -v .env` (если есть `.git`) |

---

## Почему такой подход

- **Модерация только в backend.** Бот не знает про OpenAI Moderation, нет рейт-лимита в боте — критерий ДЗ.
- **Admin под `X-Admin-Token`**, `Depends(require_admin)` — единая точка защиты. Минимум без JWT — по условиям ДЗ.
- **`IsAdmin` на уровне роутера.** Нельзя случайно забыть проверку внутри handler'а.
- **Feedback через PostgreSQL с UNIQUE.** `ON CONFLICT DO NOTHING` — защита от дубля на уровне БД, а не в коде.
- **`init_db()` в `lifespan`.** Таблица создаётся при старте, а не отдельной миграцией — минимум для ДЗ.
- **`humanize_backend_error`.** Единая точка перевода ошибок backend в понятный текст; `aread()` до `raise_for_status()` — чтобы не ловить `ResponseNotRead`.
- **Понятный контракт SSE.** `token`/`done`/`error` — бот обрабатывает все три.

---

## Ссылки

- [aiogram 3](https://docs.aiogram.dev/)
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [OpenAI Moderation API](https://platform.openai.com/docs/guides/moderation)
- [PostgreSQL — INSERT ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SSE (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Telegram Bot API](https://core.telegram.org/bots/api)