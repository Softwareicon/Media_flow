import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useVideoPlayer, VideoView } from 'expo-video';
import React from 'react';
import { Alert, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useToast } from '@/components/Toast';
import { EmptyState, IconButton } from '@/components/ui';
import { downloadManager, type DownloadItem } from '@/downloads/DownloadManager';
import { useDownloads } from '@/downloads/useDownloads';
import { formatBytes } from '@/lib/format';
import { shareFile } from '@/lib/share';
import { space, type } from '@/theme/tokens';

function VideoPane({ uri }: { uri: string }) {
  const player = useVideoPlayer({ uri }, (p) => {
    p.loop = false;
    p.play();
  });
  return <VideoView player={player} style={{ flex: 1 }} contentFit="contain" nativeControls fullscreenOptions={{ enable: true }} allowsPictureInPicture />;
}

/** Plays/views a downloaded file from local storage — works offline. */
export default function Player() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const items = useDownloads();
  const item: DownloadItem | undefined = items.find((i) => i.id === id);
  const router = useRouter();
  const toast = useToast();

  if (!item || !item.file_uri || !item.fileExists) {
    return <SafeAreaView style={{ flex: 1, backgroundColor: '#000' }}><EmptyState icon="alert-circle-outline" title="File not found" body="It may have been deleted." /></SafeAreaView>;
  }
  const remove = () => Alert.alert('Delete this file?', item.saved_location === 'library' ? 'The copy in your photo library stays.' : 'It will be removed from this device.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Delete', style: 'destructive', onPress: async () => { await downloadManager.remove(item.id); router.back(); } },
  ]);
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: '#000' }} edges={['bottom']}>
      <View style={{ flex: 1 }}>
        {item.kind === 'image' ? (
          <Image source={{ uri: item.file_uri }} style={{ flex: 1 }} contentFit="contain" accessibilityLabel={item.title ?? 'Downloaded image'} />
        ) : item.kind === 'video' || item.kind === 'audio' ? (
          <VideoPane uri={item.file_uri} />
        ) : null}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, paddingTop: space.md, gap: space.sm }}>
        <View style={{ flex: 1 }}>
          <Text numberOfLines={1} style={[type.bodyStrong, { color: '#fff' }]}>{item.title ?? item.file_name}</Text>
          <Text style={[type.caption, { color: '#B8BED0' }]}>{[item.platform_name, item.quality_label, formatBytes(item.received_bytes)].filter(Boolean).join(' · ')}</Text>
        </View>
        <IconButton icon="share-outline" label="Share" tone="#fff" onPress={async () => {
          if (!(await shareFile(item.file_uri!, item.mime_type, item.title))) toast('error', 'Sharing isn’t available on this device.');
        }} />
        <IconButton icon="trash-outline" label="Delete" tone="#fff" onPress={remove} />
        <IconButton icon="close" label="Close" tone="#fff" onPress={() => router.back()} />
      </View>
      <View style={{ height: space.sm }} />
    </SafeAreaView>
  );
}
