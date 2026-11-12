#!/usr/bin/env bash
# Loads one deal dossier into the production app through its own route (POST /api/deal, the same validation, journal and
# activity log as the panel), as the owner's account. The repository is public, so the dossier travels ENCRYPTED to a
# key that exists only on this server:
#   1. the first run creates /opt/sinder/import/key.pem (root only) and prints its PUBLIC key;
#   2. the dossier is encrypted to that public key (deploy/ops/import/<name>.key = RSA-OAEP wrapped passphrase,
#      <name>.enc = AES-256-CBC, PBKDF2, base64) and committed;
#   3. the next run decrypts it here and hands it to deploy/ops/_deal_import.js inside the app container.
# The owner's session is signed inside the container with AUTH_SECRET exactly as lib/auth.ts signs one (10 minutes,
# never printed). Nothing is sent outside the system, no approval is created. The log shows ids, kinds and counts only.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot_i() { docker run --rm -i --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- "$@"; }
K=/opt/sinder/import
asroot sh -c "mkdir -p $K && chmod 700 $K && { [ -f $K/key.pem ] || { openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out $K/key.pem 2>/dev/null && chmod 600 $K/key.pem && echo 'new import key created'; }; }"
echo "== import public key (encrypt the dossier to this)"
asroot openssl pkey -in $K/key.pem -pubout

D="$(dirname "$0")/import"
shopt -s nullglob
files=("$D"/*.enc)
if [ ${#files[@]} -eq 0 ]; then echo "== no encrypted dossier in deploy/ops/import: nothing to load"; exit 0; fi
for enc in "${files[@]}"; do
  name=$(basename "$enc" .enc); key="$D/$name.key"
  echo "== dossier $name"
  [ -f "$key" ] || { echo "ERROR  $name.key is missing"; exit 1; }
  PASS=$(base64 -d < "$key" | asroot_i openssl pkeyutl -decrypt -inkey $K/key.pem -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256)
  [ -n "$PASS" ] || { echo "ERROR  could not unwrap the passphrase (encrypted to another key?)"; exit 1; }
  base64 -d < "$enc" | PASS="$PASS" openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:PASS \
    | docker exec -i sinder-server-app node -e "$(cat "$(dirname "$0")/_deal_import.js")"
done
