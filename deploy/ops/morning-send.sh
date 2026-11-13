#!/usr/bin/env bash
# The morning Telegram message as each linked chat would get it now (lib/morning.ts via /api/cron/digest?preview=morning):
# prints counts and sizes only (the workflow log is public), sends nothing. With SEND=1 (task morning-send) it runs the
# Telegram part of the digest now (?only=telegram): at most once per chat per day, the day key is kept in the profile.
set -euo pipefail
Q="only=telegram&force=1"
docker exec -i -e Q="$Q" sinder-server-app node -e '
fetch("http://127.0.0.1:3000/api/cron/digest?"+process.env.Q,{headers:{authorization:"Bearer "+process.env.CRON_SECRET}})
 .then(async r=>{const j=await r.json(); if(j.preview){for(const p of j.preview) console.log(`chat lang=${p.lang} profile=${p.has_profile} alerts=${p.alerts} chars=${p.chars} sections=${(p.text.match(/\n\n/g)||[]).length+1} counts=${JSON.stringify(p.counts)}`)} else console.log(r.status, JSON.stringify(j).slice(0,200))})
 .catch(e=>{console.log("ERR "+e.message);process.exit(1)})'
