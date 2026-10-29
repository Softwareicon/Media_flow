/**
 * Device-side download manager.
 *
 * Flow per item: queued → authorizing (server releases the authorized media URL) → downloading
 * (device fetches the bytes directly; the server never proxies media) → verifying (magic bytes,
 * size) → saving (photo library / user folder) → completed. Every state is persisted to SQLite.
 *
 * Platform limits, stated honestly:
 * - iOS: transfers use a background URLSession, so they can finish while the app is suspended.
 *   iOS schedules that work; force-quitting the app cancels it.
 * - Android: transfers continue while the app process is alive. If the process is killed
 *   mid-transfer, the item comes back queued and downloads again from the start.
 * - Pause/resume needs the source server to support HTTP range requests. A paused item resumes
 *   from where it stopped only while the source URL is unchanged (resume data embeds the original
 *   request); if the newly authorized URL differs (e.g. a re-signed link), it restarts from zero.
 */
import { Asset, requestPermissionsAsync } from 'expo-media-library';
import { Directory, DownloadTask, File, Paths } from 'expo-file-system';
import type { DownloadPauseState } from 'expo-file-system';
import * as Network from 'expo-network';
import { Platform } from 'react-native';

import { api, ApiError } from '@/api/client';
import type { Analysis, MediaOption } from '@/api/types';
import { allDownloads, deleteDownloadRow, type DownloadRow, upsertDownload } from '@/db/database';
import { verifyHead } from '@/lib/fileSignature';
import { safeFileName } from '@/lib/filenames';
import {
  ACTIVE, backoffMs, canTransition, classifyError, type DownloadStatus, type ErrorCode, findDuplicate, isRetryable,
  pickToStart, SpeedMeter, storageCheck, TERMINAL,
} from './logic';

export interface DownloadItem extends DownloadRow {
  speed: number | null;
  eta: number | null;
  fileExists: boolean;
}

export interface ManagerConfig {
  maxConcurrent: number;
  wifiOnly: boolean;
  saveTarget: 'library' | 'app' | 'folder';
  folderUri: string | null;
}

export type EnqueueResult = { kind: 'queued'; item: DownloadItem } | { kind: 'duplicate'; item: DownloadItem } |
  { kind: 'no_space'; needed: number; free: number };

class ManagerError extends Error {
  code: ErrorCode;
  constructor(code: ErrorCode, message?: string) {
    super(message ?? code);
    this.code = code;
  }
}

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
export const optionKey = (o: Pick<MediaOption, 'mime_type' | 'width' | 'height' | 'quality_label' | 'id'>) =>
  `${o.mime_type}|${o.width ?? 0}x${o.height ?? 0}|${o.quality_label ?? o.id}`;

function freeSpace(): number | null {
  try {
    return Paths.availableDiskSpace;
  } catch {
    return null;
  }
}

const toRow = (item: DownloadItem): DownloadRow => {
  const { speed: _s, eta: _e, fileExists: _f, ...row } = item;
  return row;
};

class DownloadManager {
  private items = new Map<string, DownloadItem>();
  private tasks = new Map<string, DownloadTask>();
  private meters = new Map<string, SpeedMeter>();
  private transferTotals = new Map<string, number>();
  private limits = new Map<string, number>();
  private retryTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private pausing = new Set<string>();
  private listeners = new Set<() => void>();
  private snapshot: DownloadItem[] = [];
  private lastEmit = 0;
  private emitTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPersist = new Map<string, number>();
  private config: ManagerConfig = { maxConcurrent: 2, wifiOnly: false, saveTarget: 'library', folderUri: null };
  private ready: Promise<void> | null = null;
  onEvent: ((e: { type: 'completed' | 'failed'; item: DownloadItem }) => void) | null = null;

  // ---------- store plumbing (useSyncExternalStore)
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  getSnapshot = () => this.snapshot;

  private emit(immediate = false) {
    const run = () => {
      this.emitTimer = null;
      this.lastEmit = Date.now();
      this.snapshot = [...this.items.values()].sort((a, b) => b.created_at - a.created_at);
      this.listeners.forEach((l) => l());
    };
    if (immediate || Date.now() - this.lastEmit > 250) run();
    else this.emitTimer ??= setTimeout(run, 250);
  }

