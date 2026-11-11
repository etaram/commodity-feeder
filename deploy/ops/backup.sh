#!/usr/bin/env bash
# Encrypted backup of the database, then a full restore into a separate throw-away database to prove it works.
# The key lives in /opt/sinder/backup.key (root only). Off-site copy is a separate step. Prints no secrets.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c '
set -e
cd /opt/sinder && mkdir -p backup/db
[ -f backup.key ] || { umask 077; openssl rand -base64 48 > backup.key; echo "new backup key created"; }
ts=$(date -u +%Y%m%dT%H%M%SZ); f=backup/db/sinder-$ts.sql.gz.enc
t0=$(date +%s)
cd repo/deploy
docker compose exec -T db sh -c "psql -U sinder -d sinder -qc \"create table if not exists backup_probe(id int primary key, note text, at timestamptz default now()); insert into backup_probe values (1, \$\$restore test row\$\$) on conflict (id) do update set at = now()\""
docker compose exec -T db pg_dump -U sinder -d sinder | gzip | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:/opt/sinder/backup.key > /opt/sinder/$f
echo "backup written: $f ($(du -h /opt/sinder/$f | cut -f1)) in $(( $(date +%s)-t0 ))s"
t1=$(date +%s)
docker compose exec -T db sh -c "psql -U sinder -d postgres -qc \"drop database if exists restore_test\" -c \"create database restore_test\""
openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/opt/sinder/backup.key < /opt/sinder/$f | gunzip | docker compose exec -T db psql -U sinder -d restore_test -q >/dev/null
echo "restored into restore_test in $(( $(date +%s)-t1 ))s; rows read back:"
docker compose exec -T db psql -U sinder -d restore_test -Atc "select id, note from backup_probe"
docker compose exec -T db sh -c "psql -U sinder -d postgres -qc \"drop database restore_test\""
ls -1 /opt/sinder/backup/db | tail -3
find /opt/sinder/backup/db -name "*.enc" -mtime +14 -delete
'
