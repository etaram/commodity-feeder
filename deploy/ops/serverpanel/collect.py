#!/usr/bin/env python3
"""Server status for the admin panel ("Server and tasks").

Runs on the company server every 2 minutes from sinder-serverpanel.timer, at low priority. Writes two small JSON files
that the private data service serves at /_server/ (see deploy/docker-compose.yml, service "data"):

  status.json   the state now: load, CPU busy %, memory, swap, disk, containers, runners, model containers,
                website-check counters and the newest lines of the job journal
  history.json  the last 24 hours at 2-minute resolution (at most 720 points), small numbers only, for sparklines

What is never written: secrets, environment values, command lines, IP addresses, host names, user names, paths of
the runners' work folders. Container names and the runner number (r1, r2, r3) are the only names.
Standard library only. Usage: collect.py [--out DIR] [--state DIR] [--print]
"""
import json
import os
import re
import subprocess
import sys
import time

OUT = os.environ.get("SERVERPANEL_OUT", "/opt/sinder/serverpanel/public")
STATE = os.environ.get("SERVERPANEL_STATE", "/var/lib/sinder-serverpanel")
JOURNAL = os.environ.get("SERVERPANEL_JOURNAL", "/var/log/sinder-jobs.log")
HISTORY_POINTS = 720            # 24 hours at one point every 2 minutes
HISTORY_COLS = ["t", "cpu", "mem", "disk", "load1", "wc", "queue", "busy_runners"]
MODEL_RE = re.compile(r"^(ollama|semantic|bench|enrich)", re.I)
# anything that looks like a key or token in a journal line is cut out before it is published
SECRETISH = re.compile(r"(?i)(bearer\s+\S+|(?:token|key|secret|password|passwd)\S*\s*[=:]\s*\S+|[A-Za-z0-9_\-+/=]{32,}|gh[pousr]_[A-Za-z0-9]{20,})")
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def sh(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return default


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


# ---------- host ----------

def cpu_times():
    """(busy, total) jiffies from the first line of /proc/stat. Idle and iowait count as not busy."""
    parts = read("/proc/stat").split("\n", 1)[0].split()
    if not parts or parts[0] != "cpu":
        return None
    v = [int(x) for x in parts[1:9]]           # user nice system idle iowait irq softirq steal
    total = sum(v)
    idle = v[3] + v[4]
    return total - idle, total


def cpu_busy(state_dir):
    """CPU busy % since the previous run (the 2-minute average); on the first run, over one second."""
    now = cpu_times()
    if not now:
        return None, 0
    prev_path = os.path.join(state_dir, "cpu.json")
    prev = load_json(prev_path, None)
    t = time.time()
    try:
        write_json(prev_path, {"busy": now[0], "total": now[1], "t": t})
    except Exception:
        pass
    if not prev or now[1] <= prev.get("total", 0) or t - prev.get("t", 0) > 900:
        time.sleep(1)
        later = cpu_times()
        d_total = later[1] - now[1]
        return (round(100.0 * (later[0] - now[0]) / d_total, 1) if d_total > 0 else None), 1
    d_total = now[1] - prev["total"]
    return round(100.0 * (now[0] - prev["busy"]) / d_total, 1), round(t - prev["t"])


def meminfo():
    m = {}
    for line in read("/proc/meminfo").splitlines():
        k, _, rest = line.partition(":")
        try:
            m[k] = int(rest.split()[0]) // 1024     # kB -> MB
        except Exception:
            pass
    total, avail = m.get("MemTotal", 0), m.get("MemAvailable", 0)
    return ({"total_mb": total, "used_mb": max(0, total - avail), "available_mb": avail},
            {"total_mb": m.get("SwapTotal", 0), "used_mb": max(0, m.get("SwapTotal", 0) - m.get("SwapFree", 0))})


def disk(path="/"):
    try:
        s = os.statvfs(path)
    except Exception:
        return None
    gb = 1024 ** 3
    total = s.f_blocks * s.f_frsize / gb
    free = s.f_bavail * s.f_frsize / gb
    used = total - s.f_bfree * s.f_frsize / gb
    return {"total_gb": round(total, 1), "used_gb": round(used, 1), "free_gb": round(free, 1),
            "used_pct": round(100.0 * used / (used + free), 1) if used + free > 0 else None}


# ---------- docker ----------

def parse_mem_mb(s):
    """'1.2GiB / 15GiB' -> 1228.8 (the first figure, in MB)."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)", s or "")
    if not m:
        return None
    mult = {"B": 1 / 1048576, "KiB": 1 / 1024, "KB": 1 / 1024, "kB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024, "TiB": 1048576, "TB": 1048576}
    return round(float(m.group(1)) * mult.get(m.group(2), 1), 1)


def containers():
    rows = []
    ps = sh(["docker", "ps", "-a", "--format", "{{json .}}"])
    if not ps:
        return None
    ids = []
    for line in ps.splitlines():
        try:
            c = json.loads(line)
        except Exception:
            continue
        st = c.get("Status", "")
        h = re.search(r"\((healthy|unhealthy|health: starting)\)", st)
        rows.append({"name": c.get("Names", "")[:60], "state": c.get("State", ""),
                     "health": (h.group(1).replace("health: ", "") if h else None), "cpu_pct": None, "mem_mb": None,
                     "want_running": None})
        ids.append(c.get("ID", ""))
    # restart policy: a stopped container that should be running is "down"; one without a policy is just idle
    pol = sh(["docker", "inspect", "--format", "{{.Name}}|{{.HostConfig.RestartPolicy.Name}}"] + [i for i in ids if i]) if ids else ""
    want = {}
    for line in pol.splitlines():
        n, _, p = line.partition("|")
        want[n.lstrip("/")] = p in ("always", "unless-stopped", "on-failure")
    stats = sh(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=40)
    by = {}
    for line in stats.splitlines():
        try:
            s = json.loads(line)
            by[s.get("Name", "")] = s
        except Exception:
            pass
    for r in rows:
        r["want_running"] = want.get(r["name"])
        s = by.get(r["name"])
        if s:
            try:
                r["cpu_pct"] = round(float(str(s.get("CPUPerc", "")).rstrip("%")), 1)
            except Exception:
                pass
            r["mem_mb"] = parse_mem_mb(s.get("MemUsage", ""))
    rows.sort(key=lambda r: (r["state"] != "running", r["name"]))
    return rows[:40]


# ---------- runners ----------

def runners():
    """r1..rN from the runner services; busy when a Runner.Worker process of that runner is alive."""
    units = sh(["systemctl", "list-units", "--all", "--type=service", "--no-legend", "--plain", "actions.runner.*"])
    found = {}
    for line in units.splitlines():
        parts = line.split()
        if not parts:
            continue
        m = re.search(r"-(\d+)\.service$", parts[0])
        if m:
            found["r" + m.group(1)] = parts[2] == "active" if len(parts) > 2 else False
    busy = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        cmd = read(f"/proc/{pid}/cmdline").replace("\0", " ")
        if "Runner.Worker" in cmd:
            m = re.search(r"/home/runner/(r\d+)/", cmd)
            if m:
                busy.add(m.group(1))
    names = sorted(set(found) | busy | ({"r1", "r2", "r3"} if os.path.isdir("/home/runner") else set()), key=lambda x: int(x[1:]))
    return [{"name": n, "active": bool(found.get(n)), "busy": n in busy} for n in names]


# ---------- data counters and journal ----------

def repo_volume_dir():
    """The synced repository copy that the data service serves (read only here)."""
    for name in ("sinder_repo", "deploy_repo"):
        p = f"/var/lib/docker/volumes/{name}/_data"
        if os.path.isdir(os.path.join(p, "data")):
            return p
    return None


def refine_counts():
    vol = repo_volume_dir()
    if not vol:
        return None
    d = load_json(os.path.join(vol, "data/leads/refine_progress.json"), None)
    if not isinstance(d, dict):
        return None
    return {k: d.get(k) for k in ("at", "universe", "processed", "websites_checked", "website_check_queue", "needs_ai")}


ENRICH_STATUS = os.environ.get("SERVERPANEL_ENRICH", "/opt/sinder/enrich/status.json")


def enrich_counts(path=ENRICH_STATUS):
    """The supplier enrichment job's counts (leads/enrich_server.py writes them; numbers and field names only)."""
    d = load_json(path, None)
    if not isinstance(d, dict) or d.get("v") != 1:
        return None
    num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None  # noqa: E731
    fill = d.get("fill") if isinstance(d.get("fill"), dict) else {}
    tiers = d.get("by_tier") if isinstance(d.get("by_tier"), dict) else {}
    return {"at": str(d.get("at", ""))[:20], "state": str(d.get("state", ""))[:12], "queue": num(d.get("queue")), "done": num(d.get("done")),
            "remaining": num(d.get("remaining")), "per_hour": num(d.get("per_hour")), "eta_hours": num(d.get("eta_hours")),
            "by_tier": {str(k)[:20]: {"done": num((v or {}).get("done")), "total": num((v or {}).get("total"))} for k, v in list(tiers.items())[:6] if isinstance(v, dict)},
            "fill": {str(k)[:20]: num(v) for k, v in list(fill.items())[:30]}}


def clean_line(s):
    s = SECRETISH.sub("[hidden]", s)
    s = IPV4.sub("[ip]", s)
    s = EMAIL.sub("[email]", s)
    return s.strip()[:160]


def journal(path=JOURNAL, n=20):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 16384))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return None
    return [clean_line(x) for x in lines if x.strip()][-n:]


