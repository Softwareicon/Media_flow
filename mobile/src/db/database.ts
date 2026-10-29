/**
 * Local SQLite store: settings, download records and link history.
 * Everything here works offline and never leaves the device.
 */
import * as SQLite from 'expo-sqlite';

import type { DownloadStatus } from '@/downloads/logic';

let dbPromise: Promise<SQLite.SQLiteDatabase> | null = null;

const MIGRATIONS: string[] = [
  `CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS downloads (
     id TEXT PRIMARY KEY NOT NULL,
     server_id TEXT,
     analysis_id TEXT,
     option_id TEXT NOT NULL,
     option_key TEXT NOT NULL,
     source_url TEXT NOT NULL,
     platform TEXT NOT NULL,
     platform_name TEXT NOT NULL,
     title TEXT,
     author TEXT,
     thumbnail_url TEXT,
     kind TEXT NOT NULL,
     mime_type TEXT NOT NULL,
     extension TEXT NOT NULL,
     quality_label TEXT,
     width INTEGER, height INTEGER, duration REAL,
     file_name TEXT NOT NULL,
     file_uri TEXT,
     saved_location TEXT,
     asset_id TEXT,
     expected_bytes INTEGER,
     received_bytes INTEGER NOT NULL DEFAULT 0,
     status TEXT NOT NULL,
     error_code TEXT,
     attempts INTEGER NOT NULL DEFAULT 0,
     resume_state TEXT,
     created_at INTEGER NOT NULL,
     updated_at INTEGER NOT NULL,
     completed_at INTEGER
   );
   CREATE INDEX IF NOT EXISTS ix_downloads_status ON downloads(status);
   CREATE INDEX IF NOT EXISTS ix_downloads_created ON downloads(created_at);
   CREATE TABLE IF NOT EXISTS link_history (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     source_url TEXT NOT NULL,
     platform TEXT NOT NULL,
     platform_name TEXT NOT NULL,
     title TEXT,
     thumbnail_url TEXT,
     status TEXT NOT NULL,
     created_at INTEGER NOT NULL
   );
   CREATE INDEX IF NOT EXISTS ix_history_created ON link_history(created_at);`,
];

export function db(): Promise<SQLite.SQLiteDatabase> {
  dbPromise ??= (async () => {
    const d = await SQLite.openDatabaseAsync('mediaflow.db');
    await d.execAsync('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
    const row = await d.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
    const current = row?.user_version ?? 0;
    for (let v = current; v < MIGRATIONS.length; v += 1) {
      await d.withTransactionAsync(async () => {
        await d.execAsync(MIGRATIONS[v]!);
        await d.execAsync(`PRAGMA user_version = ${v + 1}`);
      });
    }
    return d;
  })();
  return dbPromise;
}

export async function kvGet(key: string): Promise<string | null> {
  const r = await (await db()).getFirstAsync<{ value: string }>('SELECT value FROM kv WHERE key = ?', key);
  return r?.value ?? null;
}

export async function kvSet(key: string, value: string): Promise<void> {
  await (await db()).runAsync('INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', key, value);
}

export interface DownloadRow {
  id: string;
  server_id: string | null;
  analysis_id: string | null;
  option_id: string;
  option_key: string;
  source_url: string;
  platform: string;
  platform_name: string;
  title: string | null;
  author: string | null;
  thumbnail_url: string | null;
  kind: 'video' | 'image' | 'audio';
  mime_type: string;
  extension: string;
  quality_label: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  file_name: string;
  file_uri: string | null;
  saved_location: 'library' | 'app' | 'folder' | null;
  asset_id: string | null;
  expected_bytes: number | null;
  received_bytes: number;
  status: DownloadStatus;
  error_code: string | null;
  attempts: number;
  resume_state: string | null;
  created_at: number;
  updated_at: number;
  completed_at: number | null;
}

const COLS: Array<keyof DownloadRow> = [
  'id', 'server_id', 'analysis_id', 'option_id', 'option_key', 'source_url', 'platform', 'platform_name', 'title',
  'author', 'thumbnail_url', 'kind', 'mime_type', 'extension', 'quality_label', 'width', 'height', 'duration',
  'file_name', 'file_uri', 'saved_location', 'asset_id', 'expected_bytes', 'received_bytes', 'status', 'error_code',
  'attempts', 'resume_state', 'created_at', 'updated_at', 'completed_at',
];

export async function upsertDownload(r: DownloadRow): Promise<void> {
  const placeholders = COLS.map(() => '?').join(',');
  const updates = COLS.filter((c) => c !== 'id').map((c) => `${c} = excluded.${c}`).join(',');
  await (await db()).runAsync(
    `INSERT INTO downloads(${COLS.join(',')}) VALUES(${placeholders}) ON CONFLICT(id) DO UPDATE SET ${updates}`,
    COLS.map((c) => (r[c] ?? null) as string | number | null),
  );
}

export async function allDownloads(): Promise<DownloadRow[]> {
  return (await db()).getAllAsync<DownloadRow>('SELECT * FROM downloads ORDER BY created_at DESC');
}

export async function deleteDownloadRow(id: string): Promise<void> {
  await (await db()).runAsync('DELETE FROM downloads WHERE id = ?', id);
}

export interface HistoryRow {
  id: number;
  source_url: string;
  platform: string;
  platform_name: string;
  title: string | null;
  thumbnail_url: string | null;
  status: string;
  created_at: number;
}

export async function addHistory(h: Omit<HistoryRow, 'id' | 'created_at'>): Promise<void> {
  const d = await db();
  await d.runAsync('DELETE FROM link_history WHERE source_url = ?', h.source_url); // keep latest only
  await d.runAsync(
    'INSERT INTO link_history(source_url, platform, platform_name, title, thumbnail_url, status, created_at) VALUES(?,?,?,?,?,?,?)',
    h.source_url, h.platform, h.platform_name, h.title, h.thumbnail_url, h.status, Date.now(),
  );
  await d.runAsync('DELETE FROM link_history WHERE id NOT IN (SELECT id FROM link_history ORDER BY created_at DESC LIMIT 500)');
}

export async function listHistory(search = ''): Promise<HistoryRow[]> {
  const like = `%${search.replace(/[%_\\]/g, (m) => `\\${m}`)}%`;
  return (await db()).getAllAsync<HistoryRow>(
    "SELECT * FROM link_history WHERE (title LIKE ? ESCAPE '\\' OR source_url LIKE ? ESCAPE '\\') ORDER BY created_at DESC LIMIT 500",
    like, like,
  );
}

export async function deleteHistoryItem(id: number): Promise<void> {
  await (await db()).runAsync('DELETE FROM link_history WHERE id = ?', id);
}

export async function clearHistory(): Promise<void> {
  await (await db()).runAsync('DELETE FROM link_history');
}
