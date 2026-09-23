import React, { useCallback, useState } from 'react';
import { Alert, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { request, useSession } from '../src/api';
import { RecentRoom, Room } from '../src/types';
import { Button, Card, Input, Loading, Page, styles } from '../src/ui';

export default function Home() {
  const { identity, ready, login, logout } = useSession();
  const [base, setBase] = useState(process.env.EXPO_PUBLIC_API_URL || '');
  const [name, setName] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState<RecentRoom[]>([]);
  useFocusEffect(useCallback(() => {
    let active = true;
    if (identity) {
      void request<RecentRoom[]>(identity.baseUrl, identity.token, '/api/rooms')
        .then(value => { if (active) { setRecent(value); setError(''); } })
        .catch(err => { if (active) setError(err.message); });
    }
    return () => { active = false; };
  }, [identity]));
  async function enter(spectate: boolean) {
    if (!identity || busy) return;
    setBusy(true); setError('');
    try {
      const room = await request<Room>(identity.baseUrl, identity.token, `/api/rooms/${code.toUpperCase()}/join`, 'POST', { spectate });
      router.push({ pathname: '/room/[code]', params: { code: room.code } });
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  if (!ready) return <Loading />;
  return <Page>
    <View style={{ gap: 10, paddingVertical: 14 }}><Text style={styles.eyebrow}>SOCIAL DEDUCTION / 5–10 PLAYERS</Text><Text style={styles.title}>圆桌已备好。{ '\n' }谁值得信任？</Text><Text style={styles.muted}>真人与 AI 同桌。秘密身份，公开交锋。</Text></View>
    {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
    {!identity ? <Card>
      <Text style={styles.heading}>连接你的服务器</Text>
      <Input testID="server-url" accessibilityLabel="服务器地址" value={base} onChangeText={setBase} placeholder="https://avalon.your-domain.com" autoCapitalize="none" autoCorrect={false} keyboardType="url" />
      <Input testID="nickname" accessibilityLabel="玩家昵称" value={name} onChangeText={setName} placeholder="你的昵称" maxLength={24} />
      <Input testID="access-code" accessibilityLabel="服务器邀请码" value={accessCode} onChangeText={setAccessCode} placeholder="服务器邀请码（由部署者提供）" secureTextEntry maxLength={128} />
      <Button testID="login" label={busy ? '连接中…' : '进入大厅'} disabled={busy || !base || !name.trim()} onPress={() => {
        setBusy(true); setError('');
        void login(base, name, accessCode).catch(err => setError(err.message)).finally(() => setBusy(false));
      }} />
      <Text style={styles.muted}>这里只填写游戏服务器地址，不要填写模型 API Key。安装包使用 HTTPS；此版本需要联网。</Text>
    </Card> : <>
      <Card><Text style={styles.eyebrow}>你的圆桌身份</Text><Text style={styles.heading}>{identity.name}</Text><Text style={styles.muted}>{identity.baseUrl}</Text>
        <Button testID="create-room" label="创建房间" onPress={() => router.push('/create')} />
      </Card>
      <Card><Text style={styles.heading}>加入好友的对局</Text>
        <Input testID="room-code" accessibilityLabel="八位房间号" value={code} onChangeText={v => setCode(v.toUpperCase().replace(/[^A-Z0-9]/g, ''))} placeholder="输入 8 位房间号" maxLength={8} autoCapitalize="characters" />
        <View style={styles.row}><Button label="加入参赛" disabled={busy || code.length !== 8} onPress={() => void enter(false)} /><Button label="公共视角观战" ghost disabled={busy || code.length !== 8} onPress={() => void enter(true)} /></View>
      </Card>
      <Card><Text style={styles.heading}>最近的房间与复盘</Text>
        {recent.length ? recent.map(r => <Button key={r.code} ghost label={`${r.code} · ${r.num_players}人 · ${r.status === 'FINISHED' ? '查看复盘' : r.status === 'LOBBY' ? '等待开局' : '返回对局'}`} onPress={() => router.push({ pathname: '/room/[code]', params: { code: r.code } })} />) : <Text style={styles.muted}>创建第一张圆桌，或输入好友的房间号。</Text>}
      </Card>
      <Button label="退出会话 / 更换服务器" ghost onPress={() => Alert.alert('退出当前会话？', '退出会撤销本机会话凭证。已有参赛座位不能通过新建会话自动找回。', [{ text: '取消' }, { text: '退出', style: 'destructive', onPress: () => { void logout().catch(err => setError(err.message)); } }])} />
    </>}
    <Text style={styles.muted}>非官方玩家项目。经典顺序任务；计时、顺序发言与超时行为为本 App 房间协议。</Text>
  </Page>;
}
