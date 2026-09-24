import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { request, useSession } from '../src/api';
import { SERVER_URL } from '../src/config';
import { Catalog, RecentRoom, Room } from '../src/types';
import { Button, Card, Input, Loading, Page, styles } from '../src/ui';

const statusLabel: Record<string, string> = { FINISHED: '查看复盘', LOBBY: '等待开局', PAUSED_AI: 'AI 暂停中', ARCHIVED: '历史房间' };
export default function Home() {
  const { identity, ready, login, logout } = useSession();
  const [name, setName] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [connectionError, setConnectionError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [recent, setRecent] = useState<RecentRoom[]>([]);
  useEffect(() => {
    let active = true;
    setConnectionError(''); setCatalog(null);
    void request<Catalog>(SERVER_URL, null, '/api/config').then(value => { if (active) setCatalog(value); })
      .catch(() => { if (active) setConnectionError('暂时无法连接服务器，请检查网络后重试。'); });
    return () => { active = false; };
  }, [attempt]);
  useFocusEffect(useCallback(() => {
    let active = true;
    if (identity) void request<RecentRoom[]>(identity.baseUrl, identity.token, '/api/rooms')
      .then(value => { if (active) { setRecent(value); setError(''); } })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [identity]));
  async function enter(spectate: boolean) {
    if (!identity || busy) return;
    setBusy(true); setError('');
    try {
      const room = await request<Room>(identity.baseUrl, identity.token, `/api/rooms/${code}/join`, 'POST', { spectate });
      router.push({ pathname: '/room/[code]', params: { code: room.code } });
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  if (!ready) return <Loading />;
  return <Page>
    <View style={{ gap: 10, paddingVertical: 14 }}><Text style={styles.eyebrow}>AVALON / 5–10 人远程联机</Text><Text style={styles.title}>谁值得信任？</Text><Text style={styles.muted}>和好友远程同局，也可以独自挑战 AI 玩家。</Text></View>
    {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
    {!identity ? <Card>
      <Text style={styles.heading}>进入阿瓦隆</Text>
      <Text style={styles.muted}>{catalog ? '服务器已连接' : connectionError || '正在连接服务器…'}</Text>
      {connectionError ? <Button label="重试连接" ghost onPress={() => setAttempt(v => v + 1)} /> : null}
      <Input testID="nickname" accessibilityLabel="玩家昵称" value={name} onChangeText={setName} placeholder="你的昵称" maxLength={24} />
      {catalog?.requires_access_code ? <Input testID="access-code" accessibilityLabel="内测邀请码" value={accessCode} onChangeText={setAccessCode} placeholder="内测邀请码" secureTextEntry maxLength={128} /> : null}
      <Button testID="login" label={busy ? '进入中…' : '进入大厅'} disabled={busy || !catalog || !name.trim() || (!!catalog?.requires_access_code && !accessCode)} onPress={() => {
        setBusy(true); setError('');
        void login(name.trim(), accessCode).catch(err => setError(err.message)).finally(() => setBusy(false));
      }} />
      <Text style={styles.muted}>App 自动连接游戏服务，无需设置服务器或模型密钥。</Text>
    </Card> : <>
      <Card><Text style={styles.eyebrow}>游戏大厅</Text><Text style={styles.heading}>{identity.name}</Text>
        <Button testID="create-room" label="创建房间" onPress={() => router.push('/create')} />
        <Text style={styles.muted}>选择总人数，预留好友席位，其余由 AI 玩家加入。</Text>
      </Card>
      <Card><Text style={styles.heading}>加入好友的房间</Text>
        <Input testID="room-code" accessibilityLabel="八位房间号" value={code} onChangeText={v => setCode(v.toUpperCase().replace(/[^A-Z0-9]/g, ''))} placeholder="输入 8 位房间号" maxLength={8} autoCapitalize="characters" />
        <View style={styles.row}><Button label="加入参赛" disabled={busy || code.length !== 8} onPress={() => void enter(false)} /><Button label="观战" ghost disabled={busy || code.length !== 8} onPress={() => void enter(true)} /></View>
        <Text style={styles.muted}>好友可以在不同地点加入，无需连接同一个 Wi-Fi。</Text>
      </Card>
      <Card><Text style={styles.heading}>最近房间与复盘</Text>
        {recent.length ? recent.map(r => <Button key={r.code} ghost label={`${r.code} · ${r.num_players}人 · ${statusLabel[r.status] || '返回对局'}`} onPress={() => router.push({ pathname: '/room/[code]', params: { code: r.code } })} />) : <Text style={styles.muted}>创建房间，或输入好友分享的房间号。</Text>}
      </Card>
      <Button label="退出登录" ghost onPress={() => Alert.alert('退出登录？', '退出将清除本机会话。当前版本退出后无法自动找回已有参赛座位。', [{ text: '取消' }, { text: '退出', style: 'destructive', onPress: () => { void logout().catch(err => setError(err.message)); } }])} />
    </>}
    <Text style={styles.muted}>非官方玩家项目。文字讨论；计时、顺序发言与超时处理为 App 房间协议。</Text>
  </Page>;
}
