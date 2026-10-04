# Служба поддержки

Дементьев Ярослав, вариант 2. Заявки, комментарии, статусы и контроль срока ответа.
Python 3.13, FastAPI, PostgreSQL 16, Bootstrap. Для запуска нужны Git и Docker Compose.

## Запуск

```sh
git clone https://github.com/Binar-code/oksp_hw_01.git
cd oksp_hw_01
cp .env.example .env
docker compose up -d db
docker compose run --build --rm app python -m scripts.seed small
docker compose up -d app
```

Схема создаётся при наполнении. Интерфейс: http://localhost:8080.
Пользователь `demo / demo`, сотрудник `staff / demo`.
В `.env`: `APP_PORT=8080` - порт, `POSTGRES_PASSWORD=changeme` - пароль БД.

`app/` - сервис, SQL и интерфейс, `scripts/` - наполнение и замеры, `tests/` - тесты, `docker/` - Dockerfile.

## Тесты и замеры

```sh
docker compose run --rm app python -m pytest -q
```

Перед каждым замером сбросить данные выбранным наполнением. Сначала `small`, затем повторить команды с `work`:

```sh
docker compose stop app
docker compose run --rm app python -m scripts.seed small
docker compose up -d app
docker compose exec -T app python -m scripts.measure small --output report_data/
```

```sh
docker compose exec -T app python -m scripts.compare --output report_data/
```

Для следующей пары выбрать новое имя каталога. Результаты сохраняются в `report_data/`: `raw.csv` - запросы, `summary.csv` - статистика, `counts.csv` - число строк. Не выполнять другие операции во время замеров. Измеряются все 9 операций контракта. По умолчанию 5 прогревов и 30 повторов под `staff`, HTTP p50, p95 и максимум. Разложение: среднее серверное время, SQL execute с драйвером и оставшаяся обработка.

| Наполнение | Пользователи | Категории | Заявки | Комментарии |
|---|---:|---:|---:|---:|
| small | 50 | 5 | 300 | 900 |
| work | 3000 | 10 | 50000 | 150000 |

Пустая БД: `docker compose run --rm app python -m app.db --reset` при остановленном приложении. Вход доступен после наполнения. Полное удаление данных: `docker compose down -v`. Обновление кода: `docker compose up -d --build`.

## API

Вход устанавливает cookie `session` на 8 часов. После перезапуска нужен повторный вход. Без входа API возвращает 401, HTML перенаправляет на `/login`. JSON-ошибки: `detail` со строкой, при 422 со списком ошибок. Время в ISO 8601. Ответы не кешируются.

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| GET /login | Нет | 200, форма | Нет |
| POST /login | Форма: username, password | 303 на /, cookie | 401 |
| POST /logout | Нет | 303 на /login, удаление cookie | Нет |
| POST /api/tickets | JSON: title (1-200), body (1-10000), category_id больше 0 | 201, заявка | 401, 404, 422 |
| PATCH /api/tickets/{id}/status | id, JSON: status | 200, заявка | 401, 403, 404, 409, 422 |
| POST /api/tickets/{id}/comments | id, JSON: body (1-10000) | 201, комментарий | 401, 403, 404, 422 |
| GET / | page от 1, по умолчанию 1, status необязателен | 200, HTML, список по 20 заявок, id по убыванию и форма создания | 422 |
| GET /tickets/{id} | Целочисленный id | 200, карточка | 404, 422 |
| GET /summary | Нет | 200, сводка | Нет |

Заявка: `{id, user_id, category_id, title, body, status, created_at}`.
Комментарий: `{id, ticket_id, user_id, body, created_at}`.
Карточка HTML показывает заявку, категорию, автора, комментарии по времени и id, время первого ответа в минутах и нарушение норматива. Сводка HTML показывает общее число заявок и по каждой категории: всего, открыто, с нарушением и долю нарушений. Пустые категории включены.

Статусы: `new`, `in_progress`, `closed`. Меняет только сотрудник, строго в этом порядке, иначе 409. Все видят все заявки. Комментируют автор и сотрудник, включая закрытые заявки, иначе 403. 404 означает отсутствие заявки или категории. Пробелы по краям текста удаляются. Пустой status отключает фильтр, страница за пределами списка показывает пустой список.

Первый ответ - первый комментарий сотрудника. Нарушение - превышение норматива ответа, без ответа считается время ожидания. Открытые статусы: new и in_progress. Доля нарушений считается среди открытых заявок категории. Схема API: `/docs`.
