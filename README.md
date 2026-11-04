# Лабораторная работа: хранилище данных

Проект загружает данные из PostgreSQL и MongoDB в PostgreSQL-хранилище. Загрузка запускается DAG `warehouse_refresh` в Apache Airflow.

```text
PostgreSQL source ─┐
                   ├─ Airflow/Python → STG → DDS → CDM
MongoDB source ────┘
```

## Слои

- `source` — исходные таблицы магазина, три CSV-таблицы и журнал `public.logs`.
- `stg` — данные источников почти без преобразований.
- `dds` — аналитическая модель: измерения `dim_*` и факты `fact_*`.
- `cdm` — готовые представления с показателями для отчётов.

## Запуск

Нужны Docker Desktop и Docker Compose.

```bash
docker compose up -d --build
docker compose run --rm seed
```

После запуска Airflow доступен по адресу http://127.0.0.1:8080. Логин и пароль по умолчанию: `admin` / `admin`.

В интерфейсе Airflow нужно включить DAG `warehouse_refresh` и запустить его. Для проверки без интерфейса можно выполнить ту же загрузку напрямую:

```bash
docker compose run --rm refresh
```

Результат первого задания:

```sql
SELECT *
FROM cdm.craft_customer_monthly
ORDER BY report_period, client_id;
```

Остановка:

```bash
docker compose down
```

Проверка Python-кода линтером:

```bash
python -m pip install -r requirements.txt
ruff check src dags
```

Настройки портов и паролей при необходимости копируются из `.env.example` в локальный `.env`. Для учебного локального стенда заданы простые значения по умолчанию.

## Как создаются данные

При первом создании Docker-томов PostgreSQL автоматически выполняет SQL из `sql/init/`:

- `source-schema.sql` создаёт таблицы источника и триггеры журнала;
- `warehouse-stg.sql` создаёт STG;
- `warehouse-dds.sql` создаёт DDS;
- `warehouse-functions.sql` создаёт функции разбора MongoDB JSON и дат;
- `airflow-db.sql` создаёт служебную БД Airflow;
- `sql/cdm/views.sql` создаёт витрины CDM.

Команда `docker compose run --rm seed` добавляет демонстрационные данные в PostgreSQL и MongoDB. Три CSV читаются из `seeds/csv/`.

## Как работает загрузка

1. Триггеры исходного PostgreSQL записывают `INSERT`, `UPDATE`, `DELETE` и `TRUNCATE` в `public.logs`.
2. Airflow читает события, чей `id` больше последнего загруженного `stg.pg_logs.id`.
3. События применяются к таблицам STG. MongoDB загружается в STG полным снимком.
4. `sql/dds/rebuild.sql` перестраивает таблицы DDS из STG.
5. Представления CDM автоматически показывают результат запросов к DDS.

Весь шаг выполняется одной транзакцией PostgreSQL-хранилища: при ошибке незавершённые изменения STG и DDS откатываются.

## Где смотреть на защите

| Что объяснять | Файл |
|---|---|
| Исходная модель и журнал | `sql/init/source-schema.sql` |
| Демонстрационные данные | `src/warehouse/seed.py` |
| DAG Airflow | `dags/warehouse_refresh.py` |
| Общий порядок ETL | `src/airflow_utils/refresh.py` |
| Чтение журнала PostgreSQL | `src/airflow_utils/postgres_source.py` |
| Чтение MongoDB | `src/airflow_utils/mongo_source.py` |
| Загрузка STG | `src/airflow_utils/loader.py` |
| Построение DDS | `sql/dds/rebuild.sql` |
| Расчёт витрин | `sql/cdm/views.sql` |

## Первое задание

Витрина `cdm.craft_customer_monthly` имеет зерно «клиент × отчётный месяц» и содержит 17 полей из задания.

- Общая оплаченная сумма считается по всем заказам клиента, у которых заполнено `paid_at`.
- Количество созданных, незавершённых и находящихся в работе заказов относится к месяцу создания.
- Завершённые заказы, средняя цена, медиана длительности, популярная категория и популярный мастер относятся к месяцу завершения.
- При одинаковой популярности мастеров выбирается мастер с минимальным `master_id`.
- Идентификатор строки строится из клиента и месяца с помощью `md5`.

Главный SQL первого задания находится в `sql/cdm/views.sql`, начиная с `CREATE VIEW cdm.craft_customer_monthly`.
