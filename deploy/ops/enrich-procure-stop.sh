#!/usr/bin/env bash
# Pause the corporate procurement scan (frees memory, e.g. while the leads merge runs). Start again with enrich-procure.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" procure-stop "$GITHUB_WORKSPACE"
