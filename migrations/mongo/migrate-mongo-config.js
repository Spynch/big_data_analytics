const enc = encodeURIComponent;
module.exports = {
  mongodb: {
    url: `mongodb://${enc(process.env.MONGO_ADMIN)}:${enc(process.env.MONGO_PASSWORD)}@mongo-source:27017/?authSource=admin`,
    databaseName: process.env.MONGO_DB,
    options: {}
  },
  migrationsDir: 'versions', changelogCollectionName: 'migration_changelog',
  lockCollectionName: 'migration_lock', lockTtl: 0,
  migrationFileExtension: '.js', useFileHash: true,
  moduleSystem: 'commonjs'
};