# ---------- assemble ----------

def collect(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    busy, window = cpu_busy(state_dir)
    mem, swap = meminfo()
    load = [round(float(x), 2) for x in read("/proc/loadavg", "0 0 0").split()[:3]]
    up = read("/proc/uptime", "0").split()
    cs = containers()
    rs = runners()
    return {
        "v": 1,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"uptime_s": int(float(up[0])) if up else None, "cpus": os.cpu_count(), "load": load,
                 "cpu_busy_pct": busy, "cpu_window_s": window, "mem": mem, "swap": swap, "disk": disk("/")},
        "containers": cs,
        "runners": rs,
        "models": [c["name"] for c in (cs or []) if c["state"] == "running" and MODEL_RE.match(c["name"])],
        "refine": refine_counts(),
        "enrich": enrich_counts(),
        "journal": journal(),
    }


def add_history(path, st):
    h = load_json(path, None)
    pts = h.get("points", []) if isinstance(h, dict) and h.get("cols") == HISTORY_COLS else []
    host, mem, dk, rf = st["host"], st["host"]["mem"], st["host"]["disk"] or {}, st.get("refine") or {}
    now = int(time.time())
    p = [now, host["cpu_busy_pct"], round(100.0 * mem["used_mb"] / mem["total_mb"], 1) if mem["total_mb"] else None,
         dk.get("used_pct"), host["load"][0] if host["load"] else None, rf.get("websites_checked"), rf.get("website_check_queue"),
         sum(1 for r in st.get("runners") or [] if r["busy"])]
    pts = [x for x in pts if isinstance(x, list) and len(x) == len(HISTORY_COLS) and now - x[0] <= 86400 and x[0] < now] + [p]
    return {"v": 1, "step_s": 120, "cols": HISTORY_COLS, "points": pts[-HISTORY_POINTS:]}


def main(argv):
    out, state = OUT, STATE
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--state" in argv:
        state = argv[argv.index("--state") + 1]
    st = collect(state)
    if "--print" in argv:
        print(json.dumps(st, indent=1))
        return 0
    os.makedirs(out, exist_ok=True)
    os.chmod(out, 0o755)
    hist = add_history(os.path.join(out, "history.json"), st)
    write_json(os.path.join(out, "status.json"), st)
    write_json(os.path.join(out, "history.json"), hist)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
