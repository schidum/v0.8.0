# 🌾 Agro Monitoring API

Система точного земледелия на базе **FastAPI** с CQRS-архитектурой, жизненным циклом полей, управлением техникой и фоновой генерацией отчётов.

---

## Содержание

- [Технологический стек](#технологический-стек)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Модели данных](#модели-данных)
- [Жизненный цикл поля](#жизненный-цикл-поля)
- [Роли и доступ (RBAC)](#роли-и-доступ-rbac)
- [API — эндпоинты](#api--эндпоинты)
- [Фоновые задачи (Celery)](#фоновые-задачи-celery)
- [WebSocket](#websocket)
- [Быстрый старт](#быстрый-старт)
- [Переменные окружения](#переменные-окружения)
- [Известные ограничения](#известные-ограничения)

---

## Технологический стек

| Компонент | Технология |
|---|---|
| Web-фреймворк | FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async / `mapped_column`) |
| База данных | SQLite (dev) / PostgreSQL-совместимо |
| Аутентификация | JWT (python-jose) + PBKDF2-SHA256 |
| Очередь задач | Celery 5 + RabbitMQ 3.6.6 |
| Backend результатов | `rpc://` (встроен в RabbitMQ) |
| WebSocket | FastAPI WebSocket + `ConnectionManager` |
| Хэширование паролей | passlib (pbkdf2_sha256) |
| Генерация PDF | fpdf2 |
| Pydantic | v2 (`model_validator`, `model_config`) |
| Python | 3.8+ |

---

## Архитектура

Проект реализует **CQRS (Command Query Responsibility Segregation)**:

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Router                    │
│   /api/v1/...                                       │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
    Command Side              Query Side
    (запись / ORM)        (чтение / raw SQL)
           │                       │
    CommandHandler            PersonQuery
    PersonCommandHandler      EquipmentQuery
           │                       │
    Repository             text() + DTO
    (SQLAlchemy ORM)       (без ORM-загрузки)
           │
    Domain Events
    (Celery + RabbitMQ)
```

**Принципы:**
- Команды идут через `CommandHandler` → `Repository` → ORM
- Запросы используют `text()` (raw SQL) и возвращают Pydantic DTO без загрузки ORM-объектов
- Доменные события публикуются в RabbitMQ и обрабатываются воркерами Celery
- Позиции техники рассылаются через WebSocket при каждом обновлении

---

## Структура проекта

```
app/
├── main.py                          # точка входа, lifespan, CORS
├── config.py                        # Settings (pydantic-settings, .env)
├── database.py                      # engine, AsyncSessionLocal, Base, get_db
├── dependencies.py                  # get_current_person, require_roles,
│                                    # require_field_access, rate_limit_login
├── celery_app.py                    # инициализация Celery + RabbitMQ
│
├── models/
│   └── __init__.py                  # все ORM-модели + Enum-классы
│
├── schemas/
│   └── __init__.py                  # все Pydantic v2 DTO (In/Out/Command)
│
├── repositories/                    # Data Access Layer (async SQLAlchemy)
│   ├── __init__.py
│   └── ...                          # FieldRepository, PersonRepository, ...
│
├── services/
│   ├── __init__.py                  # AuthService, PersonService, EquipmentService, ...
│   ├── field_service.py             # FieldService с управлением состояниями
│   └── field_state_transition.py   # FieldStateTransitionValidator (state machine)
│
├── cqrs/
│   ├── commands/
│   │   └── person_commands.py       # CreatePersonCommand, UpdatePersonCommand
│   ├── handlers/
│   │   └── person_handler.py        # PersonCommandHandler
│   ├── queries/
│   │   └── person_queries.py        # PersonQuery (raw SQL)
│   ├── dto/
│   │   └── person_dto.py            # PersonReadDTO
│   ├── events.py                    # DomainEvent, PersonCreated, FieldStatusChanged
│   ├── event_publisher.py           # publish_domain_event (Celery task)
│   └── event_handlers.py           # handle_domain_event (воркер Celery)
│
├── routers/
│   ├── __init__.py                  # api_router, сборка всех роутеров
│   ├── auth.py                      # POST /auth/login
│   ├── fields.py                    # CRUD полей + /transition + /status
│   ├── persons.py                   # CRUD персонала (legacy, без CQRS)
│   ├── points.py                    # GPS-точки
│   ├── measurement_maps.py          # Карты измерений
│   ├── ph.py                        # Измерения pH
│   ├── humidity.py                  # Измерения влажности
│   ├── notifications.py             # Уведомления (Celery)
│   ├── reports.py                   # Генерация PDF-отчётов (Celery)
│   ├── ws.py                        # WebSocket /ws/connect
│   ├── commands/
│   │   ├── persons.py               # CQRS команды: создание/обновление
│   │   ├── equipment.py             # PATCH /{id}/position
│   │   └── tasks.py                 # POST /tasks/create, PATCH /complete
│   └── queries/
│       ├── persons.py               # GET /persons (CQRS)
│       ├── equipment.py             # GET /equipment (с фильтрацией для driver)
│       └── tasks.py                 # GET /tasks
│
├── tasks/
│   ├── __init__.py
│   ├── notifications.py             # send_notification_task
│   └── reports.py                   # generate_completed_tasks_report
│
└── websocket/
    └── manager.py                   # ConnectionManager (broadcast)
```

---

## Модели данных

### Основные сущности

| Модель | Таблица | Описание |
|---|---|---|
| `Person` | `persons` | Пользователи системы (все роли) |
| `PersonRole` | `person_roles` | M2M: пользователь ↔ роли |
| `Field` | `fields` | Поля с жизненным циклом |
| `FieldBoundary` | `field_boundaries` | Граничные точки полигона поля |
| `GpsPoint` | `gps_points` | GPS-точки внутри поля |
| `MeasurementMap` | `measurement_maps` | Серия замеров (дата + тип) |
| `PhMeasurement` | `ph_measurements` | Значения pH по точкам |
| `HumidityMeasurement` | `humidity_measurements` | Значения влажности по точкам |
| `Equipment` | `equipment` | Единица техники (с GPS-позицией) |
| `Task` | `tasks` | Задания (назначение, выполнение) |
| `Fueling` | `fuelings` | Факты заправки техники |
| `Notification` | `notifications` | Уведомления пользователям |

### Ownership

Все ключевые сущности (`Field`, `Equipment`, `Task`, `Fueling`) содержат `owner_id → persons.id` для изоляции данных между организациями.

---

## Жизненный цикл поля

Поле проходит через 10 состояний (`FieldStatusEnum`). Переходы валидируются `FieldStateTransitionValidator`.

```
                    ┌─────────────┐
             ┌─────▶│ preparation │◀──────────────────────────┐
             │      └──────┬──────┘                           │
             │             │                                  │
             │             ▼                                  │
             │         ┌────────┐                             │
             │    ┌───▶│ sowing │                             │
             │    │    └───┬────┘                             │
             │    │        │                                  │
             │    │        ▼                         ┌────────────────────┐
             │    │   ┌───────────┐   ──disease──▶   │      disease       │
             │    │   │ monitoring│                  └──────────┬─────────┘
             │    │   └─────┬─────┘                            │
             │    │         │                         ┌────────▼──────────┐
             │    │         ▼                         │  residue_removal  │──┐
             │    │    ┌───────────┐                  └────────┬──────────┘  │
             │    │    │ harvesting│                           │             │
             │    │    └─────┬─────┘                 ┌────────▼──────────┐  │
             │    │          │                        │   deep_plowing    │──┤
             │    │          ▼                        └────────┬──────────┘  │
             │    │  ┌──────────────────────┐                  │             │
             │    │  │post_harvest_processing│       ┌─────────▼──────────┐  │
             │    │  └──────────┬───────────┘        │chemical_treatment  │  │
             │    │             │                    └─────────┬──────────┘  │
             │    │             ▼                              │             │
             │    │      ┌────────────┐◀────────────────────── ▼ ◀──────────┘
             └────┘      │ field_free │
                         └────────────┘
```

**Правила болезни:** из `disease` можно пропустить любой из этапов восстановления (`residue_removal` → `deep_plowing` → `chemical_treatment`), но нельзя вернуться к `disease` из `preparation` или `field_free`.

---

## Роли и доступ (RBAC)

| Роль | Описание | Ключевые права |
|---|---|---|
| `manager` | Менеджер | Полный доступ ко всем данным и операциям |
| `agronomist` | Агроном | Чтение полей типа `health`, GPS-точки |
| `chemist` | Химик | Запись pH/влажности, карты измерений |
| `driver` | Водитель | Обновление позиции только своей техники, видит только свои задания |

**Особые ограничения:**
- Управление пользователями доступно только с заголовком `X-App-Client: web`
- Поля типа `irrigation` доступны только роли `manager`
- Водитель фильтруется по `assigned_driver_id == current.id`

---

## API — эндпоинты

Все маршруты монтируются под префиксом `/api/v1`.

### Auth

| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/login` | Получить JWT-токен |

### Персонал (`/persons`)

| Метод | Путь | Требуемая роль | Описание |
|---|---|---|---|
| GET | `/persons/` | manager + web | Список всех пользователей |
| POST | `/persons/` | manager + web | Создать пользователя |
| GET | `/persons/{id}` | manager + web | Получить пользователя |
| PATCH | `/persons/{id}` | manager + web | Обновить пользователя |
| DELETE | `/persons/{id}` | manager + web | Удалить пользователя |

> CQRS-версия доступна через `/api/v1/persons/create` (command) и отдельный query-роутер.

### Поля (`/fields`)

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| GET | `/fields/` | любая | Список полей (фильтр по `map_type`) |
| POST | `/fields/` | manager | Создать поле |
| GET | `/fields/{id}` | по типу карты | Получить поле |
| PATCH | `/fields/{id}` | manager | Обновить метаданные |
| DELETE | `/fields/{id}` | manager | Удалить поле |
| GET | `/fields/{id}/boundary` | любая | Граничные точки |
| GET | `/fields/{id}/status` | любая | Текущий статус + доступные переходы |
| POST | `/fields/{id}/transition` | manager | Сменить статус поля |
| GET | `/fields/{id}/status-info` | любая | Описание текущего статуса |

### GPS-точки

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| GET | `/fields/{id}/points/` | по доступу к полю | Все точки поля |
| GET | `/fields/{id}/points/bbox` | по доступу к полю | Точки в bounding box |
| POST | `/fields/{id}/points/find-or-create` | chemist | Найти или создать точку |
| DELETE | `/fields/{id}/points/{pid}` | chemist | Удалить точку |

### Измерения

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `/measurements/ph/` | chemist | Добавить pH |
| GET | `/measurements/ph/point/{id}` | любая | История pH по точке |
| GET | `/measurements/ph/field/{id}/bbox` | по доступу | pH в bbox |
| DELETE | `/measurements/ph/{id}` | chemist | Удалить pH |
| POST | `/measurements/humidity/` | chemist | Добавить влажность |
| GET | `/measurements/humidity/point/{id}` | любая | История влажности |
| GET | `/measurements/humidity/field/{id}/bbox` | по доступу | Влажность в bbox |
| DELETE | `/measurements/humidity/{id}` | chemist | Удалить влажность |

### Техника (`/equipment`)

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| GET | `/equipment/` | любая | Список техники (driver видит только свою) |
| PATCH | `/equipment/{id}/position` | любая | Обновить GPS-позицию |

### Задания (`/tasks`)

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `/tasks/create` | manager | Создать задание |
| PATCH | `/tasks/{id}/complete` | любая | Отметить выполненным |
| GET | `/tasks/` | любая | Список заданий |

### Уведомления

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `/notifications/` | любая | Отправить уведомление (через Celery) |
| GET | `/notifications/my` | любая | Мои непрочитанные уведомления |

### Отчёты

| Метод | Путь | Роль | Описание |
|---|---|---|---|
| POST | `/reports/generate` | manager | Запустить генерацию PDF-отчёта |
| GET | `/tasks/{task_id}` | любая | Статус любой фоновой Celery-задачи |

---

## Фоновые задачи (Celery)

Все задачи объявлены через `@shared_task` и зарегистрированы в модуле `app.tasks`.

### `send_notification_task`

Путь: `app/tasks/notifications.py`

- Принимает `dict` (сериализованный `NotificationCreate`)
- Создаёт запись `Notification` в БД через async-сессию
- Возвращает `{"notification_id": ..., "person_id": ..., "level": ..., "status": "success"}`
- Автоматический retry до 3 раз с задержкой 60 с

### `generate_completed_tasks_report`

Путь: `app/tasks/reports.py`

- Загружает все завершённые задания из БД
- Генерирует PDF через `fpdf2`
- Сохраняет файл в `static/reports/report_{task_id}.pdf`
- Возвращает `{"report_url": "/static/reports/..."}`

### Мониторинг задач

```
GET /api/v1/tasks/{celery_task_id}
```

Возвращает статус Celery-задачи: `PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED`.

---

## WebSocket

**Эндпоинт:** `ws://host/api/v1/ws/connect`

После подключения клиент отправляет JSON-приветствие (например, `{"user_id": 42}`).

**Автоматический broadcast** при обновлении позиции техники:

```json
{
  "type": "equipment_position_updated",
  "equipment": {
    "id": 5,
    "name": "Комбайн К-300",
    "latitude": 51.1234,
    "longitude": 71.5678,
    "last_update": "2026-04-23T10:00:00"
  }
}
```

`ConnectionManager` хранит список активных соединений в памяти процесса. При сбое соединения удаляет его из списка автоматически.

---

## Быстрый старт

### 1. Установить зависимости

```bash
pip install -r requirements.txt
```

### 2. Создать `.env` с секретным ключом

```bash
python create_key.py
```

Или вручную:

```env
SECRET_KEY=ваш_64_символьный_секрет
DATABASE_URL=sqlite+aiosqlite:///./agro.db
RABBITMQ_URL=amqp://guest:guest@localhost:5672//
```

### 3. Запустить сервер

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3.1 Запустить сервер с SSL

```bash
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8443 \
  --ssl-keyfile certs/key.pem \
  --ssl-certfile certs/cert.pem \
  --reload
```


### 4. Запустить Celery-воркер

```bash
celery -A app.celery_app worker --loglevel=info
```

> На Windows добавьте флаг `--pool=solo`

### 5. Открыть Swagger

```
http://127.0.0.1:8000/docs
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SECRET_KEY` | *(обязательно)* | JWT-секрет, минимум 32 символа |
| `ALGORITHM` | `HS256` | Алгоритм подписи JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Время жизни токена |
| `DATABASE_URL` | `sqlite+aiosqlite:///./agro.db` | URL базы данных |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672//` | URL брокера RabbitMQ |
| `CELERY_RESULT_BACKEND` | `rpc://` | Backend результатов Celery |
| `APP_TITLE` | `Агро API — Точное земледелие` | Заголовок в Swagger |
| `APP_VERSION` | `0.3.2` | Версия приложения |

---

## Известные ограничения

- **SQLite** не поддерживает `array_agg` — в `PersonQuery` используется `group_concat` с ручным парсингом JSON. При переходе на PostgreSQL заменить на `array_agg`.
- **Rate limiter** реализован in-memory (`defaultdict`). При перезапуске воркера счётчики сбрасываются. В production использовать Redis + slowapi.
- **WebSocket ConnectionManager** не масштабируется горизонтально. При нескольких воркерах нужен Redis Pub/Sub как транспорт.
- **Celery result backend** `rpc://` работает на RabbitMQ 3.6.6, но результаты доступны только в рамках одной сессии. Для persistence использовать Redis или PostgreSQL backend.
- Роутер `reports` временно отключён в `app/routers/__init__.py` (закомментирован) — раскомментировать после проверки зависимостей fpdf2.
- SSL-сертификаты для dev генерируются через `python create_ssl_cert.py` (требует OpenSSL).