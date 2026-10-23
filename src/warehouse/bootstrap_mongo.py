from warehouse.config import Settings
from airflow_utils.mongo_source import COLLECTIONS, mongo_client


def bootstrap_mongo(settings):
    with mongo_client(settings, admin=True) as client:
        database = client[settings.get('MONGO_DB')]
        names = database.list_collection_names()
        for collection, key in COLLECTIONS.items():
            if collection not in names:
                database.create_collection(collection)
            database[collection].create_index(key, unique=True)
        username = settings.get('MONGO_ETL_USER')
        if not database.command('usersInfo', username)['users']:
            database.command('createUser', username, pwd=settings.get('MONGO_ETL_PASSWORD'),
                             roles=[{'role': 'read', 'db': database.name}])


if __name__ == '__main__':
    bootstrap_mongo(Settings.from_env())
