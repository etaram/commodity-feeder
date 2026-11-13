#!/usr/bin/env bash
# Website discovery for suppliers with no website on record (see deploy/enrich/_enrich_root.sh discover). Starts the
# job when it is not running, else prints its counts. The log is public: counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" discover "$GITHUB_WORKSPACE"
