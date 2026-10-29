/** Core UI primitives. All accept theme colours from useTheme(); every touch target ≥ 48dp. */
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useRef } from 'react';
import {
  AccessibilityRole, ActivityIndicator, Animated, Pressable, ScrollView, type StyleProp, StyleSheet, Text,
  TextInput, type TextInputProps, View, type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSettings } from '@/settings/SettingsProvider';
import { useTheme } from '@/theme/ThemeProvider';
import { HIT, radius, space, type } from '@/theme/tokens';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

export function useTap() {
  const { settings } = useSettings();
  return (style: Haptics.ImpactFeedbackStyle = Haptics.ImpactFeedbackStyle.Light) => {
    if (settings.haptics) Haptics.impactAsync(style).catch(() => undefined);
  };
}

export function Screen({ children, scroll = true, refresh }: { children: React.ReactNode; scroll?: boolean; refresh?: React.ReactElement }) {
  const { c, maxWidth } = useTheme();
  const inner = <View style={{ width: '100%', maxWidth, alignSelf: 'center', paddingHorizontal: space.lg, paddingBottom: space.xxl }}>{children}</View>;
  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={{ flex: 1, backgroundColor: c.bg }}>
      {scroll ? (
        <ScrollView keyboardShouldPersistTaps="handled" refreshControl={refresh as never} contentContainerStyle={{ flexGrow: 1 }}>
          {inner}
        </ScrollView>
      ) : (
        <View style={{ flex: 1, width: '100%', maxWidth, alignSelf: 'center', paddingHorizontal: space.lg }}>{children}</View>
      )}
    </SafeAreaView>
  );
}

export function Title({ children, sub }: { children: React.ReactNode; sub?: string }) {
  const { c } = useTheme();
  return (
    <View style={{ paddingTop: space.lg, paddingBottom: space.md }}>
      <Text accessibilityRole="header" style={[type.title, { color: c.text }]}>{children}</Text>
      {sub ? <Text style={[type.caption, { color: c.textMuted, marginTop: 4 }]}>{sub}</Text> : null}
    </View>
  );
}

export function Card({ children, style, padded = true }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; padded?: boolean }) {
  const { c } = useTheme();
  return (
    <View style={[{ backgroundColor: c.surface, borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: c.border,
      padding: padded ? space.lg : 0, overflow: 'hidden' }, style]}>
      {children}
    </View>
  );
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

export function Button({ label, onPress, variant = 'primary', icon, loading, disabled, small, accessibilityHint, style }: {
  label: string; onPress: () => void; variant?: Variant; icon?: IconName; loading?: boolean; disabled?: boolean; small?: boolean;
  accessibilityHint?: string; style?: StyleProp<ViewStyle>;
}) {
  const { c } = useTheme();
  const tap = useTap();
  const off = disabled || loading;
  const fg = variant === 'primary' ? c.accentText : variant === 'danger' ? c.danger : variant === 'ghost' ? c.accent : c.text;
  const content = (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingHorizontal: small ? 14 : 20,
      minHeight: small ? 40 : 54 }}>
      {loading ? <ActivityIndicator color={fg} /> : icon ? <Ionicons name={icon} size={small ? 16 : 19} color={fg} /> : null}
      <Text style={[small ? type.caption : type.bodyStrong, { color: fg, fontWeight: '700' }]}>{label}</Text>
    </View>
  );
  return (
    <Pressable
      accessibilityRole="button" accessibilityLabel={label} accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!off, busy: !!loading }} disabled={off}
      onPress={() => { tap(); onPress(); }}
      hitSlop={small ? 4 : 0}
      style={({ pressed }) => [{ borderRadius: radius.md, overflow: 'hidden', opacity: off ? 0.5 : pressed ? 0.85 : 1,
        transform: [{ scale: pressed ? 0.985 : 1 }] }, variant === 'secondary' && { backgroundColor: c.surfaceAlt },
        variant === 'danger' && { backgroundColor: c.dangerBg }, style]}>
      {variant === 'primary' ? (
        <LinearGradient colors={c.gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>{content}</LinearGradient>
      ) : content}
    </Pressable>
  );
}

export function IconButton({ icon, label, onPress, tone, disabled }: { icon: IconName; label: string; onPress: () => void; tone?: string; disabled?: boolean }) {
  const { c } = useTheme();
  const tap = useTap();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} onPress={() => { tap(); onPress(); }}
      style={({ pressed }) => ({ width: HIT, height: HIT, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center',
        backgroundColor: pressed ? c.surfaceAlt : 'transparent', opacity: disabled ? 0.4 : 1 })}>
      <Ionicons name={icon} size={21} color={tone ?? c.textMuted} />
    </Pressable>
  );
}

export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

export function Badge({ label, tone = 'neutral', icon }: { label: string; tone?: Tone; icon?: IconName }) {
  const { c } = useTheme();
  const map: Record<Tone, [string, string]> = {
    neutral: [c.surfaceAlt, c.textMuted], accent: [c.infoBg, c.accent], success: [c.successBg, c.success],
    warning: [c.warningBg, c.warning], danger: [c.dangerBg, c.danger], info: [c.infoBg, c.info],
  };
  const [bg, fg] = map[tone];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', backgroundColor: bg,
      borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}>
      {icon ? <Ionicons name={icon} size={12} color={fg} /> : null}
      <Text style={[type.micro, { color: fg }]}>{label.toUpperCase()}</Text>
    </View>
  );
}

