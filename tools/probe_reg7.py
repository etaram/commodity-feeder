import re, requests
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
def clean(h):
    b = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<header.*?</header>", " ", h, flags=re.S)
    return re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b)))
PAGES = [("icco", "https://www.icco.org/statistics/", "Daily"), ("iso", "https://www.isosugar.org/prices.php", "Price"),
  ("asoexport", "https://asoexport.org/home/afiliados/", "Afiliados"), ("camcafe", "https://camcafeperu.com.pe/ES/asociados.php", "Asociados"),
  ("anecacao", "https://anecacao.com/socios/", "Socios"), ("uga", "https://uga.ua/en/members-and-partners/", "Members"),
  ("gapki", "https://gapki.id/member-gapki/", "Member"), ("abiove", "https://abiove.org.br/associates/", "Associates"),
  ("cec", "https://www.ciaracec.com.ar/ciara/Asociados", "Asociad"), ("chilenut", "https://chilenut.cl/socios/", "Socios"),
  ("agap", "https://agapperu.org/asociados/", "Asociados"), ("abpa", "https://abpa-br.org/associados/", "Associados")]
for name, url, key in PAGES:
    try:
        r = requests.get(url, headers=UA, timeout=(8, 25)); h = r.text; t = clean(h)
        i = max(t.find("| " + key), 0)
        trs = re.findall(r"<tr.*?</tr>", h, flags=re.S)
        print(f"== {name} {r.status_code} len={len(h)} tr={len(trs)} imgs_alt={len(re.findall(r'<img[^>]+alt=.[^>]{4,}', h))}")
        for tr in trs[:3]:
            print("     ", [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()[:30] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)][:8])
        print("   alts:", re.findall(r'<img[^>]+alt="([^"]{4,60})"', h)[:12])
        print("   text:", t[i:i+1100])
    except Exception as e:
        print(f"== {name} ERR {type(e).__name__}: {str(e)[:100]}")
