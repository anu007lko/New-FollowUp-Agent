// Per-user temporary queue skip manager for Recruitment Follow-Up Agent.
// Stores temporary skipped record IDs with return expiration timestamps (tomorrow 9:00 AM local time).

const SKIPPED_RECORDS_KEY = 'fua-skipped-records';

export interface SkippedMap {
  [recordId: string]: string; // ISO string expiration timestamp
}

export function getTomorrowMorning9AM(fromDate: Date = new Date()): Date {
  const tomorrow = new Date(fromDate);
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(9, 0, 0, 0);
  return tomorrow;
}

export function getSkippedRecordIds(nowTimeMs: number = Date.now()): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = localStorage.getItem(SKIPPED_RECORDS_KEY);
    if (!raw) return new Set();
    const map: SkippedMap = JSON.parse(raw);
    const validIds = new Set<string>();
    const cleanedMap: SkippedMap = {};
    let changed = false;

    for (const [id, expireIso] of Object.entries(map)) {
      const expireTime = new Date(expireIso).getTime();
      if (expireTime > nowTimeMs) {
        validIds.add(id);
        cleanedMap[id] = expireIso;
      } else {
        changed = true; // Prune expired entry
      }
    }

    if (changed) {
      if (Object.keys(cleanedMap).length > 0) {
        localStorage.setItem(SKIPPED_RECORDS_KEY, JSON.stringify(cleanedMap));
      } else {
        localStorage.removeItem(SKIPPED_RECORDS_KEY);
      }
    }

    return validIds;
  } catch {
    return new Set();
  }
}

export function skipRecord(recordId: string, fromDate: Date = new Date()): void {
  if (typeof window === 'undefined' || !recordId) return;
  try {
    const expireIso = getTomorrowMorning9AM(fromDate).toISOString();
    const raw = localStorage.getItem(SKIPPED_RECORDS_KEY);
    const map: SkippedMap = raw ? JSON.parse(raw) : {};
    map[recordId] = expireIso;
    localStorage.setItem(SKIPPED_RECORDS_KEY, JSON.stringify(map));
  } catch {
    // Fail silently without blocking UI
  }
}

export function isRecordSkipped(recordId: string, nowTimeMs: number = Date.now()): boolean {
  return getSkippedRecordIds(nowTimeMs).has(recordId);
}

export function clearSkippedRecords(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(SKIPPED_RECORDS_KEY);
  } catch {
    // Fail silently
  }
}
