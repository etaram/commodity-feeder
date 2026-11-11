#!/usr/bin/env bash
# Runs as root on the server (called by backup.sh). Encrypted dump, then a restore into a throw-away database.
set -euo pipefail
cd /opt/sinder && mkdir -p backup/db
[ -f backup.key ] || { umask 077; openssl rand -base64 48 > backup.key; echo "new backup key created"; }
ts=$(date -u +%Y%m%dT%H%M%SZ); f=/opt/sinder/backup/db/sinder-$ts.sql.gz.enc
cd /opt/sinder/repo/deploy
psqlc() { docker compose exec -T db psql -U sinder -v ON_ERROR_STOP=1 "$@"; }
psqlc -d sinder -q <<'SQL'
create table if not exists backup_probe(id int primary key, note text, at timestamptz default now());
insert into backup_probe values (1, 'restore test row') on conflict (id) do update set at = now();
SQL
t0=$(date +%s)
docker compose exec -T db pg_dump -U sinder -d sinder | gzip | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:/opt/sinder/backup.key > "$f"
echo "backup written: $(basename "$f") ($(du -h "$f" | cut -f1)) in $(( $(date +%s)-t0 ))s"
t1=$(date +%s)
psqlc -d postgres -q -c "drop database if exists restore_test" -c "create database restore_test"
openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/opt/sinder/backup.key < "$f" | gunzip | psqlc -d restore_test -q >/dev/null
echo "restored into restore_test in $(( $(date +%s)-t1 ))s; row read back: $(psqlc -d restore_test -Atc 'select id, note from backup_probe')"
psqlc -d postgres -q -c "drop database restore_test"
find /opt/sinder/backup/db -name "*.enc" -mtime +14 -delete
echo "backups kept: $(ls -1 /opt/sinder/backup/db | wc -l)"
