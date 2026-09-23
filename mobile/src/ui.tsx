import React from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export const colors = { bg: '#0C1420', panel: '#142132', border: '#28384B', ink: '#F3F0E9', muted: '#A5B2C4', gold: '#D8B36B', red: '#DE8D8A', green: '#92CAB3' };
export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 20, gap: 16, paddingBottom: 32 },
  card: { padding: 18, gap: 12, borderRadius: 18, backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border },
  title: { fontSize: 30, fontWeight: '800', color: colors.ink, letterSpacing: 1 },
  heading: { fontSize: 19, fontWeight: '700', color: colors.ink },
  text: { fontSize: 15, lineHeight: 23, color: colors.ink },
  muted: { fontSize: 13, lineHeight: 21, color: colors.muted },
  eyebrow: { fontSize: 12, fontWeight: '700', color: colors.gold, letterSpacing: 3 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'center' },
  error: { color: colors.red, fontSize: 14, lineHeight: 22 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: colors.bg, color: colors.ink, padding: 14, fontSize: 16, minHeight: 48 },
  button: { minHeight: 46, borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.gold },
  buttonText: { fontSize: 15, fontWeight: '700', color: colors.bg },
  ghost: { backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border },
  disabled: { opacity: 0.4 },
  pill: { paddingHorizontal: 15, paddingVertical: 10, minHeight: 42, borderRadius: 12, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  pillActive: { borderColor: colors.gold, backgroundColor: '#2C2B28' },
});
export function Page({ children }: { children: React.ReactNode }) {
  return <SafeAreaView style={styles.page} edges={['bottom']}><KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView>
  </KeyboardAvoidingView></SafeAreaView>;
}
export function Card({ children }: { children: React.ReactNode }) { return <View style={styles.card}>{children}</View>; }
export function Button({ label, onPress, disabled = false, ghost = false, testID }: { label: string; onPress: () => void; disabled?: boolean; ghost?: boolean; testID?: string }) {
  return <Pressable testID={testID} accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[styles.button, ghost && styles.ghost, disabled && styles.disabled]}>
    <Text style={[styles.buttonText, ghost && { color: colors.ink }]}>{label}</Text>
  </Pressable>;
}
export function Choice({ label, selected, onPress, disabled = false }: { label: string; selected: boolean; onPress: () => void; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ selected, disabled }} disabled={disabled} onPress={onPress} style={[styles.pill, selected && styles.pillActive, disabled && styles.disabled]}>
    <Text style={[styles.text, selected && { color: colors.gold }]}>{label}</Text>
  </Pressable>;
}
export function Input(props: TextInputProps) { return <TextInput placeholderTextColor={colors.muted} {...props} style={[styles.input, props.style]} />; }
export function Loading() { return <View style={[styles.page, { justifyContent: 'center', alignItems: 'center' }]}><ActivityIndicator color={colors.gold} /></View>; }
