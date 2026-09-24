import React, { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { request, useSession } from '../src/api';
import { Catalog, ROLE_NAMES, Room } from '../src/types';
import { makeSeats, roomSetupError } from '../src/roomSetup';
import { Button, Card, Choice, Page, styles } from '../src/ui';

export default function CreateRoom() {
  const { identity } = useSession();
  const [n, setN] = useState(7);
  const [humans, setHumans] = useState(1);
  const [hostPlays, setHostPlays] = useState(true);
  const [profile, setProfile] = useState<string | null>(null);
  const [roles, setRoles] = useState(['PERCIVAL', 'MORGANA']);
  const [speechSeconds, setSpeechSeconds] = useState(60);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    if (identity) void request<Catalog>(identity.baseUrl, identity.token, '/api/config').then(value => {
      if (active) { setCatalog(value); setProfile(value.profiles[0]?.id || null); setError(''); }
    }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [identity, attempt]);
  if (!identity) return <Redirect href="/" />;
  const preset = catalog?.presets[String(n)];
  const aiAvailable = !!catalog?.profiles.length;
  const aiCount = n - humans;
  const problem = preset ? roomSetupError(n, humans, hostPlays, roles, preset.evil, aiAvailable) : '正在读取房间配置…';
  async function create() {
    if (!identity || busy || problem) return;
    setBusy(true); setError('');
    try {
      const room = await request<Room>(identity.baseUrl, identity.token, '/api/rooms', 'POST', { num_players: n, optional_roles: roles,
        seats: makeSeats(n, humans, profile), host_plays: hostPlays, speech_seconds: speechSeconds, action_seconds: 90 });
      router.replace({ pathname: '/room/[code]', params: { code: room.code } });
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <Page>
    <Text style={styles.eyebrow}>远程同局 / 好友与 AI</Text><Text style={styles.title}>创建房间</Text>
    {error ? <><Text accessibilityRole="alert" style={styles.error}>{error}</Text><Button label="重新读取配置" ghost onPress={() => setAttempt(v => v + 1)} /></> : null}
    <Card><Text style={styles.heading}>游戏总人数</Text><View style={styles.row}>{[5, 6, 7, 8, 9, 10].map(value => <Choice key={value} label={`${value}人`} selected={n === value} onPress={() => { setN(value); setHumans(h => Math.min(h, value)); }} />)}</View>
      <Text style={styles.muted}>{preset ? `${preset.good} 好人 / ${preset.evil} 邪恶 · 任务人数 ${preset.quest_sizes.join(' / ')}` : '正在读取服务器规则…'}</Text>
    </Card>
    <Card><Text style={styles.heading}>真人与 AI 玩家</Text>
      <View style={[styles.row, { justifyContent: 'space-between' }]}><Text style={styles.text}>我也参与对局</Text><Switch accessibilityLabel="房主参赛" value={hostPlays} onValueChange={value => { setHostPlays(value); if (value) setHumans(h => Math.max(1, h)); }} /></View>
      <Text style={styles.text}>真人席位{hostPlays ? '（包含你）' : '（房主仅观战）'}</Text>
      <View style={styles.row}>{Array.from({ length: n + 1 }, (_, i) => i).filter(v => v >= (hostPlays ? 1 : 0)).map(value => <Choice key={value} label={`${value}位`} selected={humans === value} onPress={() => setHumans(value)} />)}</View>
      <Text style={styles.heading}>{n} 人局：{humans} 位真人 + {aiCount} 位 AI 玩家</Text>
      <Text style={styles.muted}>{humans === 0 ? '全部由 AI 对局，你以公共视角观战。' : `创建后分享房间号，等待 ${Math.max(0, humans - (hostPlays ? 1 : 0))} 位好友远程加入。`}</Text>
      {catalog && !aiAvailable ? <><Text style={styles.error}>AI 暂不可用，请选择全真人对局或联系管理员。</Text><Button label="改为全真人对局" ghost onPress={() => setHumans(n)} /></> : null}
      {aiCount > 0 && aiAvailable ? <><Text style={styles.text}>AI 模型</Text><View style={styles.row}>{catalog?.profiles.map(p => <Choice key={p.id} label={p.label} selected={profile === p.id} onPress={() => setProfile(p.id)} />)}</View>
        <Text style={styles.muted}>每位 AI 独立扮演一个座位。模型由服务器统一提供，无需玩家填写密钥。服务异常时暂停对局，不会改用其他类型玩家。</Text></> : null}
    </Card>
    <Card><Text style={styles.heading}>角色配置</Text><Text style={styles.muted}>固定梅林与刺客；剩余名额自动补忠臣、普通爪牙。角色随机分配，与真人或 AI 无关。</Text>
      <View style={styles.row}>{['PERCIVAL', 'MORGANA', 'MORDRED', 'OBERON'].map(role => <Choice key={role} label={ROLE_NAMES[role]} selected={roles.includes(role)} onPress={() => setRoles(previous => previous.includes(role) ? previous.filter(r => r !== role) : [...previous, role])} />)}</View>
    </Card>
    <Card><Text style={styles.heading}>每位玩家发言时间</Text><View style={styles.row}>{[30, 60, 90, 120].map(value => <Choice key={value} label={`${value}秒`} selected={speechSeconds === value} onPress={() => setSpeechSeconds(value)} />)}</View>
      <Text style={styles.muted}>其他行动限时 90 秒。真人超时按房间协议处理；AI 超时或服务不可用则暂停，由房主重试。</Text>
    </Card>
    {problem && catalog ? <Text accessibilityRole="alert" style={styles.error}>{problem}</Text> : null}
    <Button testID="confirm-create" label={busy ? '创建中…' : '创建房间'} disabled={busy || !catalog || !!problem} onPress={() => void create()} />
  </Page>;
}
