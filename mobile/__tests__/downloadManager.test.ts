/**
 * Integration tests for the real DownloadManager with MOCKED native modules (expo-file-system,
 * expo-media-library, expo-network) and a mocked API client. They exercise queueing, concurrency,
 * pause/resume, cancel, retries, verification and saving — not real network transfers.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

type Behavior = { bytes?: Uint8Array; fail?: Error; hang?: boolean };

const mockFx: {
  assetFails?: boolean;
  fs: Map<string, Uint8Array>;
  behaviors: Map<string, Behavior>;
  free: number;
  tasks: any[];
  permission: boolean;
  assets: string[];
} = { fs: new Map(), behaviors: new Map(), free: 50e9, tasks: [], permission: true, assets: [] };

const mockMP4 = new Uint8Array([0, 0, 0, 0x20, ...Array.from('ftypisom').map((c) => c.charCodeAt(0)), ...new Array(52).fill(0)]);
const HTML = new Uint8Array(Array.from('<!DOCTYPE html><html><body>error</body></html>              ').map((c) => c.charCodeAt(0)));

jest.mock('expo-file-system', () => {
  const join = (parts: any[]) => parts.map((p) => (typeof p === 'string' ? p : p.uri)).join('/').replace(/([^:])\/+/g, '$1/');
  class File {
    uri: string;
    constructor(...parts: any[]) { this.uri = join(parts); }
    get exists() { return mockFx.fs.has(this.uri); }
    get size() { return mockFx.fs.get(this.uri)?.length ?? 0; }
    open() { const data = mockFx.fs.get(this.uri) ?? new Uint8Array(); return { readBytes: async (n: number) => data.slice(0, n), close: () => undefined }; }
    delete() { mockFx.fs.delete(this.uri); }
    get name() { return this.uri.split('/').pop()!; }
    async copy(dest: any) {
      const target = dest instanceof Directory ? `${dest.uri}/${this.name}` : dest.uri;
      if (mockFx.fs.has(target)) throw new Error('DestinationAlreadyExistsException');
      mockFx.fs.set(target, mockFx.fs.get(this.uri)!);
    }
    static createDownloadTask(url: string, dest: File, opts: any) { const t = new DownloadTask(url, dest, opts); mockFx.tasks.push(t); return t; }
  }
  class Directory {
    uri: string;
    constructor(...parts: any[]) { this.uri = join(parts); }
    get exists() { return [...mockFx.fs.keys()].some((k) => k.startsWith(this.uri + '/')) || mockFx.fs.has(this.uri + '/.dir'); }
    create() { mockFx.fs.set(this.uri + '/.dir', new Uint8Array()); }
    delete() { for (const k of [...mockFx.fs.keys()]) if (k.startsWith(this.uri + '/')) mockFx.fs.delete(k); }
    createFile(name: string) { return new File(this, name); }
    static async pickDirectoryAsync() { return new Directory('content://picked'); }
  }
  class DownloadTask {
    state = 'idle';
    private resolveFn: ((f: File | null) => void) | null = null;
    url: string;
    dest: File;
    opts: any;
    constructor(url: string, dest: File, opts: any) { this.url = url; this.dest = dest; this.opts = opts; }
    private run(): Promise<File | null> {
      this.state = 'active';
      const b = mockFx.behaviors.get(this.url) ?? { bytes: mockMP4 };
      return new Promise((resolve, reject) => {
        this.resolveFn = resolve;
        if (b.fail) { this.state = 'error'; reject(b.fail); return; }
        if (b.hang) { this.opts?.onProgress?.({ bytesWritten: 10, totalBytes: 0 }); return; }
        const bytes = b.bytes!;
        this.opts?.onProgress?.({ bytesWritten: bytes.length, totalBytes: bytes.length });
        mockFx.fs.set(this.dest.uri, bytes);
        this.state = 'completed';
        resolve(this.dest);
      });
    }
    downloadAsync() { return this.run(); }
    resumeAsync() { return this.run(); }
    async pauseAsync() { this.state = 'paused'; this.resolveFn?.(null); }
    cancel() { this.state = 'cancelled'; this.resolveFn?.(null); }
    savable() { return { url: this.url, fileUri: this.dest.uri, isDirectory: false, resumeData: 'r1' }; }
    finish() { mockFx.behaviors.set(this.url, { bytes: mockMP4 }); mockFx.fs.set(this.dest.uri, mockMP4); this.state = 'completed'; this.resolveFn?.(this.dest); }
    static fromSavable(s: any, opts: any) { const t = new DownloadTask(s.url, new File(s.fileUri), opts); mockFx.tasks.push(t); return t; }
  }
  return { File, Directory, DownloadTask, Paths: { document: new Directory('file:///doc'), get availableDiskSpace() { return mockFx.free; } } };
});

jest.mock('expo-media-library', () => ({
  requestPermissionsAsync: jest.fn(async () => ({ granted: mockFx.permission })),
  Asset: { create: jest.fn(async (uri: string) => { if (mockFx.assetFails) throw new Error('Photos rejected this file'); mockFx.assets.push(uri); return { id: `asset-${mockFx.assets.length}` }; }) },
}));

jest.mock('expo-network', () => ({
  NetworkStateType: { WIFI: 'WIFI', ETHERNET: 'ETHERNET', CELLULAR: 'CELLULAR' },
  getNetworkStateAsync: jest.fn(async () => ({ type: 'WIFI', isConnected: true })),
  addNetworkStateListener: jest.fn(() => ({ remove: () => undefined })),
}));

jest.mock('@/db/database', () => ({
  allDownloads: jest.fn(async () => []),
  upsertDownload: jest.fn(async () => undefined),
  deleteDownloadRow: jest.fn(async () => undefined),
}));

jest.mock('@/api/client', () => {
  class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, msg: string) { super(msg); this.status = status; this.code = code; }
  }
  let n = 0;
  return {
    ApiError,
    api: {
      authorizeDownload: jest.fn(async (analysisId: string, optionId: string) => ({
        download: { id: `srv-${++n}` }, media_url: `https://cdn.test/${analysisId}/${optionId}`, request_headers: {}, url_expires_at: null,
        max_bytes: 4e9,
      })),
      analyze: jest.fn(),
      reportDownload: jest.fn(async () => ({})),
      cancelDownload: jest.fn(async () => ({})),
      deleteDownload: jest.fn(async () => undefined),
    },
  };
});

const flush = async (times = 8) => { for (let i = 0; i < times; i += 1) await Promise.resolve(); await new Promise((r) => setImmediate(r)); };

function analysis(id = 'a1', extra: any = {}) {
  return {
    analysis_id: id, source_url: `https://site.test/${id}`, platform: 'web', platform_name: 'Websites', status: 'downloadable',
    title: `Clip ${id}`, media_type: 'video', alternatives: [], best_option_id: 'f0',
    options: [{ id: 'f0', kind: 'video', label: 'Original · mockMP4', quality_label: 'Original', mime_type: 'video/mp4', extension: 'mp4',
      size_bytes: mockMP4.length, size_is_estimate: false, is_original: true }],
    ...extra,
  } as any;
}

function load() {
  let mod: any;
  let client: any;
  let network: any;
  jest.isolateModules(() => {
    mod = require('../src/downloads/DownloadManager');
    client = require('@/api/client'); // same registry as the manager's import
    network = require('expo-network');
  });
  return { m: mod.downloadManager as any, api: client.api, ApiError: client.ApiError, network };
}

beforeEach(() => {
  mockFx.fs.clear(); mockFx.behaviors.clear(); mockFx.tasks = []; mockFx.free = 50e9; mockFx.permission = true; mockFx.assets = []; mockFx.assetFails = false;
  jest.clearAllMocks();
});

const statusOf = (m: any, id: string) => m.getSnapshot().find((i: any) => i.id === id)?.status;

test('happy path: authorize → download → verify → save to Photos → report', async () => {
  const { m, api } = load();
  m.configure({ maxConcurrent: 2, saveTarget: 'library' });
  const r = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  const item = m.getSnapshot()[0];
  expect(r.kind).toBe('queued');
  expect(item.status).toBe('completed');
  expect(item.saved_location).toBe('library');
  expect(item.received_bytes).toBe(mockMP4.length);
  expect(mockFx.assets).toHaveLength(1);
  expect(api.reportDownload).toHaveBeenCalledWith(expect.stringMatching(/^srv-/), 'completed', mockMP4.length);
});

test('HTML error page served as video is blocked and deleted, never saved', async () => {
  const { m } = load();
  mockFx.behaviors.set('https://cdn.test/a1/f0', { bytes: HTML });
  await m.enqueue(analysis(), { ...analysis().options[0], size_bytes: HTML.length });
  await flush();
  const item = m.getSnapshot()[0];
  expect(item.status).toBe('failed');
  expect(item.error_code).toBe('dangerous_file');
  expect(mockFx.assets).toHaveLength(0);
  expect([...mockFx.fs.keys()].filter((k) => k.endsWith('.mp4'))).toHaveLength(0);
});

test('incomplete file (size mismatch) fails', async () => {
  const { m } = load();
  await m.enqueue(analysis(), { ...analysis().options[0], size_bytes: 999_999 });
  await flush();
  expect(m.getSnapshot()[0].error_code).toBe('size_mismatch');
});

test('concurrency limit and FIFO queue', async () => {
  const { m } = load();
  m.configure({ maxConcurrent: 1 });
  mockFx.behaviors.set('https://cdn.test/a1/f0', { hang: true });
  const one = await m.enqueue(analysis('a1'), analysis('a1').options[0]);
  const two = await m.enqueue(analysis('a2'), analysis('a2').options[0]);
  await flush();
  expect(statusOf(m, one.item.id)).toBe('downloading');
  expect(statusOf(m, two.item.id)).toBe('queued');
  mockFx.tasks[0].finish();
  await flush(16);
  expect(statusOf(m, one.item.id)).toBe('completed');
  expect(statusOf(m, two.item.id)).toBe('completed');
});

test('pause keeps resume state; resume completes', async () => {
  const { m } = load();
  mockFx.behaviors.set('https://cdn.test/a1/f0', { hang: true });
  const { item } = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  await m.pause(item.id);
  await flush();
  expect(statusOf(m, item.id)).toBe('paused');
  expect(m.getSnapshot()[0].resume_state).toContain('r1');
  mockFx.behaviors.set('https://cdn.test/a1/f0', { bytes: mockMP4 });
  await m.resume(item.id);
  await flush(16);
  expect(statusOf(m, item.id)).toBe('completed');
});

test('cancel stops the transfer, deletes partial files and tells the server', async () => {
  const { m, api } = load();
  mockFx.behaviors.set('https://cdn.test/a1/f0', { hang: true });
  const { item } = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  await m.cancel(item.id);
  await flush();
  expect(statusOf(m, item.id)).toBe('cancelled');
  expect([...mockFx.fs.keys()].some((k) => k.includes(item.id))).toBe(false);
  expect(api.cancelDownload).toHaveBeenCalledWith(expect.stringMatching(/^srv-/));
  m.retry(item.id);
  mockFx.behaviors.set('https://cdn.test/a1/f0', { bytes: mockMP4 });
  await flush(16);
  expect(statusOf(m, item.id)).toBe('completed');
});

test('interrupted by network error → auto-retry with backoff → completes', async () => {
  jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
  try {
    const { m } = load();
    mockFx.behaviors.set('https://cdn.test/a1/f0', { fail: new Error('The network connection was lost.') });
    const { item } = await m.enqueue(analysis(), analysis().options[0]);
    await flush();
    expect(statusOf(m, item.id)).toBe('failed');
    expect(m.getSnapshot()[0].error_code).toBe('network');
    mockFx.behaviors.set('https://cdn.test/a1/f0', { bytes: mockMP4 });
    jest.advanceTimersByTime(2100);
    await flush(16);
    expect(statusOf(m, item.id)).toBe('completed');
  } finally {
    jest.useRealTimers();
  }
});

test('expired analysis is re-analyzed automatically and the same quality is downloaded', async () => {
  const { m, api, ApiError } = load();
  api.authorizeDownload.mockImplementationOnce(async () => { throw new ApiError(410, 'analysis_expired', 'expired'); });
  api.analyze.mockResolvedValueOnce(analysis('a9'));
  await m.enqueue(analysis('a1'), analysis('a1').options[0]);
  await flush(16);
  expect(api.analyze).toHaveBeenCalledWith('https://site.test/a1');
  expect(m.getSnapshot()[0].status).toBe('completed');
  expect(m.getSnapshot()[0].analysis_id).toBe('a9');
});

test('duplicate detection and insufficient storage', async () => {
  const { m } = load();
  await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  expect((await m.enqueue(analysis(), analysis().options[0])).kind).toBe('duplicate');
  expect((await m.enqueue(analysis(), analysis().options[0], true)).kind).toBe('queued');
  mockFx.free = 100 * 1024 * 1024;
  const big = { ...analysis('b').options[0], size_bytes: 2e9 };
  expect((await m.enqueue(analysis('b'), big)).kind).toBe('no_space');
});

test('photo permission denied → file kept in the app, still completed', async () => {
  const { m } = load();
  mockFx.permission = false;
  m.configure({ saveTarget: 'library' });
  await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  const item = m.getSnapshot()[0];
  expect(item.status).toBe('completed');
  expect(item.saved_location).toBe('app');
  expect(mockFx.assets).toHaveLength(0);
});


// ---- regression tests for the independent review findings

test('cancel while authorizing: nothing downloads, nothing reaches Photos, server record released', async () => {
  const { m, api } = load();
  let release!: () => void;
  api.authorizeDownload.mockImplementationOnce(() => new Promise((resolve) => {
    release = () => resolve({ download: { id: 'srv-late' }, media_url: 'https://cdn.test/a1/f0', request_headers: {}, url_expires_at: null, max_bytes: 4e9 });
  }));
  const { item } = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  expect(statusOf(m, item.id)).toBe('authorizing');
  await m.cancel(item.id);
  release();
  await flush(16);
  expect(statusOf(m, item.id)).toBe('cancelled');
  expect(mockFx.tasks).toHaveLength(0);
  expect(mockFx.assets).toHaveLength(0);
  expect(api.cancelDownload).toHaveBeenCalledWith('srv-late');
  expect(api.reportDownload).not.toHaveBeenCalledWith('srv-late', 'completed', expect.anything());
});

test('removing a failed item during its retry backoff leaves no zombie row', async () => {
  jest.useFakeTimers({ doNotFake: ['setImmediate', 'nextTick'] });
  try {
    const { m } = load();
    const db = require('@/db/database');
    mockFx.behaviors.set('https://cdn.test/a1/f0', { fail: new Error('network timeout') });
    const { item } = await m.enqueue(analysis(), analysis().options[0]);
    await flush();
    expect(statusOf(m, item.id)).toBe('failed');
    await m.clearFinished();
    const writesAfterRemove = db.upsertDownload.mock.calls.length;
    jest.advanceTimersByTime(10_000);
    await flush(16);
    expect(m.getSnapshot()).toHaveLength(0);
    expect(db.upsertDownload.mock.calls.length).toBe(writesAfterRemove);
    expect(mockFx.tasks).toHaveLength(1); // never restarted
  } finally {
    jest.useRealTimers();
  }
});

test('Android folder target: file is copied into the chosen folder', async () => {
  const { m } = load();
  require('react-native').Platform.OS = 'android';
  m.configure({ saveTarget: 'folder', folderUri: 'content://picked' });
  await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  const item = m.getSnapshot()[0];
  expect(item.status).toBe('completed');
  expect(item.saved_location).toBe('folder');
  expect(mockFx.fs.get(`content://picked/${item.file_name}`)).toEqual(mockMP4);
});

test('Photos rejecting the file keeps it in the app instead of re-downloading', async () => {
  const { m } = load();
  mockFx.assetFails = true;
  m.configure({ saveTarget: 'library' });
  await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  const item = m.getSnapshot()[0];
  expect(item.status).toBe('completed');
  expect(item.saved_location).toBe('app');
  expect(mockFx.tasks).toHaveLength(1);
});

test('resume after app restart re-authorizes; a changed URL restarts instead of reusing stale resume data', async () => {
  const { m, api } = load();
  mockFx.behaviors.set('https://cdn.test/a1/f0', { hang: true });
  const { item } = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  await m.pause(item.id);
  await flush();
  // simulate a restart: the native task is gone, resume data is all that's left
  (m as any).tasks.clear();
  api.authorizeDownload.mockImplementationOnce(async () => ({ download: { id: 'srv-new' }, media_url: 'https://cdn.test/resigned', request_headers: {}, url_expires_at: null, max_bytes: 4e9 }));
  await m.resume(item.id);
  await flush(16);
  expect(api.authorizeDownload).toHaveBeenCalledTimes(2);
  expect(mockFx.tasks[mockFx.tasks.length - 1].url).toBe('https://cdn.test/resigned');
  expect(statusOf(m, item.id)).toBe('completed');
  const firstServerId = api.authorizeDownload.mock.results[0].value;
  expect(api.cancelDownload).toHaveBeenCalledWith((await firstServerId).download.id); // earlier record not orphaned
});

test('double-tapping pause only pauses once', async () => {
  const { m } = load();
  mockFx.behaviors.set('https://cdn.test/a1/f0', { hang: true });
  const { item } = await m.enqueue(analysis(), analysis().options[0]);
  await flush();
  const spy = jest.spyOn(mockFx.tasks[0], 'pauseAsync');
  await Promise.all([m.pause(item.id), m.pause(item.id)]);
  expect(spy).toHaveBeenCalledTimes(1);
  expect(statusOf(m, item.id)).toBe('paused');
});

test('Wi-Fi-only queue listens for network changes', async () => {
  const { m, network } = load();
  await m.init();
  expect(network.addNetworkStateListener).toHaveBeenCalled();
});
