import { spawn } from 'child_process';
import path from 'path';
import { error as logError } from './logger';

type Prediction = {
  ticker: string;
  predicted_return_6m: number;
  confidence: string;
};

function spawnPythonPredict(ticker: string, timeoutMs = 10000): Promise<Prediction> {
  return new Promise((resolve, reject) => {
    const script = path.join(process.cwd(), 'ml', 'predict.py');
    const proc = spawn('python3', [script, ticker], { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    const to = setTimeout(() => {
      proc.kill('SIGTERM');
      reject(new Error('Python predict timed out'));
    }, timeoutMs);

    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { stderr += d.toString(); });
    proc.on('close', (code) => {
      clearTimeout(to);
      // Try to parse stdout JSON regardless of exit code. Scripts may print helpful JSON errors.
      try {
        const parsed = JSON.parse(stdout || '{}');
        if (code !== 0) {
          // If script returned an error object, include it
          if (parsed && (parsed.error || parsed.message)) return reject(new Error(String(parsed.error || parsed.message)));
          return reject(new Error(`Python predict failed with code ${code}: ${stderr || stdout}`));
        }
        resolve(parsed as Prediction);
      } catch (e) {
        reject(new Error('Failed to parse prediction JSON: ' + e + ' -- ' + stdout + ' ' + stderr));
      }
    });
    proc.on('error', (err) => { clearTimeout(to); reject(err); });
  });
}

export async function predictTicker(ticker: string): Promise<Prediction> {
  // Prefer an external ML service if configured
  const mlUrl = process.env.ML_SERVICE_URL;
  if (mlUrl) {
    try {
      const res = await fetch(`${mlUrl.replace(/\/$/, '')}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker }),
      });
      if (!res.ok) throw new Error(`ML service returned ${res.status}`);
      const json = await res.json();
      return json as Prediction;
    } catch (e) {
      logError('ML service call failed, falling back to local Python:', e);
    }
  }

  // Local Python fallback if explicitly enabled
  if (process.env.ML_SERVICE_LOCAL === 'true') {
    return await spawnPythonPredict(ticker, 10000);
  }

  throw new Error('No ML service configured and local Python not enabled');
}

export type { Prediction };
