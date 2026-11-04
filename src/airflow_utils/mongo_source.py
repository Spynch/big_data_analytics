import json

from bson import ObjectId, json_util
from pymongo import MongoClient

COLLECTIONS = {"clients": "client_id", "orders": "order_id", "restaurant": "restaurant_id"}


def mongo_client(settings):
    return MongoClient(
        host=settings.get("MONGO_HOST"),
        port=int(settings.values.get("MONGO_CONNECT_PORT", "27017")),
        username=settings.get("MONGO_USER"),
        password=settings.get("MONGO_PASSWORD"),
        authSource="admin",
        tz_aware=True,
        serverSelectionTimeoutMS=10000,
    )


def extract_mongo(settings):
    snapshot = {}
    with mongo_client(settings) as client:
        database = client[settings.get("MONGO_DB")]
        for collection in COLLECTIONS:
            rows = []
            for document in database[collection].find().sort("_id", 1):
                if not isinstance(document["_id"], ObjectId):
                    raise ValueError(f"{collection}: _id must be ObjectId")
                raw = json_util.dumps(
                    document,
                    json_options=json_util.CANONICAL_JSON_OPTIONS,
                )
                payload = json.loads(raw)
                rows.append((str(document["_id"]), payload))
            snapshot[f"mongo_{collection}"] = rows
    return snapshot
