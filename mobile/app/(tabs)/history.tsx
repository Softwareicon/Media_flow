import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { Alert, FlatList, Pressable, Text, View } from 'react-native';

import { PLATFORM_ICON } from '@/components/media';
import { Badge, Button, EmptyState, IconButton, Screen, SearchField, Title, type Tone } from '@/components/ui';
import { clearHistory, deleteHistoryItem, type HistoryRow, listHistory } from '@/db/database';
import { relativeTime } from '@/lib/format';
import { useSettings } from '@/settings/SettingsProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space, type } from '@/theme/tokens';

const STATUS: Record<string, [string, Tone]> = {
  downloadable: ['Downloadable', 'success'], link_only: ['Link only', 'info'], needs_connection: ['Connect account', 'accent'],
  not_configured: ['Unavailable', 'warning'], unavailable: ['Unavailable', 'danger'], export_only: ['Export only', 'info'],
};

/** Links you've analyzed. Stored only on this device; can be turned off in Settings. */
export default function History() {
  const { c } = useTheme();
  const router = useRouter();
  const { settings } = useSettings();
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [q, setQ] = useState('');

  const load = useCallback(() => {
    listHistory(q.trim()).then(setRows).catch(() => setRows([]));
  }, [q]);
  useFocusEffect(load);

  const clearAll = () => Alert.alert('Clear history?', 'Removes all analyzed links from this device. Downloads are not affected.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Clear', style: 'destructive', onPress: () => clearHistory().then(load) },
  ]);

  return (
    <Screen scroll={false}>
      <Title sub={settings.keepHistory ? 'Stored only on this device' : 'History is turned off in Settings'}>History</Title>
      <View style={{ marginBottom: space.md }}>
        <SearchField placeholder="Search links" value={q} onChangeText={setQ} onSubmitEditing={load} onEndEditing={load} />
      </View>
      <FlatList data={rows} keyExtractor={(r) => String(r.id)} contentContainerStyle={{ gap: space.sm, paddingBottom: space.xxl }}
        renderItem={({ item }) => {
          const [label, tone] = STATUS[item.status] ?? ['Checked', 'neutral' as Tone];
          return (
            <Pressable onPress={() => router.push({ pathname: '/', params: { url: item.source_url } })} accessibilityRole="button"
              accessibilityLabel={`Analyze again: ${item.title ?? item.source_url}`}
              style={({ pressed }) => ({ flexDirection: 'row', gap: space.md, alignItems: 'center', padding: space.md, borderRadius: radius.md,
                backgroundColor: pressed ? c.surfaceAlt : c.surface })}>
              <View style={{ width: 52, height: 52, borderRadius: radius.sm, overflow: 'hidden', backgroundColor: c.surfaceAlt, alignItems: 'center', justifyContent: 'center' }}>
                {item.thumbnail_url ? <Image source={{ uri: item.thumbnail_url }} style={{ width: 52, height: 52 }} cachePolicy="disk" />
                  : <Ionicons name={PLATFORM_ICON[item.platform] ?? 'link'} size={22} color={c.textFaint} />}
              </View>
              <View style={{ flex: 1, gap: 4 }}>
                <Text numberOfLines={1} style={[type.bodyStrong, { color: c.text }]}>{item.title || item.source_url}</Text>
                <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
                  <Badge label={label} tone={tone} />
                  <Text style={[type.caption, { color: c.textFaint }]}>{item.platform_name} · {relativeTime(item.created_at)}</Text>
                </View>
              </View>
              <IconButton icon="close" label="Remove from history" onPress={() => deleteHistoryItem(item.id).then(load)} />
            </Pressable>
          );
        }}
        ListEmptyComponent={<EmptyState icon="time-outline" title={q ? 'No matches' : 'No history yet'} body="Links you analyze show up here so you can come back to them." />}
        ListFooterComponent={rows.length ? <Button label="Clear history" variant="ghost" icon="trash-outline" onPress={clearAll} /> : undefined}
      />
    </Screen>
  );
}