  /** The item is still the live record (not removed / replaced). Removed items must never be re-saved. */
  private live(item: DownloadItem): boolean {
    return this.items.get(item.id) === item;
  }

  /** Live and not cancelled: in-flight async work should continue. */
  private active(item: DownloadItem): boolean {
    return this.live(item) && item.status !== 'cancelled';
  }

  private async save(item: DownloadItem, force = true) {
    if (!this.live(item)) return;
    item.updated_at = Date.now();
    const last = this.lastPersist.get(item.id) ?? 0;
    if (force || item.updated_at - last > 2000) {
      this.lastPersist.set(item.id, item.updated_at);
      await upsertDownload(toRow(item)).catch(() => undefined);
    }
  }

  private set(item: DownloadItem, status: DownloadStatus, patch: Partial<DownloadRow> = {}): boolean {
    if (!this.live(item)) return false;
    if (item.status !== status && !canTransition(item.status, status)) return false;
    Object.assign(item, patch, { status });
    if (TERMINAL.has(status) || status === 'paused' || status === 'queued') {
      item.speed = null;
      item.eta = null;
    }
    void this.save(item);
    this.emit(true);
    return true;
  }

  // ---------- lifecycle
  init(): Promise<void> {
    this.ready ??= (async () => {
      const rows = await allDownloads().catch(() => [] as DownloadRow[]);
      for (const r of rows) {
        const item: DownloadItem = { ...r, speed: null, eta: null, fileExists: !!r.file_uri && new File(r.file_uri).exists };
        if (ACTIVE.has(item.status)) {
          // Closed mid-transfer: no live task survives a restart, so it goes back to the queue.
          // A paused item keeps its resume data and re-authorizes when resumed.
          item.status = 'queued';
          await upsertDownload(toRow(item)).catch(() => undefined);
        }
        this.items.set(item.id, item);
      }
      try {
        // Wi-Fi-only queue: start waiting items as soon as the connection changes.
        Network.addNetworkStateListener(() => void this.pump());
      } catch {
        /* listener unavailable (tests / web) */
      }
      this.emit(true);
      void this.pump();
    })();
    return this.ready;
  }

  configure(c: Partial<ManagerConfig>) {
    this.config = { ...this.config, ...c };
    void this.pump();
  }

  // ---------- public API
  async enqueue(analysis: Analysis, option: MediaOption, allowDuplicate = false): Promise<EnqueueResult> {
    await this.init();
    const key = optionKey(option);
    if (!allowDuplicate) {
      const dup = findDuplicate([...this.items.values()].map((i) => ({ ...i, sourceUrl: i.source_url, optionKey: i.option_key })),
        { sourceUrl: analysis.source_url, optionKey: key });
      if (dup) return { kind: 'duplicate', item: this.items.get(dup.id)! };
    }
    const space = storageCheck(freeSpace(), option.size_bytes);
    if (!space.ok) return { kind: 'no_space', needed: space.needed, free: space.free };

    const now = Date.now();
    const item: DownloadItem = {
      id: newId(), server_id: null, analysis_id: analysis.analysis_id, option_id: option.id, option_key: key,
      source_url: analysis.source_url, platform: analysis.platform, platform_name: analysis.platform_name,
      title: analysis.title ?? null, author: analysis.author ?? null, thumbnail_url: analysis.thumbnail_url ?? null,
      kind: option.kind, mime_type: option.mime_type, extension: option.extension, quality_label: option.quality_label ?? null,
      width: option.width ?? null, height: option.height ?? null, duration: analysis.duration_seconds ?? null,
      file_name: safeFileName(analysis.title, option.extension, analysis.platform), file_uri: null, saved_location: null,
      asset_id: null, expected_bytes: option.size_is_estimate ? null : option.size_bytes ?? null, received_bytes: 0,
      status: 'queued', error_code: null, attempts: 0, resume_state: null, created_at: now, updated_at: now,
      completed_at: null, speed: null, eta: null, fileExists: false,
    };
    this.items.set(item.id, item);
    await this.save(item);
    this.emit(true);
    void this.pump();
    return { kind: 'queued', item };
  }

