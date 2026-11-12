#!/usr/bin/env python3
"""Server-side scheduler for the GitHub workflows of this repository, plus a freshness check of the key outputs.

GitHub skips or delays scheduled workflows on this repository, so the company server starts them itself through the
workflow_dispatch API, at the times listed in deploy/ops/schedule.tab. Standard library only.

Subcommands
  dispatch [--dry-run]       every 5 minutes (systemd timer): start the workflows whose cron time has come
  fresh [--no-alert]         every 30 minutes (systemd timer): check the age of the outputs in freshness.tab
  token-check                exit 0 if the dispatch token on the server can read this repository's workflows
  state                      print the server-side state as JSON (no secrets), read by "report"
  report                     runner side: read "state" JSON on stdin, add the last successful run from the API, print
  workflows                  list the workflow files named in schedule.tab
  check-schedules DIR        exit 1 if a workflow in schedule.tab still has a GitHub "schedule:" trigger under DIR
  remove-schedules DIR       remove the GitHub "schedule:" triggers of the workflows in schedule.tab under DIR

Nothing here prints a token. The logs of the server-ops workflow are public: names, times and counts only.
"""
import datetime as dt
import fcntl
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO = os.environ.get("SCHED_REPO", "etaram/commodity-feeder")
REF = os.environ.get("SCHED_REF", "main")
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("SCHED_BASE", "/opt/sinder/scheduler")
STATE_DIR = os.environ.get("SCHED_STATE", "/var/lib/sinder-sched")
LOG = os.environ.get("SCHED_LOG", "/var/log/sinder-sched.log")
TOKEN_FILE = os.environ.get("SCHED_TOKEN_FILE", "/opt/sinder/secrets/gh_dispatch.token")
ENV_FILE = os.environ.get("SCHED_ENV_FILE", "/opt/sinder/repo/deploy/.env")
CATCH_UP_MIN = 30           # after a server outage, missed times older than this are not started any more
ALERT_REPEAT_H = 12         # while something stays stale, repeat the Telegram alert this often
UTC = dt.timezone.utc


def now_min():
    return dt.datetime.now(UTC).replace(second=0, microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ") if t else None


def parse_iso(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d\+", s):
        s = s.replace("+", ":00+", 1)
    return dt.datetime.fromisoformat(s).astimezone(UTC)


def log(msg):
    line = f"{iso(dt.datetime.now(UTC))} {msg}"
    print(line)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def tab_path(name):
    for d in (BASE, os.path.dirname(HERE)):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"{name} not found")


def rows(name):
    out = []
    for line in open(tab_path(name), encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.split())
    return out


# ---------- cron ----------

def _field(spec, lo, hi):
    vals = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = int(part)
            b = hi if step > 1 else a
        vals.update(range(a, b + 1, step))
    return vals


def cron_match(expr, t):
    mi, ho, dom, mon, dow = expr
    days_dom = _field(dom, 1, 31)
    days_dow = {d % 7 for d in _field(dow, 0, 7)}
    wd = (t.weekday() + 1) % 7           # cron: 0 = Sunday
    if dom != "*" and dow != "*":
        day_ok = t.day in days_dom or wd in days_dow
    else:
        day_ok = t.day in days_dom and wd in days_dow
    return t.minute in _field(mi, 0, 59) and t.hour in _field(ho, 0, 23) and t.month in _field(mon, 1, 12) and day_ok


def schedule():
    out = []
    for r in rows("schedule.tab"):
        if r[0] == "@continuous":               # back-to-back: started again as soon as the previous run has finished
            cron, r = None, [None] * 4 + r
        else:
            cron = r[:5]
        wf, max_h = r[5], float(r[6])
        inputs = {}
        if len(r) > 7 and r[7] != "-":
            inputs = dict(kv.split("=", 1) for kv in r[7].split(","))
        out.append({"cron": cron, "workflow": wf, "max_h": max_h, "inputs": inputs})
    return out


# ---------- GitHub API ----------

def token():
    t = os.environ.get("GH_TOKEN", "")
    if not t and os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE).read().strip()
    return t


def api(path, method="GET", body=None, tok=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "sinder-scheduler")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:                       # network trouble: report the kind only, never a URL or header
        return 0, type(e).__name__


def waiting_runs(wf, tok, states=("queued", "pending", "waiting")):
    """Runs of this workflow that have not started yet (queued, or held by its concurrency group)."""
    n = 0
    for st in states:
        code, js = api(f"actions/workflows/{wf}/runs?status={st}&per_page=5", tok=tok)
        if code != 200:
            return None
        n += js.get("total_count", 0)
    return n


