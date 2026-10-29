import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import React from 'react';
import type { ColorValue } from 'react-native';

import { useDownloads } from '@/downloads/useDownloads';
import { useTheme } from '@/theme/ThemeProvider';

type IconName = React.ComponentProps<typeof Ionicons>['name'];
const icon = (on: IconName, off: IconName) => ({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) =>
  <Ionicons name={focused ? on : off} size={size} color={color as string} />;

export default function TabsLayout() {
  const { c } = useTheme();
  const items = useDownloads();
  const active = items.filter((i) => !['completed', 'failed', 'cancelled'].includes(i.status)).length;
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: c.accent,
      tabBarInactiveTintColor: c.textFaint,
      tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
      tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
    }}>
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: icon('home', 'home-outline') }} />
      <Tabs.Screen name="downloads" options={{ title: 'Downloads', tabBarIcon: icon('arrow-down-circle', 'arrow-down-circle-outline'),
        tabBarBadge: active || undefined, tabBarBadgeStyle: { backgroundColor: c.accent } }} />
      <Tabs.Screen name="gallery" options={{ title: 'Gallery', tabBarIcon: icon('images', 'images-outline') }} />
      <Tabs.Screen name="history" options={{ title: 'History', tabBarIcon: icon('time', 'time-outline') }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings', tabBarIcon: icon('settings', 'settings-outline') }} />
    </Tabs>
  );
}
