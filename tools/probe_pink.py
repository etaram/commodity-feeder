import io, re, requests, pandas as pd
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderPriceProbe/1.0)"}
page = requests.get("https://www.worldbank.org/en/research/commodity-markets", headers=UA, timeout=40).text
u = re.search(r'href="(https://thedocs\.worldbank\.org/[^"]*CMO-Historical-Data-Monthly\.xlsx)"', page).group(1)
print("url", u)
x = pd.ExcelFile(io.BytesIO(requests.get(u, headers=UA, timeout=90).content))
print("sheets", x.sheet_names)
df = x.parse("Monthly Prices", header=None)
pd.set_option("display.width", 250, "display.max_columns", 12, "display.max_colwidth", 38)
print(df.shape); print(df.iloc[:8, :9].to_string()); print(df.iloc[-4:, :9].to_string())
print("COLS", [str(c)[:30] for c in df.iloc[4].tolist()][:70])
print("UNITS", [str(c)[:14] for c in df.iloc[5].tolist()][:70])