def runs_created_since(wf, t, tok):
    """Runs of this workflow created at or after t, by any trigger (GitHub's schedule, a dispatch, a re-run)."""
    q = urllib.request.quote(">=" + t.strftime("%Y-%m-%dT%H:%M:%SZ"))
    code, js = api(f"actions/workflows/{wf}/runs?created={q}&per_page=1", tok=tok)
    return js.get("total_count", 0) if code == 200 and js else None


# ---------- state ----------

def load(name, default):
    try:
        return json.load(open(os.path.join(STATE_DIR, name)))
    except (OSError, ValueError):
        return default


def save(name, obj):
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, name)
    with open(p + ".tmp", "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(p + ".tmp", p)


# ---------- dispatch ----------

def cmd_dispatch(dry=False):
    os.makedirs(STATE_DIR, exist_ok=True)
    lock = open(os.path.join(STATE_DIR, "dispatch.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    tok = token()
    if not tok and not dry:
        log("dispatch: no dispatch token on the server; nothing started")
        return 0
    st = load("dispatch.json", {})
    now = now_min()
    # a fresh start (new heartbeat job, or after an outage) looks back CATCH_UP_MIN minutes; the run check below
    # stops a time slot that already has a run from being started twice
    last = parse_iso(st.get("last_tick")) or now - dt.timedelta(minutes=CATCH_UP_MIN)
    start = max(last + dt.timedelta(minutes=1), now - dt.timedelta(minutes=CATCH_UP_MIN))
    due = {}
    t = start
    entries = schedule()
    while t <= now:
        for i, e in enumerate(entries):
            if e["cron"] and cron_match(e["cron"], t):
                due[i] = t                          # one start per line, even if several times were missed
        t += dt.timedelta(minutes=1)
    wfs = st.setdefault("workflows", {})
    for i, e in enumerate(entries):              # back-to-back lines are due on every tick; the run check below decides
        if e["cron"] is None:
            due[i] = now
    started = 0
    for i, when in sorted(due.items(), key=lambda kv: kv[1]):
        e = entries[i]
        wf, cron = e["workflow"], " ".join(e["cron"]) if e["cron"] else "@continuous"
        rec = wfs.setdefault(wf, {})
        tag = "dispatch (dry run)" if dry else "dispatch"
        if e["cron"] is None:
            if runs_created_since(wf, now - dt.timedelta(minutes=4), tok) != 0:
                continue                         # started a moment ago (the API may not list it as running yet)
            if waiting_runs(wf, tok, ("queued", "pending", "waiting", "in_progress")) != 0:
                continue                         # still running (or the API did not answer): try again next tick
        else:
            n = runs_created_since(wf, when - dt.timedelta(minutes=1), tok)
            if n != 0:                           # this time slot already has a run (GitHub's schedule or an earlier tick)
                log(f"{tag}: {wf} for {iso(when)} [{cron}] already has a run created since then; skipped" if n else
                    f"{tag}: {wf} for {iso(when)} [{cron}] could not be checked (api); skipped this tick")
                continue
            w = waiting_runs(wf, tok)
            if w:
                log(f"{tag}: {wf} already has {w} run(s) waiting to start; skipped [{cron}]")
                rec.update(last_skip=iso(now), last_result="skipped: already waiting")
                continue
        if dry:
            log(f"{tag}: would start {wf} for {iso(when)} [{cron}] inputs {e['inputs'] or '-'}")
            started += 1
            continue
        code, _ = api(f"actions/workflows/{wf}/dispatches", "POST", {"ref": REF, "inputs": e["inputs"]}, tok)
        ok = code == 204
        log(f"dispatch: {wf} for {iso(when)} [{cron}] -> {'started' if ok else f'FAILED http {code}'}")
        rec.update(last_attempt=iso(now), last_result="started" if ok else f"failed http {code}")
        if ok:
            started += 1
            rec["last_dispatch"] = iso(now)
            rec["dispatches"] = rec.get("dispatches", 0) + 1
    log(f"tick {iso(now)}: window from {iso(start)}, {len(due)} line(s) due, {started} {'would start' if dry else 'started'}")
    if not dry:
        st["last_tick"] = iso(now)
        save("dispatch.json", st)
    return 0


# ---------- freshness ----------

def read_env(path):
    env = {}
    try:
        for line in open(path, encoding="utf-8"):
            m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if m:
                v = m.group(2).strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                else:
                    v = re.split(r"\s+#", v, 1)[0].strip()
                env[m.group(1)] = v
    except OSError:
        pass
    return env


CHAT_KEYS = ("SCHED_ALERT_CHAT_ID", "TELEGRAM_ALERT_CHAT_ID", "ALERT_CHAT_ID", "OWNER_CHAT_ID", "TELEGRAM_OWNER_CHAT_ID", "TELEGRAM_CHAT_ID")


def telegram_conf():
    env = read_env(ENV_FILE)
    tok = env.get("TELEGRAM_BOT_TOKEN", "")
    if not tok:                                  # same rule as dealdesk/lib/tgenv.ts: a variable named after the bot
        for k, v in env.items():
            if re.search(r"_?bot$", k, re.I) and re.match(r"^\d{6,}:[A-Za-z0-9_-]{30,}$", v or ""):
                tok = v
                break
    chat = next((env[k] for k in CHAT_KEYS if env.get(k)), "")
    return tok, chat


def telegram(text):
    tok, chat = telegram_conf()
    if not (tok and chat):
        return "not configured"
    data = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return "sent" if r.status == 200 else f"http {r.status}"
    except urllib.error.HTTPError as e:
        return f"http {e.code}"
    except Exception as e:
        return type(e).__name__


def repo_volume_dir():
    """The folder the data gateway serves (the synced copy of the repository), if it exists on this server."""
    for name in ("sinder_repo", "deploy_repo"):
        p = f"/var/lib/docker/volumes/{name}/_data"
        if os.path.isdir(os.path.join(p, ".git")):
            return p
    return None


def cmd_fresh(no_alert=False):
    now = dt.datetime.now(UTC)
    tok = token()
    items = []
    for name, kind, target, max_h in rows("freshness.tab"):
        when, err = None, None
        if kind == "git":
            code, js = api(f"commits?sha={REF}&path={target}&per_page=1", tok=tok or None)
            if code == 200 and js:
                when = parse_iso(js[0]["commit"]["committer"]["date"])
            else:
                err = f"api {code}"
        elif kind == "file":
            files = glob.glob(target)
            if files:
                when = dt.datetime.fromtimestamp(max(os.path.getmtime(f) for f in files), UTC)
            else:
                err = "no file"
        age = (now - when).total_seconds() / 3600 if when else None
        status = "UNKNOWN" if age is None else ("STALE" if age > float(max_h) else "OK")
        items.append({"name": name, "kind": kind, "last": iso(when), "age_h": None if age is None else round(age, 1),
                      "max_h": float(max_h), "status": status, "error": err})
    prev = load("freshness.json", {})
    alert = prev.get("alert", {})
    bad = [i for i in items if i["status"] != "OK"]
    out = {"checked": iso(now), "items": items, "stale": len(bad), "alert": alert}
    for i in items:
        age_txt = f"age {i['age_h']}h" if i["age_h"] is not None else "age -"
        log(f"fresh: {i['name']:<18} {i['status']:<7} {age_txt} (max {i['max_h']:g}h){'  ' + i['error'] if i['error'] else ''}")
    # alert when the set of stale items changes for the worse, or again every ALERT_REPEAT_H hours while still stale
    names = sorted(i["name"] for i in bad)
    last_sent = parse_iso(alert.get("sent"))
    new = [n for n in names if n not in alert.get("names", [])]
    if names and (new or not last_sent or now - last_sent > dt.timedelta(hours=ALERT_REPEAT_H)):
        text = "Sinder data freshness: " + "; ".join(
            f"{i['name']} {i['status']} " + (f"{i['age_h']}h old (max {i['max_h']:g}h)" if i["age_h"] is not None else f"({i['error']})")
            for i in bad)
        res = "not sent (--no-alert)" if no_alert else telegram(text)
        log(f"fresh: alert for {len(names)} item(s): {res}")
        if res == "sent":
            alert = {"sent": iso(now), "names": names}
    elif not names and alert.get("names"):
        if not no_alert:
            log(f"fresh: all fresh again; recovery note: {telegram('Sinder data freshness: all key outputs are fresh again.')}")
        alert = {}
    out["alert"] = alert
    save("freshness.json", out)
    vol = repo_volume_dir()
    if vol:                                      # untracked folder: the sync job's "git reset --hard" leaves it alone
        os.makedirs(os.path.join(vol, "_status"), exist_ok=True)
        pub = {"checked": out["checked"], "stale": out["stale"],
               "items": [{k: i[k] for k in ("name", "last", "age_h", "max_h", "status")} for i in items]}
        with open(os.path.join(vol, "_status", "freshness.json.tmp"), "w") as f:
            json.dump(pub, f, indent=1)
        os.replace(os.path.join(vol, "_status", "freshness.json.tmp"), os.path.join(vol, "_status", "freshness.json"))
    return 0


# ---------- status ----------

def systemd(unit, what):
    r = os.popen(f"systemctl {what} {unit} 2>/dev/null").read().strip()
    return r or "missing"


def cmd_state():
    tg_tok, tg_chat = telegram_conf()
    js = {"dispatch": load("dispatch.json", {}), "freshness": load("freshness.json", {}),
          "token_file": os.path.exists(TOKEN_FILE),
          "telegram": {"bot_token": bool(tg_tok), "chat_id": bool(tg_chat)},
          "status_file_served": bool(repo_volume_dir()),
          "timers": {u: {"enabled": systemd(u, "is-enabled"), "active": systemd(u, "is-active")}
                     for u in ("sinder-sched-dispatch.timer", "sinder-sched-fresh.timer")}}
    print(json.dumps(js))
    return 0


def age_h(t, now):
    return None if not t else round((now - t).total_seconds() / 3600, 1)


def cmd_report():
    raw = sys.stdin.read()
    m = re.search(r"\{.*\}", raw, re.S)
    st = json.loads(m.group(0)) if m else {}
    now = dt.datetime.now(UTC)
    tok = os.environ.get("GH_TOKEN", "") or None
    print("== server scheduler")
    for u, s in st.get("timers", {}).items():
        print(f"{u:<30} enabled={s['enabled']} active={s['active']}")
    print(f"dispatch token on server: {'yes' if st.get('token_file') else 'NO'}")
    tg = st.get("telegram", {})
    print(f"telegram alert: bot token {'yes' if tg.get('bot_token') else 'missing'}, owner chat id {'yes' if tg.get('chat_id') else 'missing'}")
    print(f"status file served by the data gateway: {'yes (_status/freshness.json)' if st.get('status_file_served') else 'no'}")
    print(f"last dispatcher tick: {st.get('dispatch', {}).get('last_tick') or 'never'}")
    print("== workflows (last workflow_dispatch start, last success)")
    print(f"{'workflow':<20} {'last dispatch':<18} {'last success':<18} {'age_h':>6} {'max_h':>6}  status")
    disp = st.get("dispatch", {}).get("workflows", {})
    seen, counts = {}, {"OK": 0, "STALE": 0, "UNKNOWN": 0}
    for e in schedule():
        seen[e["workflow"]] = max(seen.get(e["workflow"], 0), e["max_h"])
    for wf, max_h in seen.items():
        code, js = api(f"actions/workflows/{wf}/runs?status=success&per_page=1", tok=tok)
        last = parse_iso(js["workflow_runs"][0]["updated_at"]) if code == 200 and js and js.get("workflow_runs") else None
        code2, js2 = api(f"actions/workflows/{wf}/runs?event=workflow_dispatch&per_page=1", tok=tok)
        ld = parse_iso(js2["workflow_runs"][0]["created_at"]) if code2 == 200 and js2 and js2.get("workflow_runs") else None
        a = age_h(last, now)
        s = "UNKNOWN" if a is None else ("STALE" if a > max_h else "OK")
        counts[s] += 1
        print(f"{wf:<20} {iso(ld) or '-':<18} {iso(last) or '-':<18} {a if a is not None else '-':>6} {max_h:>6g}  {s}")
    print("== company checks and refinement (the build of the supplier universe)")
    since = now - dt.timedelta(hours=24)
    code, js = api(f"actions/workflows/company-check.yml/runs?created=%3E%3D{since.strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page=100", tok=tok)
    if code == 200 and js:
        runs = js.get("workflow_runs", [])
        busy = sum(((parse_iso(r["updated_at"]) - parse_iso(r["run_started_at"])).total_seconds() / 60)
                   for r in runs if r.get("status") == "completed" and r.get("run_started_at"))
        ok = sum(1 for r in runs if r.get("conclusion") == "success")
        print(f"company-check runs in the last 24h: {len(runs)} ({ok} successful), busy {busy:.0f} of 1440 minutes ({busy / 14.4:.0f}%)")
    else:
        print(f"company-check runs in the last 24h: api {code}")
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/data/leads/refine_progress.json?ref={REF}")
    req.add_header("Accept", "application/vnd.github.raw+json")
    req.add_header("User-Agent", "sinder-scheduler")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        rp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        done, queue = rp.get("websites_checked") or 0, rp.get("website_check_queue") or 0
        print(f"refine progress (at {rp.get('at')}): universe {rp.get('universe')}, processed {rp.get('processed')}, "
              f"websites_checked {done}, website_check_queue {queue}" + (f" ({100 * done / (done + queue):.1f}% of sites checked)" if done + queue else ""))
    except Exception as e:
        print(f"refine progress: not readable ({type(e).__name__})")
    fr = st.get("freshness", {})
    print(f"== key outputs (checked {fr.get('checked') or 'never'})")
    fc = {"OK": 0, "STALE": 0, "UNKNOWN": 0}
    for i in fr.get("items", []):
        fc[i["status"]] = fc.get(i["status"], 0) + 1
        print(f"{i['name']:<20} {'-':<18} {i['last'] or '-':<18} {i['age_h'] if i['age_h'] is not None else '-':>6} {i['max_h']:>6g}  {i['status']}{'  ' + i['error'] if i.get('error') else ''}")
    print(f"== totals: workflows OK {counts['OK']}, STALE {counts['STALE']}, UNKNOWN {counts['UNKNOWN']}; "
          f"outputs OK {fc.get('OK', 0)}, STALE {fc.get('STALE', 0)}, UNKNOWN {fc.get('UNKNOWN', 0)}")
    return 0


# ---------- GitHub schedule triggers ----------

def _schedule_block(lines):
    """Index range of the "schedule:" block inside the top-level "on:" block, or None."""
    in_on = False
    for i, l in enumerate(lines):
        if re.match(r"^on:\s*$", l):
            in_on = True
            continue
        if in_on and re.match(r"^\S", l) and not l.startswith("#"):
            return None
        m = re.match(r"^(\s+)schedule:\s*$", l)
        if in_on and m:
            ind = len(m.group(1))
            j = i + 1
            while j < len(lines):
                s = lines[j]
                if s.strip() == "" or (len(s) - len(s.lstrip()) > ind):
                    j += 1
                    continue
                break
            while j > i + 1 and lines[j - 1].strip() == "":
                j -= 1
            return i, j
    return None


def workflows_in_tab():
    return sorted({e["workflow"] for e in schedule()})


def cmd_check_schedules(root):
    left = []
    for wf in workflows_in_tab():
        lines = open(os.path.join(root, ".github/workflows", wf), encoding="utf-8").read().split("\n")
        if _schedule_block(lines):
            left.append(wf)
    print(f"workflows in schedule.tab that still have a GitHub schedule: {len(left)}" + (f" ({', '.join(left)})" if left else ""))
    return 1 if left else 0


def cmd_remove_schedules(root):
    n = 0
    for wf in workflows_in_tab():
        p = os.path.join(root, ".github/workflows", wf)
        lines = open(p, encoding="utf-8").read().split("\n")
        b = _schedule_block(lines)
        if not b:
            continue
        i, j = b
        ind = " " * (len(lines[i]) - len(lines[i].lstrip()))
        lines[i:j] = [f"{ind}# timed by the company server (deploy/ops/schedule.tab), not by GitHub: see deploy/ops/SCHEDULE.md"]
        open(p, "w", encoding="utf-8").write("\n".join(lines))
        n += 1
        print(f"removed the GitHub schedule from {wf}")
    print(f"{n} workflow(s) changed")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    c, rest = argv[0], argv[1:]
    if c == "dispatch":
        return cmd_dispatch("--dry-run" in rest)
    if c == "fresh":
        return cmd_fresh("--no-alert" in rest)
    if c == "token-check":
        tok = token()
        if not tok:
            print("dispatch token: none")
            return 1
        code, _ = api("actions/workflows?per_page=1", tok=tok)
        print(f"dispatch token: present, read of this repository's workflows -> http {code}")
        return 0 if code == 200 else 1
    if c == "state":
        return cmd_state()
    if c == "report":
        return cmd_report()
    if c == "workflows":
        print("\n".join(workflows_in_tab()))
        return 0
    if c == "check-schedules":
        return cmd_check_schedules(rest[0])
    if c == "remove-schedules":
        return cmd_remove_schedules(rest[0])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
