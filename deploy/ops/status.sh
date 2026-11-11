#!/usr/bin/env bash
# Read-only status of the server. Prints no secrets.
echo "== host"; hostname; uptime; nproc; free -h | sed -n 1,3p; df -h / | tail -1
echo "== docker"; docker ps --format '{{.Names}}\t{{.Status}}' 2>&1 | head -20
echo "== firewall"; sudo -n ufw status 2>/dev/null | head -8 || echo "(needs root)"
echo "== mirror backup"; du -sh /opt/sinder/backup/commodity-feeder.git 2>/dev/null; tail -2 /opt/sinder/backup/mirror.log 2>/dev/null; pgrep -fa "git clone" | head -2 || echo "no clone running"
echo "== repo copy"; git -C /opt/sinder/repo log --oneline -1 2>&1
echo "== runners"; ls /home/runner 2>/dev/null | tr '\n' ' '; echo
echo "== env file present"; [ -f /opt/sinder/repo/deploy/.env ] && echo yes || echo no
