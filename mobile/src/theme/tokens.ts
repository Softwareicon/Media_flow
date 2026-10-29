/** Design tokens. Every colour used in the app comes from here so both themes stay in sync. */
export type ThemeName = 'light' | 'dark';

export interface Palette {
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  textFaint: string;
  accent: string;
  accentText: string;
  gradient: readonly [string, string, string];
  success: string;
  warning: string;
  danger: string;
  info: string;
  successBg: string;
  warningBg: string;
  dangerBg: string;
  infoBg: string;
  overlay: string;
  skeleton: string;
}

const dark: Palette = {
  bg: '#0B0D12',
  surface: '#141821',
  surfaceAlt: '#1C2130',
  border: '#262C3B',
  text: '#F3F5FA',
  textMuted: '#A3ABBE',
  textFaint: '#6B7387',
  accent: '#8B7BFF',
  accentText: '#FFFFFF',
  gradient: ['#7C5CFF', '#4F7BFF', '#22D3EE'],
  success: '#34D399',
  warning: '#FBBF24',
  danger: '#F87171',
  info: '#60A5FA',
  successBg: 'rgba(52,211,153,0.14)',
  warningBg: 'rgba(251,191,36,0.14)',
  dangerBg: 'rgba(248,113,113,0.14)',
  infoBg: 'rgba(96,165,250,0.14)',
  overlay: 'rgba(5,7,12,0.72)',
  skeleton: '#1F2433',
};

const light: Palette = {
  bg: '#F5F6FA',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF0F6',
  border: '#E1E4EE',
  text: '#0E1220',
  textMuted: '#4C5468',
  textFaint: '#8A92A6',
  accent: '#5B3DF5',
  accentText: '#FFFFFF',
  gradient: ['#6A4BFF', '#3D6BFF', '#0EB5D6'],
  success: '#059669',
  warning: '#B45309',
  danger: '#DC2626',
  info: '#2563EB',
  successBg: 'rgba(5,150,105,0.10)',
  warningBg: 'rgba(180,83,9,0.10)',
  dangerBg: 'rgba(220,38,38,0.10)',
  infoBg: 'rgba(37,99,235,0.10)',
  overlay: 'rgba(14,18,32,0.55)',
  skeleton: '#E6E9F2',
};

export const palettes: Record<ThemeName, Palette> = { dark, light };

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 10, md: 14, lg: 20, xl: 28, pill: 999 } as const;
export const type = {
  display: { fontSize: 30, fontWeight: '800' as const, letterSpacing: -0.6 },
  title: { fontSize: 22, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 17, fontWeight: '700' as const },
  body: { fontSize: 15, fontWeight: '400' as const, lineHeight: 21 },
  bodyStrong: { fontSize: 15, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '500' as const },
  micro: { fontSize: 11, fontWeight: '700' as const, letterSpacing: 0.6 },
};
/** Minimum touch target (Apple HIG 44pt, Material 48dp). */
export const HIT = 48;
