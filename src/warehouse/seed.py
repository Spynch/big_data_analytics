import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal

from psycopg import sql
from .connections import postgres, mongo, s3
from .contracts import PG
from .extract import parse_time
from .settings import ROOT, setting


def upsert(conn, schema, table, pk, fields, rows):
    names = [f[0] for f in fields]
    stage = sql.Identifier("seed_" + table)
    target = sql.SQL("{}.{}").format(sql.Identifier(schema),sql.Identifier(table))
    conn.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(stage,target))
    cols = sql.SQL(",").join(map(sql.Identifier,names))
    with conn.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(stage,cols)) as copy:
        for row in rows:
            values = []
            for key,typ,nullable in fields:
                value = row.get(key)
                if value is not None:
                    if typ == "time": value = parse_time(value)
                    elif typ == "date" and isinstance(value,str): value = date.fromisoformat(value)
                    elif typ == "money": value = Decimal(value)
                    elif typ in ("long","int"): value = int(value)
                values.append(value)
            copy.write_row(values)
    updated = [n for n in names if n != pk]
    update = sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(n),sql.Identifier(n)) for n in updated)
    old = sql.SQL(",").join(sql.SQL("t.{}").format(sql.Identifier(n)) for n in updated)
    new = sql.SQL(",").join(sql.SQL("EXCLUDED.{}").format(sql.Identifier(n)) for n in updated)
    conn.execute(sql.SQL("INSERT INTO {} AS t ({}) SELECT {} FROM {} ON CONFLICT ({}) DO UPDATE SET {} "
                        "WHERE ({}) IS DISTINCT FROM ({})").format(target,cols,cols,stage,sql.Identifier(pk),update,old,new))


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Missing CSV header: {path.name}")
        yield from reader


def external_rows(directory, name):
    seen = set()
    occurrences = Counter()
    for number,row in enumerate(csv_rows(directory / (name + ".csv")),start=2):
        try:
            if name == "user_behavior":
                mapped = {"id":int(row["Id"]), "date_time":row["date_time"], "client_id":int(row["user_id"])}
            elif name == "order_statuses":
                mapped = {key:row[key] for key in ["id","date_time","client_id","quantity","payment_amount"]}
                mapped["id"] = int(mapped["id"])
            else:
                datetime.strptime(row["date_id"],"%Y%m%d")
                if len(row["date_id"]) != 8:
                    raise ValueError("date_id must be YYYYMMDD")
                canonical = json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"))
                occurrences[canonical] += 1
                key = canonical + "|" + str(occurrences[canonical])
                identifier = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],"big") & ((1 << 63)-1)
                mapped = {"id":identifier, **{key:row[key] for key in ["date_id","sales_qty","sales_amt"]}}
            if mapped["id"] in seen:
                raise ValueError(f"Duplicate or colliding ID {mapped['id']}")
            seen.add(mapped["id"])
            yield mapped
        except (KeyError,ValueError) as exc:
            raise ValueError(f"{name}.csv line {number}: {exc}") from exc


def run(directory=None):
    directory = directory or ROOT / "seeds"
    craft = json.loads((ROOT / "seeds/craft.json").read_text(encoding="utf8"))
    client = s3()
    for name in ["order_statuses","user_behavior","marketing_research"]:
        path = directory / (name+".csv")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        client.upload_file(str(path),setting("S3_BUCKET"),f"input/{checksum}/{path.name}")
    with postgres(admin=True) as conn:
        for dataset,(schema,table,pk,fields) in PG.items():
            if table == "logs": continue
            rows = craft[table] if schema == "public" else external_rows(directory,table)
            upsert(conn,schema,table,pk,fields,rows)
    from bson import json_util
    documents = json_util.loads((ROOT / "seeds/mongo.json").read_text(encoding="utf8"),
                                json_options=json_util.JSONOptions(tz_aware=True))
    with mongo(admin=True) as connection:
        db = connection[setting("MONGO_DB")]
        for name,rows in documents.items():
            for row in rows:
                if db[name].find_one({"_id":row["_id"]}) != row:
                    db[name].replace_one({"_id":row["_id"]},row,upsert=True)
    print("Seed completed; unchanged source rows were not updated")
