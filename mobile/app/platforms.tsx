import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '@/api/client';
import type { PlatformInfo } from '@/api/types';
import { PLATFORM_ICON } from '@/components/media';
import { Badge, Button, Card, Screen, Skeleton, type Tone } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';
import { space, type } from '@/theme/tokens';

const MODE: Record<PlatformInfo['download_mode'], [string, Tone]> = {
  direct: ['Direct download', 'success'],
  connected_account: ['Your own content', 'accent'],
  operator_api: ['Via official API', 'info'],
  link_only: ['Open in app only', 'neutral'],
  export_only: ['Data export only', 'neutral'],
};

/** The server's capability registry, shown verbatim — the app never claims more than the server reports. */
export default function Platforms() {
  const { c } = useTheme();
  const [list, setList] = useState<PlatformInfo[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    setErr(null);
    api.platforms().then(setList).catch((e) => setErr((e as Error).message));
  };
  useEffect(load, []);

  return (
    <Screen>
      <Text style={[type.body, { color: c.textMuted, marginVertical: space.lg }]}>
        Each platform decides what other apps may do with its media. Here’s exactly what this server supports right now.
      </Text>
      {err ? <Card style={{ gap: space.md }}><Text style={[type.body, { color: c.text }]}>{err}</Text><Button label="Retry" variant="secondary" onPress={load} /></Card> : null}
      {!list && !err ? [0, 1, 2].map((k) => <Skeleton key={k} height={120} style={{ marginBottom: space.md }} />) : null}
      <View style={{ gap: space.md }}>
        {list?.map((p) => {
          const [label, tone] = MODE[p.download_mode];
          return (
            <Card key={p.key} style={{ gap: space.sm }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md }}>
                <Ionicons name={PLATFORM_ICON[p.key] ?? 'globe-outline'} size={24} color={c.accent} />
                <Text style={[type.heading, { color: c.text, flex: 1 }]}>{p.name}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                <Badge label={label} tone={tone} />
                {!p.configured ? <Badge label="Not set up" tone="warning" /> : null}
                {p.connected ? <Badge label="Connected" tone="success" icon="checkmark" /> : null}
              </View>
              <Text style={[type.body, { color: c.textMuted }]}>{p.summary}</Text>
              {p.limitations.map((l) => (
                <View key={l} style={{ flexDirection: 'row', gap: 8 }}>
                  <Text style={{ color: c.textFaint }}>•</Text>
                  <Text style={[type.caption, { color: c.textMuted, flex: 1 }]}>{l}</Text>
                </View>
              ))}
            </Card>
          );
        })}
      </View>
    </Screen>
  );
}
