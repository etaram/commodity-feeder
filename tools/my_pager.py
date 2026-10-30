import sys, os, re; sys.path.insert(0, os.getcwd())
from leads.stealth import html
b = html("https://myprocurement.treasury.gov.my/advertisements/tender")
for m in list(re.finditer(r"page=2", b))[:2]:
    print("CTX", re.sub(r"\s+", " ", b[max(0, m.start()-500):m.start()+400]), "\n", flush=True)
print("WIRE", sorted(set(re.findall(r'wire:[a-z.:]+="[^"]{0,60}"', b)))[:15], flush=True)
print("XDATA", re.findall(r'x-on:click="[^"]{0,80}"|@click="[^"]{0,80}"', b)[:8], flush=True)
