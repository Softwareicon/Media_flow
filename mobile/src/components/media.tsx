import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import React from 'react';
import { Pressable, Text, View } from 'react-native';

import { connectPlatform } from '@/api/connect';
import type { Analysis, MediaOption } from '@/api/types';
import { type DownloadItem } from '@/downloads/DownloadManager';
import { ERROR_TEXT, type ErrorCode } from '@/downloads/logic';
import { formatBytes, formatDuration, formatEta, formatPercent, formatSpeed } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space, type } from '@/theme/tokens';
import { Badge, Button, Card, IconButton, ProgressBar, Skeleton, type Tone } from './ui';

export const PLATFORM_ICON: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  youtube: 'logo-youtube', instagram: 'logo-instagram', facebook: 'logo-facebook', tiktok: 'logo-tiktok', x: 'logo-twitter',
  pinterest: 'logo-pinterest', reddit: 'logo-reddit', vimeo: 'logo-vimeo', dating: 'heart', web: 'globe-outline',
};

export function MediaPreviewCard({ a }: { a: Analysis }) {
  const { c, wide } = useTheme();
  const dur = formatDuration(a.duration_seconds);
  return (
    <Card padded={false}>
      <View style={{ flexDirection: wide ? 'row' : 'column' }}>
        <View style={{ width: wide ? 280 : '100%', aspectRatio: 16 / 9, backgroundColor: c.surfaceAlt }}>
          {a.thumbnail_url ? (
            <Image source={{ uri: a.thumbnail_url }} style={{ flex: 1 }} contentFit="cover" transition={200} cachePolicy="disk"
              accessibilityLabel={a.title ? `Preview of ${a.title}` : 'Media preview'} />
          ) : (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={a.media_type === 'image' || a.media_type === 'gallery' ? 'image-outline' : 'film-outline'} size={44} color={c.textFaint} />
            </View>
          )}
          {dur ? (
            <View style={{ position: 'absolute', right: 10, bottom: 10, backgroundColor: c.overlay, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={[type.caption, { color: '#fff' }]}>{dur}</Text>
            </View>
          ) : null}
        </View>
        <View style={{ padding: space.lg, gap: 8, flex: 1 }}>
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            <Badge label={a.platform_name} icon={PLATFORM_ICON[a.platform]} tone="accent" />
            {a.media_type !== 'unknown' ? <Badge label={a.media_type} /> : null}
          </View>
          <Text style={[type.heading, { color: c.text }]} numberOfLines={3}>{a.title || 'Untitled'}</Text>
          {a.author ? <Text style={[type.caption, { color: c.textMuted }]}>{a.author}</Text> : null}
        </View>
      </View>
    </Card>
  );
}

export function PreviewSkeleton() {
  return (
    <Card padded={false}>
      <Skeleton height={190} style={{ borderRadius: 0 }} />
      <View style={{ padding: space.lg, gap: 10 }}>
        <Skeleton width={110} height={20} />
        <Skeleton height={20} />
        <Skeleton width="60%" height={14} />
      </View>
    </Card>
  );
}

function optionDetail(o: MediaOption): string {
  const parts: string[] = [];
  if (o.width && o.height) parts.push(`${o.width}×${o.height}`);
  if (o.size_bytes) parts.push(`${o.size_is_estimate ? '≈ ' : ''}${formatBytes(o.size_bytes)}`);
  else parts.push('size unknown');
  if (o.kind === 'video' && o.has_audio === false) parts.push('no audio');
  return parts.join(' · ');
}

export function QualitySelector({ options, value, onChange }: { options: MediaOption[]; value: string | null; onChange: (id: string) => void }) {
  const { c } = useTheme();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel="Quality" style={{ gap: 8 }}>
      {options.map((o) => {
        const on = o.id === value;
        return (
          <Pressable key={o.id} onPress={() => onChange(o.id)} accessibilityRole="radio" accessibilityState={{ selected: on }}
            accessibilityLabel={`${o.label}. ${optionDetail(o)}${o.note ? `. ${o.note}` : ''}`}
            style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md, minHeight: 60, borderRadius: radius.md,
              borderWidth: on ? 2 : 1, borderColor: on ? c.accent : c.border, backgroundColor: on ? c.infoBg : c.surface }}>
            <Ionicons name={on ? 'radio-button-on' : 'radio-button-off'} size={22} color={on ? c.accent : c.textFaint} />
            <View style={{ flex: 1, gap: 2 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Text style={[type.bodyStrong, { color: c.text }]}>{o.label}</Text>
                {o.is_original ? <Badge label="Original" tone="success" /> : null}
              </View>
              <Text style={[type.caption, { color: c.textMuted }]}>{optionDetail(o)}</Text>
              {o.note ? <Text style={[type.caption, { color: c.textFaint }]}>{o.note}</Text> : null}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const STATUS_COPY: Record<string, { title: string; tone: Tone; icon: React.ComponentProps<typeof Ionicons>['name'] }> = {
  link_only: { title: 'Download not offered by this platform', tone: 'info', icon: 'open-outline' },
  needs_connection: { title: 'Connect your account to continue', tone: 'accent', icon: 'link-outline' },
  not_configured: { title: 'Not available on this server', tone: 'warning', icon: 'construct-outline' },
  export_only: { title: 'Only available through the platform’s data export', tone: 'info', icon: 'archive-outline' },
  unavailable: { title: 'Can’t download this link', tone: 'danger', icon: 'alert-circle-outline' },
};

/** For every non-downloadable result: why, the official link, and authorized alternatives. */
export function NotDownloadablePanel({ a, onConnected }: { a: Analysis; onConnected: () => void }) {
  const { c } = useTheme();
  const meta = STATUS_COPY[a.status] ?? STATUS_COPY.unavailable!;
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const connect = async () => {
    setBusy(true);
    setErr(null);
    try {
      const outcome = await connectPlatform(a.platform);
      if (outcome === 'connected') onConnected();
      else if (outcome === 'denied') setErr('Connection was cancelled.');
      else if (outcome === 'failed') setErr('Connection failed. Try again.');
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card style={{ gap: space.md }}>
      <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'flex-start' }}>
        <Ionicons name={meta.icon} size={24} color={c.accent} />
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={[type.heading, { color: c.text }]}>{meta.title}</Text>
          {a.explanation ? <Text style={[type.body, { color: c.textMuted }]}>{a.explanation}</Text> : null}
        </View>
      </View>
      {a.status === 'needs_connection' ? (
        <Button label={`Connect ${a.platform_name}`} icon="link" onPress={connect} loading={busy} />
      ) : null}
      {err ? <Text style={[type.caption, { color: c.danger }]}>{err}</Text> : null}
      {a.official_url ? (
        <Button label={`Open in ${a.platform === 'web' ? 'browser' : a.platform_name}`} icon="open-outline" variant="secondary"
          onPress={() => Linking.openURL(a.official_url!)} accessibilityHint="Opens the original post in the official app or website" />
      ) : null}
      {a.alternatives.length ? (
        <View style={{ gap: space.sm, marginTop: 4 }}>
          <Text style={[type.micro, { color: c.textFaint }]}>OFFICIAL OPTIONS</Text>
          {a.alternatives.map((alt) => (
            <Pressable key={alt.label} disabled={!alt.url} onPress={() => alt.url && WebBrowser.openBrowserAsync(alt.url)}
              accessibilityRole={alt.url ? 'link' : 'text'}
              style={{ padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceAlt, gap: 2, minHeight: 48 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text style={[type.bodyStrong, { color: c.text, flex: 1 }]}>{alt.label}</Text>
                {alt.url ? <Ionicons name="open-outline" size={16} color={c.accent} /> : null}
              </View>
              <Text style={[type.caption, { color: c.textMuted }]}>{alt.description}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

const STATUS_LABEL: Record<DownloadItem['status'], [string, Tone]> = {
  queued: ['Queued', 'neutral'], authorizing: ['Starting', 'info'], downloading: ['Downloading', 'accent'],
  paused: ['Paused', 'warning'], verifying: ['Checking file', 'info'], saving: ['Saving', 'info'],
  completed: ['Done', 'success'], failed: ['Failed', 'danger'], cancelled: ['Cancelled', 'neutral'],
};

export function DownloadCard({ item, onPause, onResume, onCancel, onRetry, onOpen, onShare, onDelete }: {
  item: DownloadItem; onPause: () => void; onResume: () => void; onCancel: () => void; onRetry: () => void;
  onOpen: () => void; onShare: () => void; onDelete: () => void;
}) {
  const { c } = useTheme();
  const [label, tone] = STATUS_LABEL[item.status];
  const active = ['authorizing', 'downloading', 'verifying', 'saving'].includes(item.status);
  const progress = item.expected_bytes ? item.received_bytes / item.expected_bytes : null;
  const where = item.saved_location === 'library' ? 'Saved to Photos' : item.saved_location === 'folder' ? 'Saved to folder' : 'In app';
  return (
    <Card style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', gap: space.md }}>
        <View style={{ width: 64, height: 64, borderRadius: radius.sm, overflow: 'hidden', backgroundColor: c.surfaceAlt, alignItems: 'center', justifyContent: 'center' }}>
          {item.kind === 'image' && item.fileExists && item.file_uri ? (
            <Image source={{ uri: item.file_uri }} style={{ width: 64, height: 64 }} contentFit="cover" />
          ) : item.thumbnail_url ? (
            <Image source={{ uri: item.thumbnail_url }} style={{ width: 64, height: 64 }} contentFit="cover" cachePolicy="disk" />
          ) : (
            <Ionicons name={item.kind === 'video' ? 'film' : item.kind === 'audio' ? 'musical-notes' : 'image'} size={26} color={c.textFaint} />
          )}
        </View>
        <View style={{ flex: 1, gap: 4 }}>
          <Text numberOfLines={2} style={[type.bodyStrong, { color: c.text }]}>{item.title || item.file_name}</Text>
          <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <Badge label={label} tone={tone} />
            <Text style={[type.caption, { color: c.textMuted }]}>
              {[item.platform_name, item.quality_label, item.status === 'completed' ? formatBytes(item.received_bytes) : null].filter(Boolean).join(' · ')}
            </Text>
          </View>
        </View>
      </View>
      {active || item.status === 'paused' || item.status === 'queued' ? (
        <View style={{ gap: 6 }}>
          <ProgressBar value={progress} indeterminate={item.status === 'authorizing' || (item.status === 'downloading' && progress == null)} />
          <Text style={[type.caption, { color: c.textMuted }]}>
            {item.status === 'downloading'
              ? [formatBytes(item.received_bytes) + (item.expected_bytes ? ` of ${formatBytes(item.expected_bytes)}` : ''),
                formatPercent(item.received_bytes, item.expected_bytes), formatSpeed(item.speed), formatEta(item.eta)].filter((s) => s && s !== '—').join(' · ')
              : item.status === 'paused' ? `Paused at ${formatBytes(item.received_bytes)}` : item.status === 'queued' ? 'Waiting for a free slot' : label}
          </Text>
        </View>
      ) : null}
      {item.status === 'failed' && item.error_code ? (
        <Text style={[type.caption, { color: c.danger }]}>{ERROR_TEXT[item.error_code as ErrorCode] ?? ERROR_TEXT.unknown}</Text>
      ) : null}
      {item.status === 'completed' ? (
        <Text style={[type.caption, { color: c.textMuted }]}>{item.fileExists ? where : 'File removed from this device'}</Text>
      ) : null}
      <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginRight: -8 }}>
        {item.status === 'downloading' ? <IconButton icon="pause" label="Pause" onPress={onPause} /> : null}
        {item.status === 'paused' ? <IconButton icon="play" label="Resume" onPress={onResume} tone={c.accent} /> : null}
        {active || item.status === 'paused' || item.status === 'queued' ? <IconButton icon="close" label="Cancel" onPress={onCancel} /> : null}
        {item.status === 'failed' || item.status === 'cancelled' ? <IconButton icon="refresh" label="Retry" onPress={onRetry} tone={c.accent} /> : null}
        {item.status === 'completed' && item.fileExists ? <IconButton icon="eye-outline" label="Open" onPress={onOpen} tone={c.accent} /> : null}
        {item.status === 'completed' && item.fileExists ? <IconButton icon="share-outline" label="Share" onPress={onShare} /> : null}
        {!active ? <IconButton icon="trash-outline" label="Delete" onPress={onDelete} /> : null}
      </View>
    </Card>
  );
}
