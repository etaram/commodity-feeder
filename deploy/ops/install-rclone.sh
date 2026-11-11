#!/usr/bin/env bash
# Installs rclone (used to copy encrypted backups to the owner's Google Drive). Configuration is done by the owner.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'export DEBIAN_FRONTEND=noninteractive; apt-get install -y -qq rclone >/dev/null 2>&1; rclone version | head -1; rclone listremotes 2>/dev/null | sed "s/^/remote: /"; echo "remotes listed"'