  async pause(id: string) {
    const item = this.items.get(id);
    const task = this.tasks.get(id);
    if (!item || item.status !== 'downloading' || !task || this.pausing.has(id)) return; // ignore double taps
    this.pausing.add(id);
    try {
      await task.pauseAsync();
      this.set(item, 'paused', { resume_state: JSON.stringify(task.savable()) });
    } catch {
      /* source doesn't allow pausing mid-flight; leave it running */
    } finally {
      this.pausing.delete(id);
    }
    void this.pump();
  }

  async resume(id: string) {
    const item = this.items.get(id);
    if (!item || item.status !== 'paused') return;
    const task = this.tasks.get(id);
    const running = [...this.items.values()].filter((i) => ACTIVE.has(i.status)).length;
    if (task && task.state === 'paused' && running < this.config.maxConcurrent) {
      // same session: the native task is still alive and holds a valid request
      if (this.set(item, 'downloading')) void this.runTransfer(item, null);
      return;
    }
    // No slot, or no live task (e.g. after an app restart): queue it so start() re-authorizes first.
    this.set(item, 'queued');
    void this.pump();
  }

  async cancel(id: string) {
    const item = this.items.get(id);
    if (!item || TERMINAL.has(item.status)) return;
    if (!this.set(item, 'cancelled', { resume_state: null, received_bytes: 0, file_uri: null })) return;
    this.tasks.get(id)?.cancel();
    this.tasks.delete(id);
    this.deleteFiles(item);
    if (item.server_id) api.cancelDownload(item.server_id).catch(() => undefined);
    void this.pump();
  }

  retry(id: string) {
    const item = this.items.get(id);
    if (!item || (item.status !== 'failed' && item.status !== 'cancelled')) return;
    this.clearRetryTimer(id);
    this.set(item, 'queued', { error_code: null, attempts: 0 });
    void this.pump();
  }

  /** Remove the record and the in-app file. A copy already in the photo library stays there. */
  async remove(id: string) {
    const item = this.items.get(id);
    if (!item) return;
    if (!TERMINAL.has(item.status)) await this.cancel(id);
    this.clearRetryTimer(id);
    this.deleteFiles(item);
    this.items.delete(id);
    this.lastPersist.delete(id);
    await deleteDownloadRow(id).catch(() => undefined);
    if (item.server_id) api.deleteDownload(item.server_id).catch(() => undefined);
    this.emit(true);
  }

  async clearFinished() {
    for (const i of [...this.items.values()]) if (i.status === 'failed' || i.status === 'cancelled') await this.remove(i.id);
  }

  // ---------- scheduler
  async pump() {
    let blocked = false;
    if (this.config.wifiOnly) {
      const net = await Network.getNetworkStateAsync().catch(() => null);
      blocked = !!net && net.type !== Network.NetworkStateType.WIFI && net.type !== Network.NetworkStateType.ETHERNET;
    }
    for (const item of pickToStart([...this.items.values()], this.config.maxConcurrent, blocked)) {
      void this.start(item);
    }
  }

  private async start(item: DownloadItem) {
    if (!this.set(item, 'authorizing')) return;
    const previousServerId = item.server_id;
    try {
      const ticket = await this.authorize(item);
      if (!this.active(item) || item.status !== 'authorizing') {
        // cancelled or removed while we were waiting: release the new server record too
        api.cancelDownload(ticket.download.id).catch(() => undefined);
        return;
      }
      if (previousServerId && previousServerId !== ticket.download.id) {
        api.cancelDownload(previousServerId).catch(() => undefined); // don't orphan the earlier record
      }
      item.server_id = ticket.download.id;
      this.limits.set(item.id, ticket.max_bytes);
      if (item.resume_state) {
        const prev = JSON.parse(item.resume_state) as DownloadPauseState;
        if (prev.url !== ticket.media_url) {
          // Native resume data is bound to the original request; with a new URL we must start over.
          this.tasks.get(item.id)?.cancel();
          this.tasks.delete(item.id);
          this.deleteFiles(item);
          item.resume_state = null;
          item.received_bytes = 0;
        }
      }
      if (!this.set(item, 'downloading')) return;
      api.reportDownload(ticket.download.id, 'in_progress').catch(() => undefined);
      await this.runTransfer(item, { url: ticket.media_url, headers: ticket.request_headers });
    } catch (e) {
      if (this.active(item)) this.fail(item, e);
    }
  }

