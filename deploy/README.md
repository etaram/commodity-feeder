# Sinder on one server

Everything the system needs on a single machine: the Deal Desk app, a private data service, the scheduler,
PostgreSQL and HTTPS. The data workflows run here too, on GitHub Actions runners installed on the server.

## Order of the move (each step can be undone)

1. Server: Ubuntu 24.04, 8 GB RAM. As root: `curl -fsSLO https://raw.githubusercontent.com/etaram/commodity-feeder/main/deploy/install.sh && bash install.sh`
2. Fill `/opt/sinder/repo/deploy/.env` (names as on Vercel), then `docker compose up -d --build` and `bash check.sh`.
3. Runners: `bash runners.sh 3`, then set the repository variable `RUNNER_LABEL=sinder`. Undo: delete the variable.
4. Domain: point the A record of desk.sinder.pro at the server. Caddy obtains the certificate by itself.
   Undo: point the record back at Vercel (the Vercel project stays as it is).
5. Later, once stable: private repository (with a read-only deploy key in REPO_URL), deal state in PostgreSQL.

## Day to day

- Update the app after a code change: `cd /opt/sinder/repo && git pull && cd deploy && docker compose up -d --build app`
- Logs: `docker compose logs -f app` (or cron, sync, proxy, db)
- Database backup: `docker compose exec -T db pg_dump -U sinder sinder | gzip > /opt/sinder/backup-$(date +%F).sql.gz`
- Add an open-source tool (n8n, a browser worker, a queue): add a service to docker-compose.yml and `docker compose up -d`.

Secrets exist only in `deploy/.env` on the server (mode 600). They are never committed and never sent in a chat.
