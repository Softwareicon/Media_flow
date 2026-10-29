import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Alert, FlatList, Text, View } from 'react-native';

import { DownloadCard } from '@/components/media';
import { useToast } from '@/components/Toast';
import { Button, EmptyState, Screen, SearchField, Segmented, Title } from '@/components/ui';
import { downloadManager, type DownloadItem } from '@/downloads/DownloadManager';
import { useDownloads } from '@/downloads/useDownloads';
import { shareFile } from '@/lib/share';
import { useSettings } from '@/settings/SettingsProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { space, type } from '@/theme/tokens';

type Filter = 'active' | 'completed' | 'failed' | 'all';
type Sort = 'newest' | 'oldest' | 'largest' | 'name';

const isActive = (i: DownloadItem) => !['completed', 'failed', 'cancelled'].includes(i.status);

export default function Downloads() {
  const { c } = useTheme();
  const items = useDownloads();
  const router = useRouter();
  const toast = useToast();
  const { settings } = useSettings();
  const [filter, setFilter] = useState<Filter>('active');
  const [sort, setSort] = useState<Sort>('newest');
  const [q, setQ] = useState('');

  const counts = useMemo(() => ({
    active: items.filter(isActive).length,
    completed: items.filter((i) => i.status === 'completed').length,
    failed: items.filter((i) => i.status === 'failed' || i.status === 'cancelled').length,
  }), [items]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = items.filter((i) => (filter === 'all' ? true : filter === 'active' ? isActive(i)
      : filter === 'completed' ? i.status === 'completed' : i.status === 'failed' || i.status === 'cancelled'))
      .filter((i) => !needle || [i.title, i.file_name, i.platform_name, i.source_url].some((s) => s?.toLowerCase().includes(needle)));
    const by: Record<Sort, (a: DownloadItem, b: DownloadItem) => number> = {
      newest: (a, b) => b.created_at - a.created_at,
      oldest: (a, b) => a.created_at - b.created_at,
      largest: (a, b) => (b.received_bytes || b.expected_bytes || 0) - (a.received_bytes || a.expected_bytes || 0),
      name: (a, b) => (a.title ?? a.file_name).localeCompare(b.title ?? b.file_name),
    };
    return [...list].sort(by[sort]);
  }, [items, filter, sort, q]);

  const confirmDelete = (item: DownloadItem) => {
    Alert.alert('Delete download?', item.saved_location === 'library'
      ? 'This removes it from MediaFlow. The copy in your photo library stays.' : 'This deletes the file from this device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => downloadManager.remove(item.id) },
    ]);
  };

  return (
    <Screen scroll={false}>
      <Title sub={`${counts.active} active · up to ${settings.maxConcurrent} at once${settings.wifiOnly ? ' · Wi-Fi only' : ''}`}>Downloads</Title>
      <View style={{ gap: space.md, marginBottom: space.md }}>
        <Segmented label="Filter downloads" value={filter} onChange={setFilter} options={[
          { value: 'active', label: `Active${counts.active ? ` ${counts.active}` : ''}` },
          { value: 'completed', label: 'Done' },
          { value: 'failed', label: `Failed${counts.failed ? ` ${counts.failed}` : ''}` },
          { value: 'all', label: 'All' },
        ]} />
        <SearchField placeholder="Search downloads" value={q} onChangeText={setQ} />
        <Segmented label="Sort by" value={sort} onChange={setSort} options={[
          { value: 'newest', label: 'Newest' }, { value: 'oldest', label: 'Oldest' },
          { value: 'largest', label: 'Largest' }, { value: 'name', label: 'Name' },
        ]} />
      </View>
      <FlatList
        data={shown}
        keyExtractor={(i) => i.id}
        contentContainerStyle={{ gap: space.md, paddingBottom: space.xxl }}
        renderItem={({ item }) => (
          <DownloadCard item={item}
            onPause={() => downloadManager.pause(item.id)}
            onResume={() => downloadManager.resume(item.id)}
            onCancel={() => downloadManager.cancel(item.id)}
            onRetry={() => downloadManager.retry(item.id)}
            onOpen={() => router.push(`/player/${item.id}`)}
            onShare={async () => { if (item.file_uri && !(await shareFile(item.file_uri, item.mime_type, item.title))) toast('error', 'Sharing isn’t available on this device.'); }}
            onDelete={() => confirmDelete(item)} />
        )}
        ListEmptyComponent={
          <EmptyState icon={q ? 'search' : filter === 'failed' ? 'checkmark-done-outline' : 'cloud-download-outline'}
            title={q ? 'No matches' : filter === 'active' ? 'Nothing downloading' : filter === 'failed' ? 'No failed downloads' : 'No downloads yet'}
            body={q ? 'Try a different search.' : 'Paste a link on the Home tab to get started.'}
            action={!q && filter !== 'failed' ? <Button label="Go to Home" small variant="secondary" onPress={() => router.push('/')} /> : undefined} />
        }
        ListFooterComponent={filter === 'failed' && counts.failed ? (
          <Button label="Clear failed & cancelled" variant="ghost" icon="trash-outline" onPress={() => downloadManager.clearFinished()} />
        ) : filter === 'active' && counts.active ? (
          <Text style={[type.caption, { color: c.textFaint, textAlign: 'center', marginTop: space.sm }]}>
            Pause and resume work when the source server supports it. Downloads continue in the background where your phone allows.
          </Text>
        ) : undefined}
      />
    </Screen>
  );
}
