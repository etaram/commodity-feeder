# Reaching portals that refuse US addresses

## Done without any new account: the regional relay (2026-11-04)
A one-function Vercel project on the owner's existing account, `sinder-relay-eu`, deployed in Frankfurt (fra1):
`GET /api/fetch?url=...` with a secret header returns the page fetched from a European address. Every collector's
`session().get()` falls back to it automatically on HTTP 403, 451 or no connection, and logs "relay used". Verified
from GitHub Actions: direct requests leave from San Francisco, relayed ones from Frankfurt am Main.
Secret and URL live in the Supplier Universe sheet, tab Config (RELAY_URL, RELAY_SECRET), next to WEB_INDEX_KEY;
nothing in Git. Source: relay/ in the repository. More regions: the same files deployed as another project with
serverlessFunctionRegion bom1 (Mumbai), cpt1 (Cape Town), sin1 (Singapore), gru1 (Sao Paulo); Vercel has no Gulf region.
Limits: GET only, 25 s, 4 MB, no cookies kept, so a portal that needs a login session still needs a real runner.

## If a Gulf address or a login session is ever needed: Oracle Cloud always-free VM

Why: GitHub Actions runs from US addresses. Some portals refuse them (Zambia: captcha; several Gulf and Latin
portals: geoblock). A small VM in Frankfurt, Jeddah or Mumbai runs the same collectors from a local address and
pushes the results to the repo. Cost: zero on Oracle's always-free tier (one small ARM VM is enough).

## What the owner does (about 30 minutes, once)
1. Open an Oracle Cloud account (cloud.oracle.com, "Start for free"). Choose the home region where the blocked
   portals are: Frankfurt (eu-frankfurt-1) for Europe, Jeddah (me-jeddah-1) for the Gulf, Mumbai (ap-mumbai-1) for
   South Asia. The home region cannot be changed later; a second account can have another region.
2. Create a VM: Compute > Instances > Create. Shape VM.Standard.A1.Flex (always free), 1 OCPU, 6 GB, image
   Ubuntu 24.04. Download the SSH key it offers.
3. In the repository, create a fine-grained GitHub token with "Contents: read and write" on commodity-feeder only.
   Never paste the token into chat or into a file in the repository; it goes into the VM's secret store only.
4. Send me the VM's public IP and say which portals it should run. I do not need the SSH key: the setup script below
   is run by you once, and the VM pulls everything else from the repository.

## What runs on the VM (no code changes to the collectors)
```
sudo apt-get update && sudo apt-get install -y python3-pip git
git clone https://github.com/etaram/commodity-feeder.git && cd commodity-feeder
pip3 install --break-system-packages -r requirements.txt
# secrets: in ~/.config/feeder.env (chmod 600): GITHUB_TOKEN=..., GOOGLE_SERVICE_ACCOUNT_JSON=... (optional)
# cron, every 6 hours: pull, run the region's collectors, commit their partial files, push
(crontab -l; echo '0 */6 * * * cd ~/commodity-feeder && . ~/.config/feeder.env && git pull -q --rebase && python3 -m leads.run --source zambia,etimad,qatar 2>&1 | tail -n 200 > ~/run.log && git add data/leads/partial && git -c user.name=oracle-runner -c user.email=runner@sinder.pro commit -qm "runner: $(date -u +%FT%H:%MZ)" && git push -q') | crontab -
```
The leads workflow in GitHub Actions then merges the partial files like any other source; the registry marks the
source "active" from the runner's file age. Rollback: stop the cron; the Actions pipeline continues without it.

## What this does not solve
Portals that need a local company registration or a one-time-password login (Etimad needs a Saudi account) still
need a local partner's credentials, which the system never stores in Git.
