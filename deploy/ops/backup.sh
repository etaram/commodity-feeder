#!/usr/bin/env bash
# Encrypted backup of the database, then a full restore into a separate throw-away database to prove it works.
# The key lives in /opt/sinder/backup.key (root only). Off-site copy is a separate step. Prints no secrets.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'cd /opt/sinder/repo && git pull -q && bash deploy/ops/_backup_root.sh'
