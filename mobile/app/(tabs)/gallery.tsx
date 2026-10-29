import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, Text, useWindowDimensions, View } from 'react-native';

import { Badge, EmptyState, Screen, SearchField, Segmented, Title } from '@/components/ui';
import type { DownloadItem } from '@/downloads/DownloadManager';
import { useDownloads } from '@/downloads/useDownloads';
import { formatDuration } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/tokens';

type Kind = 'all' | 'video' | 'image' | 'audio';

/** Works fully offline: everything here is read from files on this device. */
export default function Gallery() {
  const { c, columns, maxWidth } = useTheme();
  const { width } = useWindowDimensions();
  const router = useRouter();
  const items = useDownloads();
  const [q, setQ] = useState('');
  const [kind, setKind] = useState<Kind>('all');
  const files = useMemo(() => {
    const n = q.trim().toLowerCase();
    return items.filter((i) => i.status === 'completed' && i.fileExists && (kind === 'all' || i.kind === kind) &&
      (!n || [i.title, i.file_name, i.platform_name].some((s) => s?.toLowerCase().includes(n))));
  }, [items, q, kind]);
  const gap = 8;
  const tile = (Math.min(width, maxWidth) - space.lg * 2 - gap * (columns - 1)) / columns;

  const renderTile = ({ item }: { item: DownloadItem }) => (
    <Pressable onPress={() => router.push(`/player/${item.id}`)} accessibilityRole="button"
      accessibilityLabel={`${item.kind} ${item.title ?? item.file_name}`}
      style={({ pressed }) => ({ width: tile, height: tile, borderRadius: radius.md, overflow: 'hidden', backgroundColor: c.surfaceAlt,
        opacity: pressed ? 0.8 : 1 })}>
      {item.kind === 'image' && item.file_uri ? (
        <Image source={{ uri: item.file_uri }} style={{ flex: 1 }} contentFit="cover" recyclingKey={item.id} />
      ) : item.thumbnail_url ? (
        <Image source={{ uri: item.thumbnail_url }} style={{ flex: 1 }} contentFit="cover" cachePolicy="disk" recyclingKey={item.id} />
      ) : (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={item.kind === 'audio' ? 'musical-notes' : 'film'} size={28} color={c.textFaint} />
        </View>
      )}
      {item.kind !== 'image' ? (
        <View style={{ position: 'absolute', left: 6, bottom: 6, flexDirection: 'row', alignItems: 'center', gap: 4,
          backgroundColor: c.overlay, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
          <Ionicons name={item.kind === 'audio' ? 'musical-note' : 'play'} size={11} color="#fff" />
          {formatDuration(item.duration) ? <Text style={{ color: '#fff', fontSize: 11, fontWeight: '600' }}>{formatDuration(item.duration)}</Text> : null}
        </View>
      ) : null}
    </Pressable>
  );

  return (
    <Screen scroll={false}>
      <Title sub={`${files.length} file${files.length === 1 ? '' : 's'} on this device · available offline`}>Gallery</Title>
      <View style={{ gap: space.md, marginBottom: space.md }}>
        <SearchField placeholder="Search your files" value={q} onChangeText={setQ} />
        <Segmented label="Media type" value={kind} onChange={setKind} options={[
          { value: 'all', label: 'All' }, { value: 'video', label: 'Videos' }, { value: 'image', label: 'Photos' }, { value: 'audio', label: 'Audio' },
        ]} />
      </View>
      <FlatList key={columns} data={files} numColumns={columns} keyExtractor={(i) => i.id} renderItem={renderTile}
        columnWrapperStyle={{ gap }} contentContainerStyle={{ gap, paddingBottom: space.xxl }}
        ListEmptyComponent={<EmptyState icon="images-outline" title={q ? 'No matches' : 'Your gallery is empty'}
          body={q ? 'Try another search.' : 'Finished downloads appear here and can be viewed without a connection.'} />}
        ListHeaderComponent={files.some((f) => f.saved_location === 'library') ? (
          <View style={{ marginBottom: space.sm }}><Badge label="Also saved to Photos" icon="images" tone="success" /></View>) : undefined}
      />
    </Screen>
  );
}
