from bson import json_util
import psycopg

from airflow_utils.mongo_source import mongo_client
from warehouse.config import ROOT, Settings
from warehouse.csv_import import import_csvs, insert_rows, read_csv


POSTGRES_SEEDS = (
    ("master", "masters.csv"),
    ("product", "products.csv"),
    ("master_product", "master_products.csv"),
    ("client", "clients.csv"),
    ("order", "orders.csv"),
)


def csv_values(path):
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"Seed file is empty: {path}")
    columns = tuple(rows[0])
    values = [tuple(row[column] or None for column in columns) for row in rows]
    return columns, values


def seed_postgres(connection, directory):
    for table, filename in POSTGRES_SEEDS:
        columns, rows = csv_values(directory / filename)
        insert_rows(connection, "public", table, columns, rows)


def seed_mongo(database, directory):
    for path in sorted(directory.glob("*.json")):
        documents = json_util.loads(path.read_text(encoding="utf-8"))
        if not isinstance(documents, list):
            raise ValueError(f"MongoDB seed must contain a JSON array: {path}")
        collection = database[path.stem]
        for document in documents:
            collection.replace_one({"_id": document["_id"]}, document, upsert=True)


def seed(settings):
    with psycopg.connect(settings.dsn("source")) as connection:
        seed_postgres(connection, ROOT / "seeds" / "postgres")
        import_csvs(connection, ROOT / "seeds" / "csv", settings.get("SOURCE_TIMEZONE"))
    with mongo_client(settings) as client:
        seed_mongo(client[settings.get("MONGO_DB")], ROOT / "seeds" / "mongo")


if __name__ == "__main__":
    seed(Settings.from_env())
