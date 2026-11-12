#!/bin/sh
# Runs as root on the server (called by env-check.sh). Prints key NAMES and set/empty/missing, never a value.
E=/opt/sinder/repo/deploy/.env; X=/opt/sinder/server-instance/deploy/env.example
state() { # set | empty | missing for one key; a value that is only spaces and a "# comment" counts as empty
  if grep -qE "^$1=" "$E"; then v=$(grep -E "^$1=" "$E" | tail -1 | cut -d= -f2- | sed -E 's/^[[:space:]]*#.*$//; s/[[:space:]]+$//; s/^[[:space:]]+//')
    [ -n "$v" ] && echo set || echo empty; else echo missing; fi; }
echo "== env file: $([ -f "$E" ] && echo "present, mode $(stat -c %a "$E")" || echo MISSING)"
echo "== keys of env.example"
for k in $(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$X" | tr -d =); do printf "  %-28s %s\n" "$k" "$(state "$k")"; done
echo "== other keys in .env (names only)"
for k in $(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$E" | tr -d = | sort -u); do grep -qE "^$k=" "$X" || printf "  %-28s %s\n" "$k" "$(state "$k")"; done
echo "== public IPv4: $(curl -s --max-time 10 -4 ifconfig.me || echo unknown)"
echo "== listening TCP ports (not loopback)"; ss -ltnH | awk '{print $4}' | grep -vE '^127\.|^\[::1\]' | sort -u | tr '\n' ' '; echo
echo "== who holds 80/443"; docker ps --format '{{.Names}} {{.Ports}}' | grep -E ':(80|443)->' | sed -E 's/, \[::\][^,]*//g'
echo "== ufw"; (command -v ufw >/dev/null && ufw status | head -12) || echo "ufw not installed"
echo "== iptables INPUT policy and rules for 80/443"; iptables -S INPUT 2>/dev/null | grep -E '^-P|dport (80|443)\b' | head -6
echo "== database backups"; L=$(ls -1t /opt/sinder/backup/db/*.enc 2>/dev/null | head -1)
[ -n "$L" ] && echo "  newest $(basename "$L"), $(( ($(date +%s) - $(stat -c %Y "$L")) / 60 )) minutes old; kept $(ls -1 /opt/sinder/backup/db | wc -l)" || echo "  none"
echo "== containers"; docker ps --format '  {{.Names}}\t{{.Status}}'
echo "== resources"; free -h | sed -n 2p; df -h / | tail -1
