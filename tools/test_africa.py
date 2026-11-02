import logging, sys, json
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO)
from leads import rwanda, uganda
for mod in (rwanda, uganda):
    try:
        rows, st = mod.fetch()
        print(mod.__name__, len(rows), st)
        for r in rows[:5]: print(json.dumps(r, ensure_ascii=False)[:400])
        import collections; print(collections.Counter(r["access"] for r in rows), collections.Counter(r["nature"] for r in rows))
    except Exception as e:
        import traceback; traceback.print_exc()
