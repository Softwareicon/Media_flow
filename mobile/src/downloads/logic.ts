/**
 * Pure download-manager logic: state machine, scheduling, speed/ETA, duplicates, storage and
 * error classification. No React Native imports, so it is fully unit-tested in __tests__/.
 */
export type DownloadStatus =
  | 'queued' // waiting for a free slot
  | 'authorizing' // asking the server for the media URL
  | 'downloading'
  | 'paused'
  | 'verifying' // checking the file's real type
  | 'saving' // copying into the photo library / chosen folder
  | 'completed'
  | 'failed'
  | 'cancelled';

export const ACTIVE: ReadonlySet<DownloadStatus> = new Set(['authorizing', 'downloading', 'verifying', 'saving']);
export const TERMINAL: ReadonlySet<DownloadStatus> = new Set(['completed', 'failed', 'cancelled']);

const TRANSITIONS: Record<DownloadStatus, DownloadStatus[]> = {
  queued: ['authorizing', 'cancelled', 'failed'],
  authorizing: ['downloading', 'failed', 'cancelled', 'queued'],
  downloading: ['paused', 'verifying', 'failed', 'cancelled', 'queued'],
  paused: ['downloading', 'queued', 'cancelled', 'failed'],
  verifying: ['saving', 'completed', 'failed', 'cancelled'],
  saving: ['completed', 'failed', 'cancelled'],
  completed: [],
  failed: ['queued'], // retry
  cancelled: ['queued'], // retry after cancel
};

export function canTransition(from: DownloadStatus, to: DownloadStatus): boolean {
  return TRANSITIONS[from].includes(to);
}

export interface Schedulable {
  id: string;
  status: DownloadStatus;
  created_at: number;
}

/** Which queued items may start now, FIFO, without exceeding the concurrency limit. */
export function pickToStart<T extends Schedulable>(items: T[], maxConcurrent: number, blocked = false): T[] {
  if (blocked) return [];
  const running = items.filter((i) => ACTIVE.has(i.status)).length;
  const free = Math.max(0, maxConcurrent - running);
  return items
    .filter((i) => i.status === 'queued')
    .sort((a, b) => a.created_at - b.created_at)
    .slice(0, free);
}

/** Moving-window transfer speed; resilient to irregular progress callbacks. */
export class SpeedMeter {
  private samples: Array<[number, number]> = [];

  constructor(private windowMs = 4000) {}

  push(bytes: number, now = Date.now()): void {
    const last = this.samples[this.samples.length - 1];
    if (last && bytes < last[1]) this.samples = []; // restarted from zero
    this.samples.push([now, bytes]);
    while (this.samples.length > 2 && this.samples[0]![0] < now - this.windowMs) this.samples.shift();
  }

  /** bytes per second, or null until there's enough data */
  speed(): number | null {
    if (this.samples.length < 2) return null;
    const [t0, b0] = this.samples[0]!;
    const [t1, b1] = this.samples[this.samples.length - 1]!;
    const dt = (t1 - t0) / 1000;
    return dt > 0.25 ? Math.max(0, (b1 - b0) / dt) : null;
  }

  eta(received: number, total: number | null | undefined): number | null {
    const s = this.speed();
    if (!s || !total || total <= received) return null;
    return (total - received) / s;
  }

  reset(): void {
    this.samples = [];
  }
}

export interface DupCandidate {
  sourceUrl: string;
  optionKey: string; // platform-independent: `${mime}|${width}x${height}|${quality}`
}

export interface DupItem extends DupCandidate {
  id: string;
  status: DownloadStatus;
  fileExists?: boolean;
}

/**
 * A download is a duplicate if the same media+quality is already queued/running, or completed and the
 * file still exists. Failed/cancelled entries never block a new attempt.
 */
export function findDuplicate<T extends DupItem>(items: T[], c: DupCandidate): T | null {
  return (
    items.find(
      (i) =>
        i.sourceUrl === c.sourceUrl &&
        i.optionKey === c.optionKey &&
        (i.status === 'completed' ? i.fileExists !== false : !TERMINAL.has(i.status)),
    ) ?? null
  );
}

/** Keep a safety margin so the OS and other apps don't run out of space. */
export const STORAGE_RESERVE = 200 * 1024 * 1024;

export function storageCheck(freeBytes: number | null, expectedBytes: number | null | undefined, reserve = STORAGE_RESERVE):
  { ok: true } | { ok: false; needed: number; free: number } {
  if (freeBytes == null || !expectedBytes) return { ok: true }; // unknown size: re-checked as bytes arrive
  // Saving to the library makes a second copy before the temp file is removed → need ~2x.
  const needed = expectedBytes * 2 + reserve;
  return freeBytes >= needed ? { ok: true } : { ok: false, needed, free: freeBytes };
}

export type ErrorCode =
  | 'network' | 'server' | 'link_expired' | 'too_large' | 'insufficient_storage' | 'not_media'
  | 'type_mismatch' | 'dangerous_file' | 'permission_denied' | 'size_mismatch' | 'rate_limited' | 'unknown';

export function isRetryable(code: ErrorCode): boolean {
  return ['network', 'server', 'link_expired', 'rate_limited', 'size_mismatch', 'unknown'].includes(code);
}

export const ERROR_TEXT: Record<ErrorCode, string> = {
  network: 'Connection lost. Retry when you’re back online.',
  server: 'The server had a problem. Try again.',
  link_expired: 'The download link expired. Retry to get a fresh one.',
  too_large: 'This file is bigger than the app’s download limit.',
  insufficient_storage: 'Not enough free space on this device.',
  not_media: 'The file wasn’t a photo, video or audio file, so it was deleted.',
  type_mismatch: 'The file didn’t match its declared type and was blocked for safety.',
  dangerous_file: 'The file looked like a program or archive and was blocked.',
  permission_denied: 'Permission to save was denied. Allow it in Settings, or save inside the app.',
  size_mismatch: 'The file arrived incomplete. Retry the download.',
  rate_limited: 'Too many requests right now. Wait a moment and retry.',
  unknown: 'Something went wrong. Retry the download.',
};

export function classifyError(err: unknown): ErrorCode {
  const e = err as { code?: string; status?: number; message?: string } | undefined;
  const code = e?.code ?? '';
  const msg = (e?.message ?? String(err ?? '')).toLowerCase();
  if (code in ERROR_TEXT) return code as ErrorCode;
  if (code === 'analysis_expired' || code === 'media_link_expired' || e?.status === 410) return 'link_expired';
  if (code === 'rate_limited' || e?.status === 429) return 'rate_limited';
  if (e?.status === 413) return 'too_large';
  if (e?.status && e.status >= 500) return 'server';
  if (/no space|enospc|disk full|insufficient storage/.test(msg)) return 'insufficient_storage';
  if (/network|timed out|timeout|offline|connection|unreachable|socket/.test(msg)) return 'network';
  if (/permission/.test(msg)) return 'permission_denied';
  return 'unknown';
}

/** Exponential backoff for automatic retries of transient errors: 2s, 4s, 8s (max 3 tries). */
export function backoffMs(attempt: number): number | null {
  return attempt >= 3 ? null : 2000 * 2 ** attempt;
}
