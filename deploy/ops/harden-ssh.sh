#!/usr/bin/env bash
# Key-only SSH: password sign-in is switched off after checking that the operator key is installed.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot grep -q "sinder-server" /root/.ssh/authorized_keys || { echo "operator key missing - not changing anything"; exit 1; }
asroot sh -c 'printf "PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n" > /etc/ssh/sshd_config.d/00-sinder.conf'
asroot sshd -t && asroot systemctl reload ssh
echo "effective settings:"; asroot sshd -T | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication) "
asroot fail2ban-client status sshd 2>/dev/null | grep -E "Currently banned|Total failed" || true