  private async authorize(item: DownloadItem) {
    if (item.analysis_id) {
      try {
        return await api.authorizeDownload(item.analysis_id, item.option_id);
      } catch (e) {
        if (!(e instanceof ApiError) || (e.status !== 410 && e.status !== 404)) throw e;
      }
    }
    // Analysis expired (they last ~15 min): analyze again and pick the same quality.
    const fresh = await api.analyze(item.source_url);
    const match = fresh.options.find((o) => optionKey(o) === item.option_key) ?? fresh.options.find((o) => o.id === item.option_id);
    if (fresh.status !== 'downloadable' || !fresh.analysis_id || !match) {
      throw new ManagerError('link_expired', fresh.explanation ?? 'This quality is no longer available.');
    }
    item.analysis_id = fresh.analysis_id;
    item.option_id = match.id;
    return api.authorizeDownload(fresh.analysis_id, match.id);
  }

  private destination(item: DownloadItem): File {
    const dir = new Directory(Paths.document, 'downloads', item.id);
    if (!dir.exists) dir.create({ intermediates: true });
    return new File(dir, item.file_name);
  }

  private async runTransfer(item: DownloadItem, fresh: { url: string; headers: Record<string, string> } | null) {
    const meter = this.meters.get(item.id) ?? new SpeedMeter();
    this.meters.set(item.id, meter);
    const maxBytes = this.limits.get(item.id) ?? Number.POSITIVE_INFINITY;
    const onProgress = ({ bytesWritten, totalBytes }: { bytesWritten: number; totalBytes: number }) => {
      if (!this.active(item)) return;
      if (bytesWritten > maxBytes) {
        this.tasks.get(item.id)?.cancel();
        this.fail(item, new ManagerError('too_large'));
        return;
      }
      meter.push(bytesWritten);
      item.received_bytes = bytesWritten;
      if (totalBytes > 0) {
        this.transferTotals.set(item.id, totalBytes);
        // the size declared at analysis time is kept for the integrity check; only fill it in when unknown
        item.expected_bytes ??= totalBytes;
      }
      item.speed = meter.speed();
      item.eta = meter.eta(bytesWritten, item.expected_bytes);
      void this.save(item, false);
      this.emit();
    };
    try {
      let task = this.tasks.get(item.id);
      let result: File | null;
      if (task && task.state === 'paused') {
        result = await task.resumeAsync();
      } else if (item.resume_state) {
        task = DownloadTask.fromSavable(JSON.parse(item.resume_state) as DownloadPauseState, { sessionType: 'background', onProgress });
        this.tasks.set(item.id, task);
        result = await task.resumeAsync();
      } else {
        if (!fresh) throw new ManagerError('link_expired');
        const dest = this.destination(item);
        item.file_uri = dest.uri;
        task = File.createDownloadTask(fresh.url, dest, { headers: fresh.headers, sessionType: 'background', onProgress });
        this.tasks.set(item.id, task);
        result = await task.downloadAsync();
      }
      if (!result) return; // paused or cancelled — state already updated by pause()/cancel()
      if (!this.active(item) || item.status !== 'downloading') {
        if (!this.active(item)) this.deleteFiles(item);
        return;
      }
      this.tasks.delete(item.id);
      item.file_uri = result.uri;
      await this.verifyAndSave(item, result);
    } catch (e) {
      if (!this.active(item) || item.status === 'paused') return;
      const free = freeSpace();
      if (free != null && free < 20 * 1024 * 1024) this.fail(item, new ManagerError('insufficient_storage'));
      else this.fail(item, e);
    }
  }

