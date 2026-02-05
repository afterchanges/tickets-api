# Tickets API

FastAPI-сервис для создания и управления тикетами

---

## 1) Возможности

### 1.1. Тикеты

- Создание тикета, получение списка, получение по ID, обновление (PATCH), мягкое удаление.
- Статусы и переходы (workflow):
  - `NEW` → `IN_PROGRESS` или `CANCELED`
  - `IN_PROGRESS` → `DONE` или `CANCELED`
  - `DONE` / `CANCELED` — конечные состояния
- Комментарии к тикету.
- Аудит-события (events) по тикету (создание/изменение/переход/комментарий/удаление).
- Фильтры/поиск/сортировка списка тикетов.
- Идемпотентность создания тикета через заголовок `Idempotency-Key` (Redis).

### 1.2. Аутентификация и роли

- JWT access/refresh.
- Refresh-токены хранятся в БД и поддерживают ротацию.
- Роли: `USER`, `AGENT`, `ADMIN`.

### 1.3. Наблюдаемость и надежность

- Структурные JSON-логи.
- `X-Request-Id` middleware: если заголовка нет — генерируется UUID, прокидывается в ответ и добавляется в логи.
- Healthchecks:
  - `/healthz` — liveness
  - `/readyz` — readiness (проверяет DB + Redis)
- Prometheus метрики: `/metrics`.

### 1.4. Ограничения

- Rate limiting (Redis-backed) на эндпойнты регистрации и логина.

### 1.5. Опциональный сидинг ADMIN пользователя

- При старте приложения можно создать начального ADMIN из переменных окружения.

---

## 2) Технологический стек

- Python 3.11
- FastAPI + Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.0 (async) + asyncpg
- Alembic (async migrations)
- Redis 7
- JWT: `python-jose`
- Пароли: `argon2-cffi`
- Логи: `structlog` + `orjson`
- Метрики: `prometheus-client`
- Тесты: `pytest`, `pytest-asyncio`, `httpx`
- Docker + docker-compose

---

## 3) Запуск сервиса

### 3.1. Требования

- Docker Desktop (Windows/macOS/Linux)

### 3.2. Запуск

```bash
docker compose up -d --build
```

API будет доступен:

- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

### 3.3. Остановка

```bash
docker compose down
```

Если нужно удалить данные Postgres:

```bash
docker compose down -v
```

---

## 4) Конфигурация (.env)

Проект читает переменные окружения из `.env`.

Пример (у вас уже есть `.env`):

- `APP_ENV` — окружение (`dev` и т.п.)
- `LOG_LEVEL` — уровень логов (`INFO`, `DEBUG`)

### 4.1. База данных

- `DATABASE_URL` — строка подключения SQLAlchemy async:
  - `postgresql+asyncpg://tickets:tickets@db:5432/tickets`

### 4.2. Redis

- `REDIS_URL` — строка подключения Redis:
  - `redis://redis:6379/0`

### 4.3. JWT

- `JWT_SECRET` — секретный ключ подписи JWT
- `JWT_ACCESS_TTL_MIN` — TTL access токена (в минутах)
- `JWT_REFRESH_TTL_DAYS` — TTL refresh токена (в днях)

### 4.4. CORS

- `CORS_ORIGINS` — список origin в JSON-формате, например:
  - `[
"http://localhost:3000",
"http://127.0.0.1:3000"
]`

### 4.5. Rate limiting

- `RATE_LIMIT_ENABLED` — включить/выключить (`true/false`)
- `RATE_LIMIT_WINDOW_SEC` — окно (сек)
- `RATE_LIMIT_LOGIN_PER_IP` — лимит логинов на IP за окно
- `RATE_LIMIT_LOGIN_PER_EMAIL` — лимит логинов на email за окно
- `RATE_LIMIT_REGISTER_PER_IP` — лимит регистраций на IP за окно

### 4.6. Сидинг администратора (опционально)

