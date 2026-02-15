#!/usr/bin/env python3
"""
Simple test runner for ml/predict.py
Runs prediction for a hardcoded ticker and prints readable output.
"""
import subprocess
import json
import os
import sys

TICKER = 'AAPL'

def run():
    script = os.path.join(os.path.dirname(__file__), 'predict.py')
    try:
        proc = subprocess.run(['python3', script, TICKER], capture_output=True, text=True, timeout=20)
    except Exception as e:
        print('Failed to run predict.py:', e)
        sys.exit(1)

    out = proc.stdout.strip()
    err = proc.stderr.strip()
    if proc.returncode != 0:
        print('Prediction script failed (exit', proc.returncode, ')')
        if out:
            try:
                j = json.loads(out)
                print('Error:', j)
            except Exception:
                print('Stdout:', out)
        if err:
            print('Stderr:', err)
        sys.exit(1)

    try:
        j = json.loads(out)
        print('Prediction result:')
        print(json.dumps(j, indent=2))
    except Exception as e:
        print('Failed to parse output as JSON:', e)
        print('Raw output:', out)

if __name__ == '__main__':
    run()
