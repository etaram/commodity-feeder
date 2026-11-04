"""Relay check from Actions: the relay's own egress address and a page that reports the caller's country."""
import sys
sys.path.insert(0, ".")
from leads.common import relay_get, session
for u in ["https://api.ipify.org?format=json", "https://ipapi.co/json/"]:
    d = session().get(u, timeout=30)
    print("direct ", u, d.status_code, d.text[:160].replace("\n", " "))
    r = relay_get(u)
    print("relay  ", u, r.status_code if r else None, (r.text[:160].replace("\n", " ") if r else "relay not configured or failed"))
