#!/usr/bin/env bash
# Public DNS records that decide whether mail from the company domain is trusted (SPF, DKIM, DMARC, MX). Read-only.
D="${MAIL_DOMAIN:-sinder.pro}"
q() { docker run --rm alpine:3.20 nslookup -type="$1" "$2" 1.1.1.1 2>&1 | grep -vE "^Server|^Address|^$|^Non-authoritative" | sed 's/^/  /' | head -8; }
echo "== MX $D"; q MX "$D"
echo "== TXT $D (SPF lives here)"; q TXT "$D"
echo "== DMARC _dmarc.$D"; q TXT "_dmarc.$D"
for s in sinder zmail zoho default selector1 google s1 k1 mail; do r=$(docker run --rm alpine:3.20 nslookup -type=TXT "$s._domainkey.$D" 1.1.1.1 2>&1 | grep -iE "v=DKIM1|k=rsa|p=" | head -1 | cut -c1-90); [ -n "$r" ] && echo "== DKIM selector $s: found ${r}..." ; done
echo "== DKIM selectors checked: sinder zmail zoho default selector1 google s1 k1 mail"
