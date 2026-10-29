/** Success / failure notifications. Announced to screen readers via a polite live region. */
import { Ionicons } from '@expo/vector-icons';
import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/theme/ThemeProvider';
import { radius, space, type } from '@/theme/tokens';

type Kind = 'success' | 'error' | 'info';
interface ToastMsg { id: number; kind: Kind; text: string; action?: { label: string; onPress: () => void } }

const Ctx = createContext<(kind: Kind, text: string, action?: ToastMsg['action']) => void>(() => undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState<ToastMsg | null>(null);
  const y = useRef(new Animated.Value(120)).current;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { c } = useTheme();
  const insets = useSafeAreaInsets();

  const hide = useCallback(() => {
    Animated.timing(y, { toValue: 120, duration: 180, useNativeDriver: true }).start(() => setMsg(null));
  }, [y]);

  const show = useCallback((kind: Kind, text: string, action?: ToastMsg['action']) => {
    if (timer.current) clearTimeout(timer.current);
    setMsg({ id: Date.now(), kind, text, action });
    AccessibilityInfo.announceForAccessibility(text);
    Animated.spring(y, { toValue: 0, useNativeDriver: true, friction: 8 }).start();
    timer.current = setTimeout(hide, action ? 5000 : 3200);
  }, [hide, y]);

  const tone = msg?.kind === 'success' ? c.success : msg?.kind === 'error' ? c.danger : c.info;
  return (
    <Ctx.Provider value={show}>
      {children}
      {msg ? (
        <Animated.View accessibilityLiveRegion="polite" pointerEvents="box-none"
          style={{ position: 'absolute', left: space.lg, right: space.lg, bottom: insets.bottom + 72, transform: [{ translateY: y }] }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, backgroundColor: c.surfaceAlt, borderRadius: radius.md,
            paddingHorizontal: space.lg, paddingVertical: space.md, borderLeftWidth: 4, borderLeftColor: tone,
            shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 16, shadowOffset: { width: 0, height: 6 }, elevation: 8 }}>
            <Ionicons name={msg.kind === 'success' ? 'checkmark-circle' : msg.kind === 'error' ? 'alert-circle' : 'information-circle'} size={22} color={tone} />
            <Text style={[type.body, { color: c.text, flex: 1 }]}>{msg.text}</Text>
            {msg.action ? (
              <Pressable accessibilityRole="button" onPress={() => { msg.action?.onPress(); hide(); }} hitSlop={12} style={{ minHeight: 44, justifyContent: 'center' }}>
                <Text style={[type.bodyStrong, { color: c.accent }]}>{msg.action.label}</Text>
              </Pressable>
            ) : null}
          </View>
        </Animated.View>
      ) : null}
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