- `SEED_ADMIN` — включить сидинг (`true/false`)
- `ADMIN_EMAIL` — email администратора
- `ADMIN_PASSWORD` — пароль администратора (минимум 12 символов)

---

## 5) Миграции (Alembic)

### 5.1. Применить миграции

```bash
docker compose exec api alembic upgrade head
```

### 5.2. Создать новую миграцию

```bash
docker compose exec api alembic revision --autogenerate -m "your_message"
```

---

## 6) Тесты

Запуск тестов в контейнере:

```bash
docker compose exec api pytest -q
```

---

## 7) API: аутентификация

Базовые эндпойнты:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/auth/me`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`

### 7.1. Как авторизоваться в Swagger

1. Выполните `POST /v1/auth/login`.
2. Скопируйте `access_token`.
3. В Swagger UI нажмите **Authorize** и вставьте токен в формате:
   - `Bearer <access_token>`

---

## 8) API: тикеты

### 8.1. Основные эндпойнты

- `POST /v1/tickets` — создать тикет
- `GET /v1/tickets` — список тикетов
- `GET /v1/tickets/{ticket_id}` — тикет по ID
- `PATCH /v1/tickets/{ticket_id}` — частичное обновление
- `POST /v1/tickets/{ticket_id}/transition` — смена статуса
- `DELETE /v1/tickets/{ticket_id}` — soft delete
- `GET /v1/tickets/{ticket_id}/events` — аудит-события
- `POST /v1/tickets/{ticket_id}/comments` — добавить комментарий
- `GET /v1/tickets/{ticket_id}/comments` — список комментариев

### 8.2. Права доступа (суть)

- `USER`:
  - видит только свои тикеты (где он `reporter`)
  - не может назначать исполнителя (assignee)
  - не может делать transition
- `AGENT`:
  - видит все тикеты
  - может делать transition
- `ADMIN`:
  - как `AGENT` + может просматривать удалённые тикеты через `include_deleted=true`

### 8.3. Идемпотентность создания тикета

Для `POST /v1/tickets` можно передать заголовок:

- `Idempotency-Key: <любая строка/uuid>`

Если повторить запрос с тем же `Idempotency-Key`, сервис вернёт тот же ответ, не создав дубль (при доступном Redis).

### 8.4. Фильтры/пагинация/сортировка

Список тикетов (`GET /v1/tickets`) поддерживает:

- `limit`, `offset`
- фильтры: `status`, `priority`, `assignee_id`, `reporter_id`, `tag`, `q`
- `include_deleted=true` (только ADMIN)
- `sort`: например `-created_at`, `priority`, `status`, `due_at`, `updated_at`.

---

## 9) Observability эндпойнты

- `GET /healthz` — liveness
- `GET /readyz` — readiness (DB + Redis)
- `GET /metrics` — Prometheus

---

## 10) Postman

В репозитории есть готовые файлы Postman:

- `postman/tickets-api.postman_collection.json`
- `postman/localhost-8000.postman_environment.json`

Импорт:

1. Postman → Import → File → выбрать оба JSON.
2. Выбрать environment `tickets-api (localhost:8000)`.
3. Запустить коллекцию: сначала `Auth` (register/login), затем `Tickets`.

---

## 11) Troubleshooting

### 11.1. Ошибка "email_taken" / "invalid_credentials"

- `email_taken` означает, что пользователь уже зарегистрирован.
- `invalid_credentials` означает неверный пароль.
  Решения:
- используйте новый email
- или очистите таблицы в dev базе (осторожно — удалит данные):

```bash
docker compose exec db psql -U tickets -d tickets -c "TRUNCATE refresh_tokens, ticket_events, ticket_comments, tickets, users RESTART IDENTITY CASCADE;"
```

### 11.2. Readiness возвращает 503

Обычно означает, что недоступен Postgres или Redis.
Проверьте:

```bash
docker compose ps
docker compose logs -n 200 api
docker compose logs -n 200 db
docker compose logs -n 200 redis
```
