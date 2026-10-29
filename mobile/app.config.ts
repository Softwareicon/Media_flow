import type { ConfigContext, ExpoConfig } from 'expo/config';

/**
 * Lets each build point at its own backend without editing app.json:
 *   EXPO_PUBLIC_API_URL=https://api.example.com eas build ...
 * Only the PUBLIC API base URL lives in the app. No secrets are ever bundled.
 */
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...(config as ExpoConfig),
  extra: {
    ...config.extra,
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? config.extra?.apiUrl,
  },
});
