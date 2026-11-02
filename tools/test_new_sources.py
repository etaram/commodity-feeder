import logging, sys, json, collections
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO)
import importlib
for name in ["ghana", "zambia", "malawi", "mozambique", "dubai", "philippines"]:
    try:
        rows, st = importlib.import_module("leads." + name).fetch()
        print("##", name, len(rows), st, collections.Counter(r["access"] for r in rows).most_common(3), flush=True)
        for r in rows[:3]: print("   ", r["deadline"], "|", r["buyer"][:40], "|", r["title"][:90], flush=True)
    except Exception as e:
        print("##", name, "ERROR", repr(e)[:300], flush=True)
