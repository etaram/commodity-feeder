#!/usr/bin/env bash
# One-time setup of the Sinder server (Ubuntu 24.04, run as root):  bash install.sh
# Installs Docker from Ubuntu's own packages, opens only SSH and the web ports, puts the repository in /opt/sinder and
# prepares deploy/.env with generated passwords. It does not start the app: fill in .env first (see the last lines).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 git ufw unattended-upgrades ffmpeg jq curl >/dev/null
systemctl enable --now docker >/dev/null
# firewall: SSH and the web only; the database and the data service are reachable from inside Docker only
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true   # security updates install themselves
# memory headroom for the description models
if [ ! -f /swapfile ]; then fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile && echo "/swapfile none swap sw 0 0" >> /etc/fstab; fi
mkdir -p /opt/sinder && cd /opt/sinder
[ -d repo/.git ] || git clone --depth 1 https://github.com/etaram/commodity-feeder.git repo
cd repo && git pull -q && cd deploy
if [ ! -f .env ]; then
  cp env.example .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
  sed -i "s|^CRON_SECRET=.*|CRON_SECRET=$(openssl rand -hex 32)|" .env
  chmod 600 .env
fi
cat <<MSG

Done. Next, on this server:
  1. nano /opt/sinder/repo/deploy/.env        fill in the values (the names match Vercel); save with Ctrl+O, Enter, Ctrl+X
  2. cd /opt/sinder/repo/deploy && docker compose up -d --build       (first build takes about 5 minutes)
  3. docker compose ps                         every service should say "running" or "healthy"
  4. bash /opt/sinder/repo/deploy/check.sh     checks the app from inside the server before any DNS change
MSG
