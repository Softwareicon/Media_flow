import { useEffect, useSyncExternalStore } from 'react';

import { useSettings } from '@/settings/SettingsProvider';
import { downloadManager } from './DownloadManager';

export function useDownloads() {
  return useSyncExternalStore(downloadManager.subscribe, downloadManager.getSnapshot, downloadManager.getSnapshot);
}

/** Keeps the manager's config in sync with user settings. Mounted once at the root. */
export function useDownloadManagerSync() {
  const { settings, ready } = useSettings();
  useEffect(() => {
    if (!ready) return;
    downloadManager.configure({
      maxConcurrent: settings.maxConcurrent, wifiOnly: settings.wifiOnly, saveTarget: settings.saveTarget,
      folderUri: settings.folderUri,
    });
    void downloadManager.init();
  }, [ready, settings.maxConcurrent, settings.wifiOnly, settings.saveTarget, settings.folderUri]);
}
