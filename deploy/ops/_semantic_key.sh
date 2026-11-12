# Sourced by bench-semantic.sh and embed-universe.sh (runner user). Puts the supplier index key into a file only the
# runner user can read, for the root step to hand to the model container; the file is removed when the job ends.
# The key: repository secret WEB_INDEX_KEY, else the private universe sheet, tab Config (service account), as
# supplier-eval does. Never printed (masked in the log in any case).
KEYF="$RUNNER_TEMP/semantic-key-$GITHUB_RUN_ID"; rm -f "$KEYF"
trap 'rm -f "$KEYF"' EXIT
K="${WEB_INDEX_KEY:-}"
if [ -z "$K" ] && [ -n "${GOOGLE_SERVICE_ACCOUNT_JSON:-}" ]; then
  K=$(docker run --rm -e GOOGLE_SERVICE_ACCOUNT_JSON -v "$GITHUB_WORKSPACE":/w:ro -w /w python:3.12-slim sh -c \
    "pip install -q --disable-pip-version-check requests google-auth >/dev/null 2>&1; python -c \"from leads.push import UNIVERSE_SHEET, Sheets; print(next((r[1] for r in Sheets().values(UNIVERSE_SHEET, 'Config!A1:B10') if len(r) > 1 and r[0] == 'WEB_INDEX_KEY'), ''))\"" 2>/dev/null || true)
fi
if [ -n "$K" ]; then echo "::add-mask::$K"; (umask 077; printf 'WEB_INDEX_KEY=%s\n' "$K" > "$KEYF"); echo "index key: found (masked)"
else echo "index key: not found (no repository secret, and the Config tab did not return it)"; KEYF=""; fi
unset K
