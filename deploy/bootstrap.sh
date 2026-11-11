#!/usr/bin/env bash
# First contact with a new server (Ubuntu 24.04, as root). Safe to run twice.
#   ssh root@SERVER "curl -fsSL https://raw.githubusercontent.com/etaram/commodity-feeder/main/deploy/bootstrap.sh | bash"
# 1. installs the operator's public SSH key (a public key is not a secret)   2. runs install.sh (Docker, firewall, swap,
# repository, generated passwords)   3. blocks password guessing (fail2ban)   4. starts a full mirror backup of the
# repository, history included, in the background.  It starts no application and sends nothing anywhere.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBEz6ig3oeBWjiXm+SKjjU5FE0YuitvLtO6sTP0ProTx sinder-server'
mkdir -p /root/.ssh && chmod 700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
grep -qF "$KEY" /root/.ssh/authorized_keys || echo "$KEY" >> /root/.ssh/authorized_keys
echo "[1/4] operator key installed"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git curl fail2ban >/dev/null
systemctl enable --now fail2ban >/dev/null 2>&1 || true
echo "[2/4] password-guessing protection on"
mkdir -p /opt/sinder && cd /opt/sinder
[ -d repo/.git ] || git clone -q --depth 1 https://github.com/etaram/commodity-feeder.git repo
(cd repo && git pull -q)
bash repo/deploy/install.sh >/opt/sinder/install.log 2>&1 && echo "[3/4] base system installed (log: /opt/sinder/install.log)" || { echo "[3/4] install.sh FAILED - see /opt/sinder/install.log"; tail -5 /opt/sinder/install.log; }
mkdir -p /opt/sinder/backup
if [ ! -d /opt/sinder/backup/commodity-feeder.git ]; then
  nohup git clone -q --mirror https://github.com/etaram/commodity-feeder.git /opt/sinder/backup/commodity-feeder.git >/opt/sinder/backup/mirror.log 2>&1 &
  echo "[4/4] full mirror backup started in the background"
else echo "[4/4] mirror backup already present"; fi
echo
echo "SERVER READY: $(hostname)  $(nproc) cores  $(free -g | awk '/Mem:/{print $2}') GB memory  $(df -h / | awk 'NR==2{print $4}') free disk"
