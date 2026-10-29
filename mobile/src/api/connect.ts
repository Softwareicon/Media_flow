import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';

import { api } from './client';

export type ConnectOutcome = 'connected' | 'cancelled' | 'denied' | 'failed';

/**
 * OAuth connect flow. The server returns a one-time `verifier` that only this app instance holds;
 * after the provider redirects back with a `handoff` code, the app proves it started the flow by
 * sending both. A link started by someone else can't attach this user's account to theirs.
 */
export async function connectPlatform(platform: string): Promise<ConnectOutcome> {
  const { authorize_url, return_url, verifier } = await api.startConnection(platform);
  const res = await WebBrowser.openAuthSessionAsync(authorize_url, return_url);
  if (res.type !== 'success') return 'cancelled';
  const q = Linking.parse(res.url).queryParams ?? {};
  if (q.status === 'denied') return 'denied';
  if (q.status !== 'pending' || typeof q.handoff !== 'string') return 'failed';
  const done = await api.completeConnection(platform, q.handoff, verifier);
  return done.connected ? 'connected' : 'failed';
}
