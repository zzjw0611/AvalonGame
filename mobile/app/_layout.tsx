import React from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider } from '../src/api';
import { colors } from '../src/ui';

export default function Layout() {
  return <SafeAreaProvider><SessionProvider><StatusBar style="light" /><Stack screenOptions={{ headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.ink, headerShadowVisible: false, contentStyle: { backgroundColor: colors.bg } }}>
    <Stack.Screen name="index" options={{ title: 'AVALON', headerTitleStyle: { color: colors.gold } }} />
    <Stack.Screen name="create" options={{ title: '创建房间' }} />
    <Stack.Screen name="room/[code]" options={{ title: '阿瓦隆对局' }} />
  </Stack></SessionProvider></SafeAreaProvider>;
}
