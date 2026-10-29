import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Text, TextInput, View } from 'react-native';

import { api, ApiError } from '@/api/client';
import type { Account } from '@/api/types';
import { useToast } from '@/components/Toast';
import { Button, Card, Screen, Segmented } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space, type } from '@/theme/tokens';

/** Optional account. Registering upgrades the current anonymous install in place. */
export default function AccountScreen() {
  const { c } = useTheme();
  const toast = useToast();
  const router = useRouter();
  const [acct, setAcct] = useState<Account | null>(null);
  const [mode, setMode] = useState<'register' | 'login'>('register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.account().then(setAcct).catch(() => undefined);
  }, []);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (mode === 'register') await api.register(email.trim(), password);
      else await api.login(email.trim(), password);
      toast('success', mode === 'register' ? 'Account created' : 'Signed in');
      router.back();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const field = (value: string, set: (v: string) => void, label: string, secure = false) => (
    <TextInput value={value} onChangeText={set} placeholder={label} accessibilityLabel={label} secureTextEntry={secure}
      autoCapitalize="none" autoCorrect={false} keyboardType={secure ? 'default' : 'email-address'}
      textContentType={secure ? (mode === 'register' ? 'newPassword' : 'password') : 'emailAddress'}
      placeholderTextColor={c.textFaint}
      style={[type.body, { color: c.text, backgroundColor: c.surfaceAlt, borderRadius: radius.md, paddingHorizontal: space.lg, minHeight: 52 }]} />
  );

  if (acct && !acct.is_anonymous) {
    return (
      <Screen>
        <Card style={{ gap: space.md, marginTop: space.lg }}>
          <Text style={[type.heading, { color: c.text }]}>Signed in as {acct.email}</Text>
          <Button label="Sign out" variant="secondary" icon="log-out-outline" onPress={async () => { await api.logout(); toast('info', 'Signed out'); router.back(); }} />
        </Card>
      </Screen>
    );
  }
  return (
    <Screen>
      <Text style={[type.body, { color: c.textMuted, marginVertical: space.lg }]}>
        An account is optional. It lets your connected platform accounts follow you to a new phone. Downloads always stay on your device.
      </Text>
      <Card style={{ gap: space.md }}>
        <Segmented label="Account action" value={mode} onChange={setMode} options={[{ value: 'register', label: 'Create account' }, { value: 'login', label: 'Sign in' }]} />
        {field(email, setEmail, 'Email')}
        {field(password, setPassword, mode === 'register' ? 'Password (10+ characters)' : 'Password', true)}
        {err ? <Text accessibilityLiveRegion="polite" style={[type.caption, { color: c.danger }]}>{err}</Text> : null}
        <Button label={mode === 'register' ? 'Create account' : 'Sign in'} onPress={submit} loading={busy}
          disabled={!email.includes('@') || password.length < (mode === 'register' ? 10 : 1)} />
        {mode === 'login' ? (
          <View><Text style={[type.caption, { color: c.textFaint }]}>Signing in switches this phone to that account. History made while signed out stays on this device.</Text></View>
        ) : null}
      </Card>
    </Screen>
  );
}
