import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def clean(h):
    b = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b)))
for name, url, key in [("fpef", "https://www.fpef.co.za/exportermembersextensivelist", "EXPORTER"), ("cecafe", "https://www.cecafe.com.br/conheca-o-cecafe/associados/", "Associados")]:
    r = requests.get(url, headers=UA, timeout=(8, 30)); h = r.text; t = clean(h); i = t.find(key)
    print(f"== {name} {r.status_code} len={len(h)}"); print("   text:", t[i:i+2500])
from leads.registries import paraguay
rows = paraguay(); print("PARAGUAY", len(rows)); [print("  ", r["supplier"], "|", r["contact_person"], "|", r["phone"], "|", r["email"]) for r in rows[:8]]