  private async verifyAndSave(item: DownloadItem, file: File) {
    if (!this.set(item, 'verifying', { resume_state: null })) return;
    const handle = file.open();
    let head: Uint8Array;
    try {
      head = await handle.readBytes(64);
    } finally {
      handle.close();
    }
    if (!this.active(item)) return void this.deleteFiles(item);
    const verdict = verifyHead(head, item.mime_type);
    if (!verdict.ok) {
      file.delete();
      throw new ManagerError(verdict.reason === 'dangerous' ? 'dangerous_file' : verdict.reason);
    }
    // Integrity: the file must match what the transfer announced (catches truncation) and the size
    // declared when the link was analyzed (catches a different file being served).
    const size = file.size;
    const announced = this.transferTotals.get(item.id);
    this.transferTotals.delete(item.id);
    if ((announced && size !== announced) || (item.expected_bytes && size !== item.expected_bytes)) {
      file.delete();
      throw new ManagerError('size_mismatch');
    }
    item.received_bytes = size;
    item.mime_type = verdict.mime;

    let location: DownloadRow['saved_location'] = 'app';
    let assetId: string | null = null;
    if (this.config.saveTarget === 'library' && item.kind !== 'audio') {
      if (!this.set(item, 'saving')) return;
      try {
        const perm = await requestPermissionsAsync(true, ['photo', 'video']);
        if (perm.granted && this.active(item)) {
          const asset = await Asset.create(file.uri);
          assetId = asset.id;
          location = 'library';
        }
      } catch {
        // Photos rejected the file (e.g. WebM on iOS) or limited access: keep it in the app instead of re-downloading.
      }
    } else if (this.config.saveTarget === 'folder' && Platform.OS === 'android' && this.config.folderUri) {
      if (!this.set(item, 'saving')) return;
      try {
        await file.copy(new Directory(this.config.folderUri)); // copies into the folder under its own name
        location = 'folder';
      } catch {
        /* folder permission revoked or name taken: file stays available in the app */
      }
    }
    if (!this.active(item)) return void this.deleteFiles(item);
    item.fileExists = true;
    if (!this.set(item, 'completed', { saved_location: location, asset_id: assetId, completed_at: Date.now() })) return;
    if (item.server_id) api.reportDownload(item.server_id, 'completed', size).catch(() => undefined);
    this.onEvent?.({ type: 'completed', item });
    void this.pump();
  }

  private clearRetryTimer(id: string) {
    const t = this.retryTimers.get(id);
    if (t) clearTimeout(t);
    this.retryTimers.delete(id);
  }

  private fail(item: DownloadItem, err: unknown) {
    if (!this.live(item) || TERMINAL.has(item.status)) return;
    const code = err instanceof ManagerError ? err.code : classifyError(err);
    this.tasks.delete(item.id);
    if (code !== 'network' && code !== 'link_expired') {
      this.deleteFiles(item);
      item.resume_state = null;
    }
    item.attempts += 1;
    this.set(item, 'failed', { error_code: code });
    if (item.server_id) api.reportDownload(item.server_id, 'failed', item.received_bytes, code).catch(() => undefined);
    const delay = isRetryable(code) && code !== 'link_expired' ? backoffMs(item.attempts - 1) : null;
    if (delay != null) {
      this.clearRetryTimer(item.id);
      const t = setTimeout(() => {
        this.retryTimers.delete(item.id);
        if (this.live(item) && item.status === 'failed') {
          this.set(item, 'queued');
          void this.pump();
        }
      }, delay);
      (t as { unref?: () => void }).unref?.();
      this.retryTimers.set(item.id, t);
    } else {
      this.onEvent?.({ type: 'failed', item });
    }
    void this.pump();
  }

  private deleteFiles(item: DownloadItem) {
    try {
      const dir = new Directory(Paths.document, 'downloads', item.id);
      if (dir.exists) dir.delete();
    } catch {
      /* already gone */
    }
    item.fileExists = false;
  }
}

export const downloadManager = new DownloadManager();
