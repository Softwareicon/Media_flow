import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { kvGet, kvSet } from '@/db/database';

export type SaveTarget = 'library' | 'app' | 'folder';

export interface Settings {
  theme: 'system' | 'light' | 'dark';
  maxConcurrent: number; // 1..5
  saveTarget: SaveTarget; // where finished files go
  folderUri: string | null; // Android SAF directory picked by the user
  wifiOnly: boolean;
  preferHighest: boolean; // pre-select the best available option
  keepHistory: boolean; // local history on this device
  haptics: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: 'system',
  maxConcurrent: 2,
  saveTarget: 'library',
  folderUri: null,
  wifiOnly: false,
  preferHighest: true,
  keepHistory: true,
  haptics: true,
};

interface Ctx {
  settings: Settings;
  ready: boolean;
  update: (patch: Partial<Settings>) => void;
}

const SettingsCtx = createContext<Ctx | null>(null);
const KEY = 'settings.v1';

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    kvGet(KEY)
      .then((raw) => {
        if (raw) setSettings({ ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) });
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      next.maxConcurrent = Math.min(5, Math.max(1, Math.round(next.maxConcurrent)));
      kvSet(KEY, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ settings, ready, update }), [settings, ready, update]);
  return <SettingsCtx.Provider value={value}>{children}</SettingsCtx.Provider>;
}

export function useSettings(): Ctx {
  const c = useContext(SettingsCtx);
  if (!c) throw new Error('useSettings outside SettingsProvider');
  return c;
}
