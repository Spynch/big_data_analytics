# Лабораторная работа: хранилище данных

Проект загружает данные из PostgreSQL и MongoDB в PostgreSQL-хранилище. Загрузка запускается DAG `warehouse_refresh` в Apache Airflow.

```text
PostgreSQL source ─┐
                   ├─ Airflow/Python → STG → DDS → CDM
MongoDB source ────┘

CSV-файлы ─────────── Airflow/Python → external_source (в хранилище)
```

## Слои

- `source` — исходные таблицы магазина и журнал `public.logs`.
- `external_source` — три таблицы внешних CSV-источников непосредственно в хранилище.
- `stg` — данные источников почти без преобразований.
- `dds` — аналитическая модель: измерения `dim_*` и факты `fact_*`.
- `cdm` — готовые представления с показателями для отчётов.

## Запуск

Нужны Docker Desktop, Docker Compose и `make`.

```bash
make run
```

Команда собирает Docker-образ, запускает сервисы, загружает демонстрационные данные и выполняет первый ETL-процесс. Повторный запуск безопасен: загрузка демонстрационных данных выполняется идемпотентно.

После запуска Airflow доступен по адресу http://127.0.0.1:8080. Логин и пароль по умолчанию: `admin` / `admin`.

Airflow работает в учебном режиме `standalone` и хранит свою служебную SQLite-базу внутри контейнера. Пересоздание контейнера сбрасывает только историю запусков Airflow, но не данные источников и хранилища.

В интерфейсе Airflow можно запустить DAG `warehouse_refresh`: он загружает три
CSV-файла непосредственно в схему `external_source` хранилища, переносит данные
PostgreSQL и MongoDB в STG и перестраивает DDS.
Для проверки без интерфейса можно выполнить ту же загрузку напрямую:

```bash
make refresh
```

Результат первого задания:

```sql
SELECT *
FROM cdm.craft_customer_monthly
ORDER BY report_period, client_id;
```

Остановка:

```bash
make down
```

Проверка Compose-конфигурации и Python-кода:

```bash
make check
```

Настройки портов и паролей при необходимости копируются из `.env.example` в локальный `.env`. Для учебного локального стенда заданы простые значения по умолчанию.

## Как создаются данные

При первом создании Docker-томов PostgreSQL автоматически выполняет SQL из `sql/init/`:

- `source-schema.sql` создаёт таблицы источника и триггеры журнала;
- `warehouse-stg.sql` создаёт STG;
- `warehouse-external-source.sql` создаёт схему и таблицы внешних CSV-источников в хранилище;
- `warehouse-dds.sql` создаёт DDS;
- `warehouse-functions.sql` создаёт функции разбора MongoDB JSON и дат;
- `sql/cdm/views.sql` создаёт витрины CDM.

Команда `make seed` добавляет демонстрационные данные в PostgreSQL и MongoDB. Данные отделены от кода загрузчика:

- `seeds/postgres/` содержит CSV-файлы исходной модели магазина;
- `seeds/mongo/` содержит коллекции в Extended JSON с типами ObjectId, Date и Decimal128;
- `seeds/csv/` содержит три внешних CSV-файла из задания.

Сервисы `seed`, `refresh` и Airflow читают CSV напрямую с компьютера через Docker
bind mount. После добавления новой строки достаточно сохранить CSV и запустить
DAG `warehouse_refresh` в Airflow; отдельный `make seed` для CSV не нужен.
При каждом запуске три таблицы `external_source` заменяются актуальным содержимым CSV.

## Как работает загрузка

1. Три CSV-файла напрямую загружаются в одноимённые таблицы схемы `external_source` в хранилище. Для второго задания дальнейшие преобразования не выполняются.
2. Триггеры исходного PostgreSQL записывают `INSERT`, `UPDATE`, `DELETE` и `TRUNCATE` в `public.logs`.
3. Airflow читает новые события и применяет их к таблицам STG. MongoDB загружается в STG полным снимком.
4. `sql/dds/rebuild.sql` перестраивает DDS для данных магазина и ресторанов.
5. Представление CDM первого задания автоматически показывает результат запроса к DDS.

Весь шаг выполняется одной транзакцией PostgreSQL-хранилища: при ошибке незавершённые изменения STG и DDS откатываются.

## Где смотреть на защите

| Что объяснять | Файл |
|---|---|
| Исходная модель и журнал | `sql/init/source-schema.sql` |
| Загрузка демонстрационных данных | `src/warehouse/seed.py` |
| Наборы демонстрационных данных | `seeds/postgres/`, `seeds/mongo/`, `seeds/csv/` |
| DAG Airflow | `dags/warehouse_refresh.py` |
| Общий порядок ETL | `src/airflow_utils/refresh.py` |
| Прямая загрузка CSV в `external_source` | `src/warehouse/csv_import.py` |
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

## Второе задание

В PostgreSQL-хранилище создана и подключена схема `external_source`. Данные из
трёх CSV-файлов загружаются в таблицы `external_source.order_statuses`,
`external_source.user_behavior` и `external_source.marketing_research`.
Для этих данных не создаются дополнительные таблицы STG/DDS и аналитические
витрины CDM, поскольку по заданию требуется подключить внешний источник к хранилищу.
