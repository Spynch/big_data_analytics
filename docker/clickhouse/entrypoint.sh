#!/bin/sh
set -eu
case "$CLICKHOUSE_USER" in ''|*[!a-zA-Z0-9_]*) echo 'Invalid ClickHouse admin name' >&2; exit 1;; esac
cat > /etc/clickhouse-server/users.d/warehouse-admin.xml <<EOF
<clickhouse><users><${CLICKHOUSE_USER}>
<named_collection_control>1</named_collection_control>
</${CLICKHOUSE_USER}></users></clickhouse>
EOF
exec /entrypoint.sh "$@"
