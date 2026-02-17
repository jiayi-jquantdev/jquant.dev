import fs from 'fs';
import path from 'path';
import { error as logError } from '../../../lib/logger';
import TrainActions from './TrainActions';

type Metrics = { mae?: number; r2?: number; feature_importances?: number[] };

export default function Page() {
  const metricsPath = path.join(process.cwd(), 'ml', 'models', 'metrics.json');
  let metrics: Metrics | null = null;
  try {
    if (fs.existsSync(metricsPath)) {
      const raw = fs.readFileSync(metricsPath, 'utf8');
      metrics = JSON.parse(raw) as Metrics;
    }
  } catch (e) {
    logError('Failed to read metrics.json', e);
    metrics = null;
  }

  return (
    <div style={{ padding: 20 }}>
      <h2>Model Training</h2>
      <div>
        <strong>Metrics</strong>
        <pre>{metrics ? JSON.stringify(metrics, null, 2) : 'No metrics found'}</pre>
      </div>
      <TrainActions />
    </div>
  );
}
