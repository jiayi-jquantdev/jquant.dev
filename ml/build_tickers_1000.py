#!/usr/bin/env python3
"""Build a combined 1000-ticker list from existing tickers and S&P500.
Writes `ml/tickers_1000.txt`.
"""
import os

FILES = ["ml/tickers.txt", "ml/sp500.txt", "ml/exchange_symbols.txt"]
OUT = "ml/tickers_1000.txt"

def main():
    seen = []
    for p in FILES:
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for line in f:
                t = line.strip()
                if not t:
                    continue
                if t not in seen:
                    seen.append(t)
    # if fewer than 1000, leave as-is (collector will attempt available)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        for t in seen[:1000]:
            f.write(t + '\n')
    print('Wrote', min(len(seen),1000), 'tickers to', OUT)

if __name__ == '__main__':
    main()
