#!/usr/bin/env bash
# Corporate procurement pages scan (see deploy/enrich/_enrich_root.sh procure). Starts the job when it is not running,
# else prints its counts. The log is public: counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" procure "$GITHUB_WORKSPACE"
