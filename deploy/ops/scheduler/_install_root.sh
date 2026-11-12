#!/usr/bin/env bash
# Runs as root on the server (called by scheduler-install.sh). Copies the scheduler and its two tables to
# /opt/sinder/scheduler and writes the systemd units. Prints no secrets.
set -euo pipefail
W="$1"; B=/opt/sinder/scheduler
PY=$(command -v python3) || { echo "python3 is missing on the server"; exit 1; }
install -d -m 755 "$B"
install -m 644 "$W/deploy/ops/scheduler/sched.py" "$W/deploy/ops/schedule.tab" "$W/deploy/ops/freshness.tab" "$B/"
install -d -m 700 /var/lib/sinder-sched
touch /var/log/sinder-sched.log && chmod 640 /var/log/sinder-sched.log
unit() { printf '%s\n' "$2" > "/etc/systemd/system/$1"; }
unit sinder-sched-dispatch.service "[Unit]
Description=Sinder: start the timed GitHub workflows (deploy/ops/schedule.tab)
After=network-online.target
[Service]
Type=oneshot
ExecStart=$PY $B/sched.py dispatch
TimeoutStartSec=240"
unit sinder-sched-dispatch.timer "[Unit]
Description=Sinder: workflow dispatcher every 5 minutes
[Timer]
OnCalendar=*:0/5:20
AccuracySec=5s
[Install]
WantedBy=timers.target"
unit sinder-sched-fresh.service "[Unit]
Description=Sinder: freshness check of the key data outputs (deploy/ops/freshness.tab)
After=network-online.target
[Service]
Type=oneshot
ExecStart=$PY $B/sched.py fresh
TimeoutStartSec=240"
unit sinder-sched-fresh.timer "[Unit]
Description=Sinder: freshness check every 30 minutes
[Timer]
OnCalendar=*:07,37
AccuracySec=30s
[Install]
WantedBy=timers.target"
systemctl daemon-reload
systemctl enable --now sinder-sched-fresh.timer >/dev/null 2>&1
echo "installed: $B (sched.py, schedule.tab: $(grep -cvE '^\s*(#|$)' "$B/schedule.tab") lines, freshness.tab: $(grep -cvE '^\s*(#|$)' "$B/freshness.tab") items)"
echo "freshness timer: $(systemctl is-enabled sinder-sched-fresh.timer) / $(systemctl is-active sinder-sched-fresh.timer)"
# first freshness check now, without a Telegram message (the timer sends alerts from its next run on)
"$PY" "$B/sched.py" fresh --no-alert | sed 's/^[^ ]* //'
# the dispatcher is switched on only when it cannot cause double runs and has a working token
reason=""
"$PY" "$B/sched.py" token-check || reason="no working dispatch token on the server"
if [ -z "$reason" ]; then
  git -C /opt/sinder/repo fetch -q origin main || echo "could not fetch main into /opt/sinder/repo"
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/.github/workflows"
  for wf in $(SCHED_BASE="$B" "$PY" "$B/sched.py" workflows); do
    git -C /opt/sinder/repo show "origin/main:.github/workflows/$wf" > "$tmp/.github/workflows/$wf" 2>/dev/null || printf 'on:\n  schedule:\n    - cron: unknown\n' > "$tmp/.github/workflows/$wf"
  done
  echo -n "on main: "; SCHED_BASE="$B" "$PY" "$B/sched.py" check-schedules "$tmp" || reason="main still has GitHub schedule triggers for these workflows (apply deploy/ops/scheduler/remove-github-schedules.sh first)"
fi
if [ -z "$reason" ]; then
  systemctl enable --now sinder-sched-dispatch.timer >/dev/null 2>&1
  echo "dispatcher timer: ENABLED ($(systemctl is-active sinder-sched-dispatch.timer))"
else
  systemctl disable --now sinder-sched-dispatch.timer >/dev/null 2>&1 || true
  echo "dispatcher timer: installed, DISABLED: $reason"
fi
