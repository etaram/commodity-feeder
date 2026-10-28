"""Helpers to read OCDS packages returned by different publishers (release package, record package, bare release)."""


def releases_of(j):
    if not isinstance(j, dict):
        return []
    if "releases" in j and isinstance(j["releases"], list):
        return [r for r in j["releases"] if isinstance(r, dict) and ("tender" in r or "ocid" in r)]
    if "records" in j:
        out = []
        for rec in j["records"]:
            cr = rec.get("compiledRelease")
            if cr:
                out.append(cr)
            elif rec.get("releases") and isinstance(rec["releases"][-1], dict) and "tender" in rec["releases"][-1]:
                out.append(rec["releases"][-1])
        return out
    if "payload" in j:
        return releases_of(j["payload"] if isinstance(j["payload"], dict) else {"releases": j["payload"]})
    if "tender" in j:
        return [j]
    return []
