#!/bin/sh
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "local/$S3_BUCKET"
mc admin user add local "$S3_ETL_USER" "$S3_ETL_PASSWORD" >/dev/null
mc admin user add local "$S3_READ_USER" "$S3_READ_PASSWORD" >/dev/null
cat > /tmp/etl-policy.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:*"],"Resource":["arn:aws:s3:::$S3_BUCKET","arn:aws:s3:::$S3_BUCKET/*"]}]}
EOF
cat > /tmp/read-policy.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket"],"Resource":["arn:aws:s3:::$S3_BUCKET"]},{"Effect":"Allow","Action":["s3:GetObject"],"Resource":["arn:aws:s3:::$S3_BUCKET/cdm/*"]}]}
EOF
mc admin policy create local warehouse-etl /tmp/etl-policy.json
mc admin policy create local warehouse-read /tmp/read-policy.json
mc admin policy attach local warehouse-etl --user "$S3_ETL_USER"
mc admin policy attach local warehouse-read --user "$S3_READ_USER"
