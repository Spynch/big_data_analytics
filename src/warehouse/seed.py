from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from bson import Decimal128, ObjectId

from warehouse.config import ROOT, Settings
from warehouse.csv_import import import_csvs, upsert_rows
from airflow_utils.mongo_source import mongo_client


def utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def seed_postgres(connection):
    upsert_rows(connection, 'public', 'master', ('master_id', 'name', 'phone', 'address', 'birthday'), [
        (1, 'Anna Master', '+70000000001', 'Moscow', '1980-01-01'),
        (2, 'Boris Master', '+70000000002', 'Kazan', '1985-02-02'),
    ])
    upsert_rows(connection, 'public', 'product', ('product_id', 'name', 'description', 'type'), [
        (1, 'Cup', 'Handmade cup', 'ceramics'), (2, 'Scarf', 'Wool scarf', 'textile'),
    ])
    upsert_rows(connection, 'public', 'master_product', ('id', 'master_id', 'product_id', 'price'), [
        (1, 1, 1, Decimal('100.00')), (2, 2, 1, Decimal('200.00')), (3, 1, 2, Decimal('300.00')),
    ])
    upsert_rows(connection, 'public', 'client', ('client_id', 'name', 'phone', 'address', 'birthday', 'email'), [
        (key, f'Craft Client {key}', f'+7111111110{key}', 'Moscow', '1990-05-10', f'craft{key}@example.test')
        for key in range(1, 7)
    ])
    columns = ('order_id', 'master_id', 'product_id', 'client_id', 'order_date', 'delivery_date', 'status', 'paid_at')
    orders = [
        (1, 1, 1, 1, '2026-01-31T10:00:00Z', '2026-02-01T10:00:00Z', 'done', '2026-01-31T10:00:00Z'),
        (2, 2, 1, 1, '2026-02-02T10:00:00Z', '2026-02-03T10:00:00Z', 'done', None),
        (3, 1, 1, 1, '2026-02-01T10:00:00Z', '2026-02-11T10:00:00Z', 'done', '2026-02-01T10:00:00Z'),
        (4, 1, 2, 2, '2026-02-01T10:00:00Z', '2026-02-02T10:00:00Z', 'done', None),
        (5, 2, 1, 2, '2026-02-01T10:00:00Z', '2026-02-04T10:00:00Z', 'done', '2026-02-01T10:00:00Z'),
        (6, 1, 2, 3, '2026-01-10T10:00:00Z', None, 'in_progress', '2026-01-10T11:00:00Z'),
        (7, 1, 1, 3, '2026-02-01T10:00:00Z', None, 'created', None),
        (8, 2, 1, 3, '2026-02-02T10:00:00Z', None, 'cancelled', None),
        (9, 1, 1, 4, '2026-02-03T12:00:00Z', '2026-02-05T00:00:00Z', 'done', None),
        (10, 1, 1, 3, '2026-02-03T10:00:00Z', None, 'delivery', None),
        (11, 1, 1, 5, '2026-01-31T23:30:00-03:00', '2026-02-02T02:30:00Z', 'done', None),
    ]
    upsert_rows(connection, 'public', 'order', columns, orders)


def seed_mongo(database):
    restaurant = {
        '_id': ObjectId('650000000000000000000001'), 'restaurant_id': 1,
        'name': 'Demo Restaurant', 'phone': '+72222222222', 'email': 'restaurant@example.test',
        'founding_day': utc('2010-01-01'), 'address': 'Moscow, Demo street 1',
    }
    clients = [{
        '_id': ObjectId(f'66000000000000000000000{key}'), 'client_id': key,
        'name': f'Restaurant Client {key}', 'phone': f'+7333333333{key}',
        'email': f'restaurant{key}@example.test', 'birthday': utc('1995-06-15'),
        'login': f'guest{key}', 'update_time': utc('2026-02-01T10:00:00'),
    } for key in (1, 2)]
    clients[0]['address'] = {'city': 'Moscow', 'street': 'Demo', 'building': '2'}
    orders = [{
        '_id': ObjectId(f'67000000000000000000000{key}'), 'order_id': key,
        'restaurant_id': 1, 'client_id': 1 if key < 3 else 2,
        'order_date': utc('2026-02-01T10:00:00'),
        'ordered_dish': [{'name': 'Soup', 'quantity': 1}, {'name': 'Tea', 'quantity': 1}],
        'cost': Decimal128('120.10'), 'payment': Decimal128('100.10'),
        'payed_by_bonuses': Decimal128('20.00'), 'bonus_for_visit': Decimal128('5.00'),
        'final_status': 'closed' if key < 3 else 'created', 'update_time': utc('2026-02-01T11:00:00'),
    } for key in (1, 2, 3)]
    for collection, documents in (('restaurant', [restaurant]), ('clients', clients), ('orders', orders)):
        for document in documents:
            database[collection].replace_one({'_id': document['_id']}, document, upsert=True)


def seed(settings):
    with psycopg.connect(settings.dsn('source', 'app')) as connection:
        seed_postgres(connection)
        import_csvs(connection, ROOT / 'seeds' / 'csv', settings.get('SOURCE_TIMEZONE'))
    with mongo_client(settings, admin=True) as client:
        seed_mongo(client[settings.get('MONGO_DB')])


if __name__ == '__main__':
    seed(Settings.from_env())
