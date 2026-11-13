#!/usr/bin/env bash
# Quality gate v1 over the server's supplier enrichment (leads/quality_gate.py): counts only in the public log;
# the list of refined keys stays on the server (/opt/sinder/enrich/refined.keys, root only).
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot python3 -I "$GITHUB_WORKSPACE/leads/quality_gate.py" /opt/sinder/enrich
