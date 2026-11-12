#!/usr/bin/env bash
# The single final check of supplier matching v2 on the HELD-OUT half: the same tool and code as match-v2-tune.sh,
# totals only in the log. The server refuses a second final run once one has reported (_matchv2_root.sh).
# Every Google call left of the task's 60 may be used here; tender kind questions come before tie-breaks.
set -uo pipefail
export MATCHV2_HALF=final MATCHV2_RUN_CAP=60 MATCHV2_TIEBREAK="${MATCHV2_TIEBREAK:-on}"
exec bash "$(dirname "$0")/match-v2-tune.sh"
