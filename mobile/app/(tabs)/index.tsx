import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { LinearGradient } from 'expo-linear-gradient';
import { useNetworkState } from 'expo-network';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api, ApiError } from '@/api/client';
import type { Analysis } from '@/api/types';
import { MediaPreviewCard, NotDownloadablePanel, PLATFORM_ICON, PreviewSkeleton, QualitySelector } from '@/components/media';
import { useToast } from '@/components/Toast';
import { Badge, Button, Card, Screen, SectionLabel, useTap } from '@/components/ui';
import { addHistory } from '@/db/database';
import { downloadManager } from '@/downloads/DownloadManager';
import { formatBytes } from '@/lib/format';
import { extractUrl, isValidHttpUrl, PLATFORM_LABELS, platformHint } from '@/lib/url';
import { useSettings } from '@/settings/SettingsProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { HIT, radius, space, type } from '@/theme/tokens';

type State = { kind: 'idle' } | { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'result'; a: Analysis };

export default function Home() {
  const { c } = useTheme();
  const { settings } = useSettings();
  const toast = useToast();
  const tap = useTap();
  const router = useRouter();
  const params = useLocalSearchParams<{ url?: string }>();
  const net = useNetworkState();
  const offline = net.isConnected === false || net.isInternetReachable === false;
  const [text, setText] = useState('');
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [choice, setChoice] = useState<string | null>(null);
  const [queueing, setQueueing] = useState(false);
  const inputRef = useRef<React.ComponentRef<typeof TextInput>>(null);

  const hint = platformHint(text);
  const valid = isValidHttpUrl(text);

  const analyze = useCallback(async (raw?: string) => {
    const url = extractUrl(raw ?? text);
    if (!url) return;
    inputRef.current?.blur();
    setState({ kind: 'loading' });
    setChoice(null);
    try {
      const a = await api.analyze(url);
      setState({ kind: 'result', a });
      const best = settings.preferHighest ? a.best_option_id : a.options[0]?.id;
      setChoice(best ?? a.options[0]?.id ?? null);
      if (settings.keepHistory) {
        addHistory({ source_url: a.source_url, platform: a.platform, platform_name: a.platform_name, title: a.title ?? null,
          thumbnail_url: a.thumbnail_url ?? null, status: a.status }).catch(() => undefined);
      }
    } catch (e) {
      setState({ kind: 'error', message: e instanceof ApiError ? e.message : 'Something went wrong. Try again.' });
    }
  }, [text, settings.preferHighest, settings.keepHistory]);

  useEffect(() => {
    if (params.url) {
      setText(params.url);
      void analyze(params.url);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.url]);

  const paste = async () => {
    tap();
    const clip = await Clipboard.getStringAsync().catch(() => '');
    const url = extractUrl(clip);
    if (url) {
      setText(url);
      void analyze(url);
    } else {
      toast('info', 'The clipboard doesn’t contain a link.');
    }
  };

  const enqueue = async (a: Analysis, ids: string[]) => {
    setQueueing(true);
    let added = 0;
    try {
      for (const id of ids) {
        const option = a.options.find((o) => o.id === id);
        if (!option) continue;
        let res = await downloadManager.enqueue(a, option);
        if (res.kind === 'duplicate' && ids.length === 1) {
          const again = await new Promise<boolean>((resolve) =>
            Alert.alert('Already downloaded', 'This file is already in your downloads at the same quality.', [
              { text: 'View', onPress: () => { resolve(false); router.push('/downloads'); } },
              { text: 'Download again', onPress: () => resolve(true) },
              { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
            ]));
          if (!again) return;
          res = await downloadManager.enqueue(a, option, true);
        }
        if (res.kind === 'no_space') {
          toast('error', `Not enough space: needs about ${formatBytes(res.needed)}, ${formatBytes(res.free)} free.`);
          return;
        }
        if (res.kind === 'queued') added += 1;
      }
      if (added) toast('success', added > 1 ? `${added} files added to downloads` : 'Added to downloads',
        { label: 'View', onPress: () => router.push('/downloads') });
    } finally {
      setQueueing(false);
    }
  };

  const a = state.kind === 'result' ? state.a : null;
  const selected = a?.options.find((o) => o.id === choice);
  const saveNote = settings.saveTarget === 'library' ? 'Saves to your photo library and stays available in Gallery.'
    : settings.saveTarget === 'folder' ? 'Saves to your chosen folder and stays available in Gallery.' : 'Saves inside MediaFlow (Gallery tab).';

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, paddingTop: space.lg, paddingBottom: space.xl }}>
          <LinearGradient colors={c.gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            style={{ width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="arrow-down" size={24} color="#fff" />
          </LinearGradient>
          <View>
            <Text accessibilityRole="header" style={[type.title, { color: c.text }]}>MediaFlow Pro</Text>
            <Text style={[type.caption, { color: c.textMuted }]}>Save media you’re allowed to keep</Text>
          </View>
        </View>

        {offline ? (
          <Card style={{ flexDirection: 'row', gap: space.md, alignItems: 'center', marginBottom: space.lg, backgroundColor: c.warningBg }}>
            <Ionicons name="cloud-offline-outline" size={22} color={c.warning} />
            <Text style={[type.caption, { color: c.text, flex: 1 }]}>You’re offline. Analyzing links needs internet — your saved files are still in Gallery.</Text>
          </Card>
        ) : null}

        <Card style={{ gap: space.md }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: c.surfaceAlt, borderRadius: radius.md,
            paddingLeft: space.lg, minHeight: 60, borderWidth: StyleSheet.hairlineWidth, borderColor: valid ? c.accent : c.border }}>
            <Ionicons name="link" size={20} color={c.textFaint} />
            <TextInput ref={inputRef} value={text} onChangeText={setText} placeholder="Paste a video or photo link"
              placeholderTextColor={c.textFaint} autoCapitalize="none" autoCorrect={false} keyboardType="url" returnKeyType="go"
              onSubmitEditing={() => valid && analyze()} accessibilityLabel="Media link"
              style={[type.body, { flex: 1, color: c.text, paddingVertical: 14 }]} />
            {text ? (
              <Pressable accessibilityRole="button" accessibilityLabel="Clear link" onPress={() => { setText(''); setState({ kind: 'idle' }); }}
                style={{ width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="close-circle" size={20} color={c.textFaint} />
              </Pressable>
            ) : (
              <Pressable accessibilityRole="button" accessibilityLabel="Paste link from clipboard" onPress={paste}
                style={{ height: HIT, paddingHorizontal: space.lg, alignItems: 'center', justifyContent: 'center' }}>
                <Text style={[type.bodyStrong, { color: c.accent }]}>Paste</Text>
              </Pressable>
            )}
          </View>
          {hint && text ? <Badge label={PLATFORM_LABELS[hint] ?? 'Website'} icon={PLATFORM_ICON[hint]} tone="accent" /> : null}
          <Button label="Analyze link" icon="sparkles" onPress={() => analyze()} disabled={!valid || offline}
            loading={state.kind === 'loading'} accessibilityHint="Checks the link and shows what you can save" />
        </Card>

        <View style={{ marginTop: space.xl, gap: space.lg }}>
          {state.kind === 'loading' ? <PreviewSkeleton /> : null}

          {state.kind === 'error' ? (
            <Card style={{ gap: space.md }}>
              <View style={{ flexDirection: 'row', gap: space.md }}>
                <Ionicons name="alert-circle" size={22} color={c.danger} />
                <Text style={[type.body, { color: c.text, flex: 1 }]}>{state.message}</Text>
              </View>
              <Button label="Try again" icon="refresh" variant="secondary" onPress={() => analyze()} />
            </Card>
          ) : null}

          {a ? <MediaPreviewCard a={a} /> : null}

          {a && a.status === 'downloadable' && a.options.length ? (
            <View style={{ gap: space.md }}>
              <SectionLabel>{a.options.length > 1 ? `Choose ${a.media_type === 'gallery' ? 'items' : 'quality'}` : 'Available file'}</SectionLabel>
              <QualitySelector options={a.options} value={choice} onChange={(id) => { tap(); setChoice(id); }} />
              <Button label={selected?.size_bytes ? `Download · ${selected.size_is_estimate ? '≈ ' : ''}${formatBytes(selected.size_bytes)}` : 'Download'}
                icon="arrow-down-circle" onPress={() => choice && enqueue(a, [choice])} disabled={!choice} loading={queueing} />
              {a.media_type === 'gallery' && a.options.length > 1 ? (
                <Button label={`Download all ${a.options.length}`} icon="albums-outline" variant="secondary"
                  onPress={() => enqueue(a, a.options.map((o) => o.id))} />
              ) : null}
              <Text style={[type.caption, { color: c.textFaint, textAlign: 'center' }]}>{saveNote}</Text>
            </View>
          ) : null}

          {a && a.status !== 'downloadable' ? <NotDownloadablePanel a={a} onConnected={() => { toast('success', 'Account connected'); void analyze(a.source_url); }} /> : null}

          {state.kind === 'idle' ? (
            <View style={{ gap: space.md }}>
              <SectionLabel>How it works</SectionLabel>
              {([
                ['clipboard-outline', 'Paste a link', 'From a website, or a platform account you’ve connected.'],
                ['shield-checkmark-outline', 'We check what’s allowed', 'Only qualities the source actually offers are shown — nothing is invented.'],
                ['download-outline', 'Save or open officially', 'Download when permitted; otherwise open it in the official app.'],
              ] as const).map(([icon, title, body]) => (
                <View key={title} style={{ flexDirection: 'row', gap: space.md, alignItems: 'flex-start' }}>
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: c.surfaceAlt, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={icon} size={20} color={c.accent} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[type.bodyStrong, { color: c.text }]}>{title}</Text>
                    <Text style={[type.caption, { color: c.textMuted }]}>{body}</Text>
                  </View>
                </View>
              ))}
              <Button label="See supported platforms" variant="ghost" icon="grid-outline" onPress={() => router.push('/platforms')} />
            </View>
          ) : null}
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
