import Constants from 'expo-constants';
import { Directory } from 'expo-file-system';
import { useFocusEffect, useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import React, { useCallback, useState } from 'react';
import { Alert, Platform, Switch, Text, View } from 'react-native';

import { api, apiBaseUrl } from '@/api/client';
import { connectPlatform } from '@/api/connect';
import type { Account, Connection } from '@/api/types';
import { PLATFORM_ICON } from '@/components/media';
import { useToast } from '@/components/Toast';
import { Button, Card, Divider, Row, Screen, SectionLabel, Segmented, Title } from '@/components/ui';
import { clearHistory } from '@/db/database';
import { type SaveTarget, useSettings } from '@/settings/SettingsProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { space, type } from '@/theme/tokens';

const extra = (Constants.expoConfig?.extra ?? {}) as { privacyUrl?: string; termsUrl?: string };
const NAMES: Record<string, string> = { vimeo: 'Vimeo', instagram: 'Instagram', facebook: 'Facebook', pinterest: 'Pinterest' };

export default function SettingsScreen() {
  const { c } = useTheme();
  const { settings, update } = useSettings();
  const toast = useToast();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [conns, setConns] = useState<Connection[]>([]);
  const [server, setServer] = useState<'checking' | 'ok' | 'down'>('checking');

  const load = useCallback(() => {
    api.health().then(() => setServer('ok')).catch(() => setServer('down'));
    api.account().then(setAccount).catch(() => undefined);
    api.connections().then(setConns).catch(() => undefined);
  }, []);
  useFocusEffect(load);

  const sw = (value: boolean, onChange: (v: boolean) => void, label: string) => (
    <Switch value={value} onValueChange={onChange} accessibilityLabel={label} trackColor={{ true: c.accent, false: c.surfaceAlt }} />
  );

  const pickFolder = async () => {
    try {
      const dir = await Directory.pickDirectoryAsync();
      update({ saveTarget: 'folder', folderUri: dir.uri });
      toast('success', 'Folder selected');
    } catch {
      toast('info', 'No folder selected.');
    }
  };

  const connect = async (platform: string) => {
    try {
      const outcome = await connectPlatform(platform);
      if (outcome === 'connected') toast('success', `${NAMES[platform]} connected`);
      else if (outcome === 'failed') toast('error', 'Connection failed. Try again.');
      load();
    } catch (e) {
      toast('error', (e as Error).message);
    }
  };

  const disconnect = (platform: string) => Alert.alert(`Disconnect ${NAMES[platform]}?`, 'MediaFlow will delete its access token for this account.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Disconnect', style: 'destructive', onPress: () => api.disconnect(platform).then(load).catch((e) => toast('error', e.message)) },
  ]);

  const deleteAccount = () => Alert.alert('Delete account and data?',
    'This permanently deletes your MediaFlow account, connected-account tokens and download records on our server. Files on this device are not touched.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete everything', style: 'destructive', onPress: async () => {
        try {
          await api.deleteAccount();
          await clearHistory();
          toast('success', 'Your account and server data were deleted.');
          load();
        } catch (e) {
          toast('error', (e as Error).message);
        }
      } },
    ]);

  const targets: Array<{ value: SaveTarget; label: string }> = [
    { value: 'library', label: 'Photos' }, { value: 'app', label: 'In app' },
    ...(Platform.OS === 'android' ? [{ value: 'folder' as SaveTarget, label: 'Folder' }] : []),
  ];

  return (
    <Screen>
      <Title>Settings</Title>

      <SectionLabel>Appearance</SectionLabel>
      <Segmented label="Theme" value={settings.theme} onChange={(t) => update({ theme: t })}
        options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />

      <SectionLabel>Downloads</SectionLabel>
      <Card padded={false}>
        <View style={{ padding: space.lg, gap: space.sm }}>
          <Text style={[type.bodyStrong, { color: c.text }]}>Save finished files to</Text>
          <Segmented label="Save location" value={settings.saveTarget} onChange={(v) => (v === 'folder' && !settings.folderUri ? pickFolder() : update({ saveTarget: v }))} options={targets} />
          <Text style={[type.caption, { color: c.textMuted }]}>
            {settings.saveTarget === 'library' ? 'Photos and videos go to your photo library. Every file also stays in the Gallery tab.'
              : settings.saveTarget === 'folder' ? 'Files are copied to the folder you picked.'
                : Platform.OS === 'ios' ? 'Kept inside MediaFlow. Use Share → Save to Files to put one in a folder.' : 'Kept inside MediaFlow.'}
          </Text>
          {settings.saveTarget === 'folder' ? <Button label="Change folder" small variant="secondary" icon="folder-open-outline" onPress={pickFolder} /> : null}
        </View>
        <Divider />
        <Row icon="layers-outline" title="Simultaneous downloads" subtitle="More at once can be slower on mobile data"
          right={<Segmented label="Simultaneous downloads" value={String(settings.maxConcurrent)} onChange={(v) => update({ maxConcurrent: Number(v) })}
            options={['1', '2', '3', '4', '5'].map((v) => ({ value: v, label: v }))} />} />
        <Divider />
        <Row icon="wifi" title="Download on Wi-Fi only" right={sw(settings.wifiOnly, (v) => update({ wifiOnly: v }), 'Download on Wi-Fi only')} />
        <Divider />
        <Row icon="trophy-outline" title="Pre-select highest quality" right={sw(settings.preferHighest, (v) => update({ preferHighest: v }), 'Pre-select highest quality')} />
        <Divider />
        <Row icon="phone-portrait-outline" title="Haptic feedback" right={sw(settings.haptics, (v) => update({ haptics: v }), 'Haptic feedback')} />
      </Card>

      <SectionLabel>Connected accounts</SectionLabel>
      <Card padded={false}>
        {conns.length === 0 ? <Row icon="cloud-offline-outline" title="Unavailable" subtitle={server === 'down' ? 'Can’t reach the server' : 'Loading…'} /> : null}
        {conns.map((cn, i) => (
          <View key={cn.platform}>
            {i ? <Divider /> : null}
            <Row icon={PLATFORM_ICON[cn.platform]} title={NAMES[cn.platform] ?? cn.platform}
              subtitle={!cn.configured ? 'Not set up on this server' : cn.connected ? `Connected${cn.username ? ` as ${cn.username}` : ''}` : 'Save media you own'}
              right={cn.configured ? (
                <Button small label={cn.connected ? 'Disconnect' : 'Connect'} variant={cn.connected ? 'secondary' : 'primary'}
                  onPress={() => (cn.connected ? disconnect(cn.platform) : connect(cn.platform))} />) : undefined} />
          </View>
        ))}
      </Card>
      <Row icon="grid-outline" title="Supported platforms" subtitle="What each platform allows, and why" onPress={() => router.push('/platforms')} />

      <SectionLabel>Privacy & data</SectionLabel>
      <Card padded={false}>
        <Row icon="time-outline" title="Keep link history on this device" right={sw(settings.keepHistory, (v) => {
          update({ keepHistory: v });
          if (!v) clearHistory().catch(() => undefined);
        }, 'Keep link history')} />
        <Divider />
        <Row icon="server-outline" title="Keep download records on server" subtitle="Off = records are deleted as soon as a download finishes"
          right={sw(account?.keep_server_history ?? true, (v) => api.updateAccount(v).then(setAccount).catch((e) => toast('error', e.message)), 'Keep download records on server')} />
        <Divider />
        <Row icon="trash-outline" title="Delete server download records" onPress={() => api.deleteServerHistory().then(() => toast('success', 'Server records deleted')).catch((e) => toast('error', e.message))} />
        <Divider />
        <Row icon="person-circle-outline" title={account?.email ? account.email : 'Account (optional)'}
          subtitle={account?.is_anonymous === false ? 'Signed in' : 'Use MediaFlow without an account, or sign in to keep connections across devices'}
          onPress={() => router.push('/account')} />
        <Divider />
        <Row icon="warning-outline" title="Delete my account and server data" danger onPress={deleteAccount} />
      </Card>
      <Card padded={false} style={{ marginTop: space.md }}>
        <Row icon="document-text-outline" title="Privacy policy" onPress={() => extra.privacyUrl && WebBrowser.openBrowserAsync(extra.privacyUrl)} />
        <Divider />
        <Row icon="reader-outline" title="Terms of service" onPress={() => extra.termsUrl && WebBrowser.openBrowserAsync(extra.termsUrl)} />
      </Card>

      <SectionLabel>About</SectionLabel>
      <Card padded={false}>
        <Row icon="information-circle-outline" title={`Version ${Constants.expoConfig?.version ?? '—'}`} />
        <Divider />
        <Row icon={server === 'ok' ? 'checkmark-circle-outline' : 'alert-circle-outline'} title="Server"
          subtitle={`${server === 'ok' ? 'Connected' : server === 'down' ? 'Unreachable' : 'Checking…'} · ${(() => { try { return apiBaseUrl(); } catch { return 'misconfigured'; } })()}`} />
      </Card>
      <Text style={[type.caption, { color: c.textFaint, textAlign: 'center', marginTop: space.xl }]}>
        Only download content you own or have permission to save. MediaFlow never bypasses DRM, logins or private accounts.
      </Text>
    </Screen>
  );
}