export function ProgressBar({ value, indeterminate, tone }: { value: number | null; indeterminate?: boolean; tone?: string }) {
  const { c } = useTheme();
  const anim = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(anim, { toValue: Math.max(0, Math.min(1, value ?? 0)), duration: 250, useNativeDriver: false }).start();
  }, [value, anim]);
  useEffect(() => {
    if (!indeterminate) return;
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: false }),
      Animated.timing(pulse, { toValue: 0, duration: 900, useNativeDriver: false })]));
    loop.start();
    return () => loop.stop();
  }, [indeterminate, pulse]);
  const width = indeterminate ? pulse.interpolate({ inputRange: [0, 1], outputRange: ['15%', '65%'] })
    : anim.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
  return (
    <View accessibilityRole="progressbar" accessibilityValue={value != null && !indeterminate ? { min: 0, max: 100, now: Math.round(value * 100) } : undefined}
      style={{ height: 6, borderRadius: 3, backgroundColor: c.surfaceAlt, overflow: 'hidden' }}>
      <Animated.View style={{ width, height: '100%', borderRadius: 3, backgroundColor: tone ?? c.accent }} />
    </View>
  );
}

export function Skeleton({ height = 16, width = '100%', style }: { height?: number; width?: number | `${number}%`; style?: StyleProp<ViewStyle> }) {
  const { c } = useTheme();
  const o = useRef(new Animated.Value(0.5)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(o, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.timing(o, { toValue: 0.5, duration: 700, useNativeDriver: true })]));
    loop.start();
    return () => loop.stop();
  }, [o]);
  return <Animated.View accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
    style={[{ height, width, borderRadius: radius.sm, backgroundColor: c.skeleton, opacity: o }, style]} />;
}

export function EmptyState({ icon, title, body, action }: { icon: IconName; title: string; body?: string; action?: React.ReactNode }) {
  const { c } = useTheme();
  return (
    <View style={{ alignItems: 'center', paddingVertical: 48, paddingHorizontal: space.xl, gap: space.md }}>
      <LinearGradient colors={[c.surfaceAlt, c.surface]} style={{ width: 84, height: 84, borderRadius: 42, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={36} color={c.accent} />
      </LinearGradient>
      <Text style={[type.heading, { color: c.text, textAlign: 'center' }]}>{title}</Text>
      {body ? <Text style={[type.body, { color: c.textMuted, textAlign: 'center' }]}>{body}</Text> : null}
      {action}
    </View>
  );
}

export function SearchField(props: TextInputProps) {
  const { c } = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: c.surface, borderRadius: radius.md,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.border, paddingHorizontal: 14, minHeight: HIT }}>
      <Ionicons name="search" size={18} color={c.textFaint} />
      <TextInput placeholderTextColor={c.textFaint} autoCorrect={false} autoCapitalize="none" clearButtonMode="while-editing"
        accessibilityLabel={props.placeholder} {...props} style={[type.body, { flex: 1, color: c.text, paddingVertical: 10 }]} />
    </View>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: Array<{ value: T; label: string }>; onChange: (v: T) => void; label: string;
}) {
  const { c } = useTheme();
  const tap = useTap();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label}
      style={{ flexDirection: 'row', backgroundColor: c.surfaceAlt, borderRadius: radius.md, padding: 4, gap: 4 }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable key={o.value} accessibilityRole={'radio' as AccessibilityRole} accessibilityState={{ selected: on }}
            accessibilityLabel={o.label} onPress={() => { tap(); onChange(o.value); }}
            style={{ flex: 1, minHeight: 40, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center',
              backgroundColor: on ? c.surface : 'transparent' }}>
            <Text numberOfLines={1} style={[type.caption, { color: on ? c.text : c.textMuted, fontWeight: on ? '700' : '500' }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function SectionLabel({ children }: { children: string }) {
  const { c } = useTheme();
  return <Text style={[type.micro, { color: c.textFaint, marginTop: space.xl, marginBottom: space.sm, marginLeft: 4 }]}>{children.toUpperCase()}</Text>;
}

export function Row({ icon, title, subtitle, right, onPress, danger }: {
  icon?: IconName; title: string; subtitle?: string; right?: React.ReactNode; onPress?: () => void; danger?: boolean;
}) {
  const { c } = useTheme();
  const body = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: 56, paddingHorizontal: space.lg, paddingVertical: 10 }}>
      {icon ? <Ionicons name={icon} size={20} color={danger ? c.danger : c.accent} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={[type.bodyStrong, { color: danger ? c.danger : c.text }]}>{title}</Text>
        {subtitle ? <Text style={[type.caption, { color: c.textMuted, marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right ?? (onPress ? <Ionicons name="chevron-forward" size={18} color={c.textFaint} /> : null)}
    </View>
  );
  return onPress ? (
    <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityHint={subtitle} onPress={onPress}
      style={({ pressed }) => ({ backgroundColor: pressed ? c.surfaceAlt : 'transparent' })}>{body}</Pressable>
  ) : body;
}

export function Divider() {
  const { c } = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: c.border, marginLeft: space.lg }} />;
}
