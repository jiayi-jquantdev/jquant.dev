#!/usr/bin/env python3
"""Try several public sources for exchange symbol lists and write ml/exchange_symbols.txt"""
import requests
urls = [
    "https://pkgstore.datahub.io/core/nasdaq-listings/nasdaq-listed_csv/data/nasdaq-listed_csv.csv",
    "https://raw.githubusercontent.com/datasets/nasdaq-listings/master/data/nasdaq-listed.csv",
    "https://pkgstore.datahub.io/core/nyse-other-listings/other-listed_csv/data/other-listed_csv.csv",
]
out = 'ml/exchange_symbols.txt'
syms = set()
for url in urls:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        for line in r.text.splitlines():
            if not line or line.lower().startswith('symbol'):
                continue
            parts = line.split(',')
            if parts:
                s = parts[0].strip().strip('"')
                if s:
                    syms.add(s)
    except Exception:
        continue
with open(out, 'w') as f:
    for s in sorted(syms):
        f.write(s + '\n')
print('Wrote', len(syms), 'symbols to', out)
