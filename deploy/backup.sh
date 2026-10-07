#!/bin/sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required}"
: "${BACKUP_S3_URI:?BACKUP_S3_URI is required}"
TMP="/tmp/rugged-backup-$(date +%s).dump"
pg_dump "$DATABASE_URL" --format=custom --file="$TMP"
aws s3 cp "$TMP" "$BACKUP_S3_URI/$(date -u +%Y/%m/%d)/rugged-$(date -u +%Y%m%dT%H%M%SZ).dump"
rm -f "$TMP"
