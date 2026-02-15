"use client";
import React, { useState } from 'react';

export default function TrainActions() {
  const [status, setStatus] = useState<string | null>(null);

  async function retrain() {
    setStatus('starting');
    try {
      const res = await fetch('/api/admin/train', { method: 'POST' });
      const j = await res.json();
      if (res.ok) setStatus('started'); else setStatus('error: ' + JSON.stringify(j));
    } catch (e) {
      setStatus('error: ' + String(e));
    }
  }

  return (
    <div style={{ marginTop: 12 }}>
      <button onClick={retrain}>Retrain Model</button>
      <div style={{ marginTop: 8 }}>Status: {status || 'idle'}</div>
    </div>
  );
}
