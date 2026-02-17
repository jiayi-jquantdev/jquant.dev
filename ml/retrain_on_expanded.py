#!/usr/bin/env python3
"""Call the improved training pipeline using the expanded CSV."""
from ml import train_full_improved

if __name__ == '__main__':
    train_full_improved.main('ml/data/historical_snapshots_1000_v3_expanded.csv')
