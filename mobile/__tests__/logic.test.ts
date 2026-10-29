import {
  backoffMs, canTransition, classifyError, findDuplicate, isRetryable, pickToStart, SpeedMeter, storageCheck,
  type DownloadStatus,
} from '../src/downloads/logic';

const item = (id: string, status: DownloadStatus, created_at: number) => ({ id, status, created_at });

describe('state machine', () => {
  it('allows the normal path and retry', () => {
    const path: DownloadStatus[] = ['queued', 'authorizing', 'downloading', 'verifying', 'saving', 'completed'];
    path.slice(1).forEach((to, i) => expect(canTransition(path[i]!, to)).toBe(true));
    expect(canTransition('failed', 'queued')).toBe(true);
    expect(canTransition('downloading', 'paused')).toBe(true);
    expect(canTransition('paused', 'downloading')).toBe(true);
  });
  it('blocks impossible jumps', () => {
    expect(canTransition('completed', 'downloading')).toBe(false);
    expect(canTransition('queued', 'completed')).toBe(false);
    expect(canTransition('paused', 'verifying')).toBe(false);
  });
});

describe('scheduler (queue + concurrency limit)', () => {
  it('fills free slots FIFO', () => {
    const items = [item('a', 'downloading', 1), item('b', 'queued', 3), item('c', 'queued', 2), item('d', 'queued', 4)];
    expect(pickToStart(items, 3).map((i) => i.id)).toEqual(['c', 'b']);
  });
  it('starts nothing when full, paused items do not take a slot', () => {
    expect(pickToStart([item('a', 'downloading', 1), item('b', 'queued', 2)], 1)).toEqual([]);
    expect(pickToStart([item('a', 'paused', 1), item('b', 'queued', 2)], 1).map((i) => i.id)).toEqual(['b']);
  });
  it('holds the queue when blocked (Wi-Fi only on cellular)', () => {
    expect(pickToStart([item('a', 'queued', 1)], 3, true)).toEqual([]);
  });
});

describe('speed and ETA', () => {
  it('computes speed over a moving window', () => {
    const m = new SpeedMeter(4000);
    m.push(0, 0);
    m.push(1_000_000, 1000);
    m.push(2_000_000, 2000);
    expect(m.speed()).toBeCloseTo(1_000_000);
    expect(m.eta(2_000_000, 10_000_000)).toBeCloseTo(8);
  });
  it('returns null until enough data and when total unknown', () => {
    const m = new SpeedMeter();
    expect(m.speed()).toBeNull();
    m.push(10, 0);
    m.push(20, 1000);
    expect(m.eta(20, null)).toBeNull();
  });
  it('resets when a transfer restarts from zero', () => {
    const m = new SpeedMeter();
    m.push(5_000_000, 0);
    m.push(6_000_000, 1000);
    m.push(100, 1500); // interrupted download restarted
    expect(m.speed()).toBeNull();
  });
});

describe('duplicate detection', () => {
  const base = { sourceUrl: 'https://x/1', optionKey: 'video/mp4|1920x1080|1080p' };
  it('flags same media+quality that is active or completed with file present', () => {
    expect(findDuplicate([{ id: '1', status: 'downloading', ...base }], base)?.id).toBe('1');
    expect(findDuplicate([{ id: '2', status: 'completed', fileExists: true, ...base }], base)?.id).toBe('2');
  });
  it('ignores failed/cancelled, deleted files and other qualities', () => {
    expect(findDuplicate([{ id: '1', status: 'failed', ...base }], base)).toBeNull();
    expect(findDuplicate([{ id: '2', status: 'completed', fileExists: false, ...base }], base)).toBeNull();
    expect(findDuplicate([{ id: '3', status: 'queued', ...base, optionKey: 'video/mp4|1280x720|720p' }], base)).toBeNull();
  });
});

describe('insufficient storage', () => {
  it('needs 2x size plus reserve', () => {
    expect(storageCheck(10_000_000_000, 1_000_000_000).ok).toBe(true);
    const r = storageCheck(1_000_000_000, 600_000_000);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.needed).toBe(600_000_000 * 2 + 200 * 1024 * 1024);
  });
  it('allows unknown sizes (checked again during transfer)', () => {
    expect(storageCheck(null, 5).ok).toBe(true);
    expect(storageCheck(10, null).ok).toBe(true);
  });
});

describe('interrupted / failed downloads', () => {
  it('classifies errors', () => {
    expect(classifyError(new Error('The network connection was lost.'))).toBe('network');
    expect(classifyError({ status: 410, code: 'analysis_expired' })).toBe('link_expired');
    expect(classifyError({ status: 429 })).toBe('rate_limited');
    expect(classifyError({ status: 413 })).toBe('too_large');
    expect(classifyError({ status: 502 })).toBe('server');
    expect(classifyError(new Error('ENOSPC: no space left on device'))).toBe('insufficient_storage');
    expect(classifyError('weird')).toBe('unknown');
  });
  it('retries transient errors with backoff, never unsafe ones', () => {
    expect(isRetryable('network')).toBe(true);
    expect(isRetryable('dangerous_file')).toBe(false);
    expect(isRetryable('insufficient_storage')).toBe(false);
    expect([0, 1, 2, 3].map(backoffMs)).toEqual([2000, 4000, 8000, null]);
  });
});
