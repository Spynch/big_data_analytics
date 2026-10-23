from alembic import command
from alembic.config import Config

from warehouse.bootstrap_mongo import bootstrap_mongo
from warehouse.config import ROOT, Settings


def migrate(settings):
    for target in ('source', 'warehouse'):
        config = Config(str(ROOT / f'alembic-{target}.ini'))
        config.attributes['settings'] = settings
        command.upgrade(config, 'head')
    bootstrap_mongo(settings)


if __name__ == '__main__':
    migrate(Settings.from_env())
