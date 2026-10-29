import { Stack, useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import * as SystemUI from 'expo-system-ui';
import React, { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ToastProvider, useToast } from '@/components/Toast';
import { downloadManager } from '@/downloads/DownloadManager';
import { ERROR_TEXT, type ErrorCode } from '@/downloads/logic';
import { useDownloadManagerSync } from '@/downloads/useDownloads';
import { SettingsProvider, useSettings } from '@/settings/SettingsProvider';
import { ThemeProvider, useTheme } from '@/theme/ThemeProvider';

SplashScreen.preventAutoHideAsync().catch(() => undefined);

function Root() {
  const { c, name } = useTheme();
  const { ready } = useSettings();
  const toast = useToast();
  const router = useRouter();
  useDownloadManagerSync();

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(c.bg).catch(() => undefined);
  }, [c.bg]);
  useEffect(() => {
    downloadManager.onEvent = ({ type, item }) => {
      if (type === 'completed') {
        toast('success', `Saved “${item.title ?? item.file_name}”`, { label: 'Open', onPress: () => router.push(`/player/${item.id}`) });
      } else {
        toast('error', ERROR_TEXT[(item.error_code ?? 'unknown') as ErrorCode] ?? ERROR_TEXT.unknown,
          { label: 'View', onPress: () => router.push('/downloads') });
      }
    };
    return () => {
      downloadManager.onEvent = null;
    };
  }, [toast, router]);

  return (
    <>
      <StatusBar style={name === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerStyle: { backgroundColor: c.bg }, headerTintColor: c.text, headerShadowVisible: false,
        contentStyle: { backgroundColor: c.bg }, headerTitleStyle: { fontWeight: '700' } }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="player/[id]" options={{ title: '', presentation: 'fullScreenModal', headerTransparent: true }} />
        <Stack.Screen name="platforms" options={{ title: 'Supported platforms' }} />
        <Stack.Screen name="account" options={{ title: 'Account', presentation: 'modal' }} />
      </Stack>
    </>
  );
}

export default function Layout() {
  return (
    <SafeAreaProvider>
      <SettingsProvider>
        <ThemeProvider>
          <ToastProvider>
            <Root />
          </ToastProvider>
        </ThemeProvider>
      </SettingsProvider>
    </SafeAreaProvider>
  );
}
