module.exports = {
  async up(db) {
    const integer = {bsonType: ['int', 'long']};
    const date = {bsonType: 'date'};
    const money = {bsonType: 'decimal'};
    const text = {bsonType: 'string'};
    const definitions = {
      clients: {
        required: ['_id', 'client_id', 'name', 'update_time'],
        properties: {_id: {bsonType:'objectId'}, client_id: integer, name:text,
          phone:text, email:text, login:text, birthday:date,
          address:{bsonType:'object'}, update_time:date}
      },
      restaurant: {
        required: ['_id', 'restaurant_id', 'name'],
        properties: {_id:{bsonType:'objectId'}, restaurant_id:integer,
          name:text, phone:text, email:text, founding_day:date, address:{bsonType:'object'}}
      },
      orders: {
        required: ['_id','order_id','restaurant_id','client_id','order_date',
          'ordered_dish','cost','payment','payed_by_bonuses','bonus_for_visit','final_status','update_time'],
        properties: {_id:{bsonType:'objectId'}, order_id:integer, restaurant_id:integer,
          client_id:integer, order_date:date, ordered_dish:{bsonType:'array'},
          cost:money, payment:money, payed_by_bonuses:money, bonus_for_visit:money,
          final_status:text, update_time:date}
      }
    };
    for (const [name, schema] of Object.entries(definitions)) {
      const validator = {$jsonSchema:{bsonType:'object', ...schema}};
      if ((await db.listCollections({name}).toArray()).length) {
        await db.command({collMod:name, validator, validationLevel:'strict', validationAction:'error'});
      } else {
        await db.createCollection(name, {validator, validationLevel:'strict', validationAction:'error'});
      }
      const key = name === 'clients' ? 'client_id' : name === 'orders' ? 'order_id' : 'restaurant_id';
      await db.collection(name).createIndex({[key]:1}, {unique:true});
    }
    await db.collection('orders').createIndex({client_id:1, order_date:1});
    await db.collection('orders').createIndex({restaurant_id:1, order_date:1});
  },
  async down() { throw new Error('Destructive rollback is unsupported'); }
};
