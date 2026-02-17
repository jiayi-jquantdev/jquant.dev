#!/bin/bash
set -euo pipefail
mkdir -p ml/logs

echo "START FULL RERUN: $(date)" | tee ml/logs/full_rerun_start.log

echo "STEP1: force-fetch all endpoints" | tee ml/logs/fetch_force_final.log
python3 ml/fetch_all_endpoints_force.py --apikey 2U9TRMHTN6LGTEOX --rate 0.05 --tickers-file /tmp/tickers_to_refetch.txt 2>&1 | tee -a ml/logs/fetch_force_final.log

echo "STEP2: expand features from cache" | tee ml/logs/expand_features_rerun.log
ALPHAVANTAGE_FETCH=0 python3 ml/expand_features.py 2>&1 | tee -a ml/logs/expand_features_rerun.log

echo "STEP3: compute coverage summary" | tee ml/logs/coverage_summary.log
python3 - <<'PY' > ml/logs/coverage_summary.log
import pandas as pd
from glob import glob
import os
fn='ml/data/historical_snapshots_1000_v3_expanded.csv'
df=pd.read_csv(fn)
base=set(['ticker','snapshot_date','price_at_snapshot','price_6m','forward_6m_return','sector'])
feat=[c for c in df.columns if c not in base]
row_counts=df[feat].notna().sum(axis=1)
uniq=sorted(df['ticker'].astype(str).unique())
print('rows',len(df))
print('unique_tickers',len(uniq))
print('feature_columns_count',len(feat))
print('per_row_mean',float(row_counts.mean()))
print('per_row_median',float(row_counts.median()))
print('per_row_min',int(row_counts.min()))
print('per_row_max',int(row_counts.max()))
print('fraction_rows_ge_100',float((row_counts>=100).mean()))
# per-endpoint cache presence
kinds=['income','balance','cashflow','earnings','overview']
ticks=[]
for p in glob('ml/cache/overview_*.json'):
    ticks.append(os.path.basename(p).replace('overview_','').replace('.json',''))
print('cached_tickers_count',len(ticks))
for k in kinds:
    cnt=0
    for t in ticks:
        if os.path.exists(f'ml/cache/{k}_{t}.json'):
            cnt+=1
    print('cache_count_'+k, cnt)
PY

echo "STEP4: train impute_and_retrain_stack" | tee ml/logs/impute_retrain_final.log
python3 ml/impute_and_retrain_stack.py 2>&1 | tee -a ml/logs/impute_retrain_final.log

echo "FULL RERUN COMPLETE: $(date)" | tee -a ml/logs/full_rerun_start.log

exit 0
