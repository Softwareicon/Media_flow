import React, { createContext, useContext, useMemo } from 'react';
import { useColorScheme, useWindowDimensions } from 'react-native';

import { useSettings } from '@/settings/SettingsProvider';
import { type Palette, palettes, type ThemeName } from './tokens';

interface Theme {
  name: ThemeName;
  c: Palette;
  /** true on tablets / large windows: screens switch to wider, multi-column layouts */
  wide: boolean;
  /** content max width so text lines stay readable on tablets */
  maxWidth: number;
  columns: number;
}

const Ctx = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const { settings } = useSettings();
  const { width } = useWindowDimensions();
  const name: ThemeName = settings.theme === 'system' ? (system === 'light' ? 'light' : 'dark') : settings.theme;
  const value = useMemo<Theme>(() => {
    const wide = width >= 700;
    return { name, c: palettes[name], wide, maxWidth: wide ? 760 : width, columns: width >= 1000 ? 5 : wide ? 4 : 3 };
  }, [name, width]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): Theme {
  const t = useContext(Ctx);
  if (!t) throw new Error('useTheme outside ThemeProvider');
  return t;
}
