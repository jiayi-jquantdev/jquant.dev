import { readJson, writeJson } from "./fs-utils";

type UsageEntry = {
  key: string;
  minuteWindowStart?: number; // epoch minutes
  minuteCount?: number;
  dayWindowStart?: string; // yyyy-mm-dd
  dayCount?: number;
};

function todayDateString() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

export async function checkAndIncrementKey(key: string, minuteLimit: number, dayLimit: number) {
  const usages = (await readJson<Record<string, UsageEntry>>("usage.json")) || {};
  const now = new Date();
  const minuteWindowStart = Math.floor(now.getTime() / 60000); // epoch minute
  const dayWindowStart = todayDateString();

  let entry = usages[key];
  if (!entry) {
    entry = { key, minuteWindowStart, minuteCount: 0, dayWindowStart, dayCount: 0 };
  }

  // reset minute window if changed
  if (entry.minuteWindowStart !== minuteWindowStart) {
    entry.minuteWindowStart = minuteWindowStart;
    entry.minuteCount = 0;
  }

  // reset day window if changed
  if (entry.dayWindowStart !== dayWindowStart) {
    entry.dayWindowStart = dayWindowStart;
    entry.dayCount = 0;
  }

  const wouldBeMinute = (entry.minuteCount || 0) + 1;
  const wouldBeDay = (entry.dayCount || 0) + 1;

  if (wouldBeMinute > minuteLimit || wouldBeDay > dayLimit) {
    // write back current entry so caller can see updated windows
    usages[key] = entry;
    await writeJson("usage.json", usages);
    return { allowed: false, minuteRemaining: Math.max(0, minuteLimit - (entry.minuteCount || 0)), dayRemaining: Math.max(0, dayLimit - (entry.dayCount || 0)) };
  }

  entry.minuteCount = wouldBeMinute;
  entry.dayCount = wouldBeDay;
  usages[key] = entry;
  await writeJson("usage.json", usages);

  return { allowed: true, minuteRemaining: minuteLimit - entry.minuteCount, dayRemaining: dayLimit - entry.dayCount };
}
