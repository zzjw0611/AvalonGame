import React, { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { request, useSession } from '../src/api';
import { Catalog, Kind, ROLE_NAMES, Room } from '../src/types';
import { Button, Card, Choice, Page, styles } from '../src/ui';

type Slot = { kind: Kind; profile: string | null };
export default function CreateRoom() {
  const { identity } = useSession();
  const [n, setN] = useState(7);
  const [hostPlays, setHostPlays] = useState(true);
  const [slots, setSlots] = useState<Slot[]>([{ kind: 'human', profile: null }, ...Array.from({ length: 6 }, () => ({ kind: 'bot' as Kind, profile: null }))]);
  const [roles, setRoles] = useState(['PERCIVAL', 'MORGANA']);
  const [speechSeconds, setSpeechSeconds] = useState(60);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    if (identity) void request<Catalog>(identity.baseUrl, identity.token, '/api/config').then(value => { if (active) setCatalog(value); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [identity]);
  if (!identity) return <Redirect href="/" />;
  const preset = catalog?.presets[String(n)];
  const evilSpecials = 1 + roles.filter(r => r !== 'PERCIVAL').length;
  const invalid = !!preset && evilSpecials > preset.evil;
  function changeN(value: number) {
    setN(value);
    setSlots(previous => Array.from({ length: value }, (_, i) => previous[i] || { kind: 'bot', profile: null }));
  }
  function changeSlot(index: number, kind: Kind, profile: string | null = null) {
    setSlots(previous => previous.map((s, i) => i === index ? { kind, profile: kind === 'llm' ? profile || catalog?.profiles[0]?.id || null : null } : s));
  }
  async function create() {
    if (!identity || busy) return;
    setBusy(true); setError('');
    try {
      const room = await request<Room>(identity.baseUrl, identity.token, '/api/rooms', 'POST', { num_players: n, optional_roles: roles, seats: slots, host_plays: hostPlays, speech_seconds: speechSeconds, action_seconds: 90 });
      router.replace({ pathname: '/room/[code]', params: { code: room.code } });
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <Page>
    <Text style={styles.eyebrow}>BUILD YOUR TABLE</Text><Text style={styles.title}>定制这场交锋</Text>
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <Card><Text style={styles.heading}>参赛总人数</Text><View style={styles.row}>{[5, 6, 7, 8, 9, 10].map(value => <Choice key={value} label={`${value}人`} selected={n === value} onPress={() => changeN(value)} />)}</View>
      <Text style={styles.muted}>{preset ? `${preset.good} 好人 / ${preset.evil} 邪恶 · 任务人数 ${preset.quest_sizes.join(' / ')}` : '正在读取服务器规则…'}</Text>
      <View style={[styles.row, { justifyContent: 'space-between' }]}><Text style={styles.text}>我作为 1 号玩家参赛</Text><Switch accessibilityLabel="房主参赛" value={hostPlays} onValueChange={value => { setHostPlays(value); changeSlot(0, value ? 'human' : 'bot'); }} /></View>
      {!hostPlays ? <Text style={styles.muted}>房主仅获公共观战视角，可配置全 AI 对局。</Text> : null}
    </Card>
    <Card><Text style={styles.heading}>特殊角色</Text><Text style={styles.muted}>固定梅林与刺客；剩余名额自动补忠臣、普通爪牙。</Text>
      <View style={styles.row}>{['PERCIVAL', 'MORGANA', 'MORDRED', 'OBERON'].map(role => <Choice key={role} label={ROLE_NAMES[role]} selected={roles.includes(role)} onPress={() => setRoles(previous => previous.includes(role) ? previous.filter(r => r !== role) : [...previous, role])} />)}</View>
      {invalid ? <Text style={styles.error}>当前特殊邪恶角色超过 {preset?.evil} 个邪恶名额，请减少选项。</Text> : null}
      {n === 5 && roles.includes('PERCIVAL') && !roles.some(r => r === 'MORGANA' || r === 'MORDRED') ? <Text style={styles.error}>五人局派西维尔需搭配莫甘娜或莫德雷德。</Text> : null}
    </Card>
    <Card><Text style={styles.heading}>每个座位由谁来玩？</Text>
      {slots.map((slot, i) => <View key={i} style={{ gap: 8, paddingVertical: 9 }}><Text style={styles.text}>{i + 1} 号{hostPlays && i === 0 ? ` · ${identity.name}（你）` : ''}</Text>
        <View style={styles.row}>{(['human', 'bot', 'llm'] as Kind[]).map(kind => <Choice key={kind} label={{ human: '真人', bot: '规则机器人', llm: '大模型' }[kind]} selected={slot.kind === kind} disabled={(hostPlays && i === 0) || (kind === 'llm' && !catalog?.profiles.length)} onPress={() => changeSlot(i, kind)} />)}</View>
        {slot.kind === 'llm' ? <View style={styles.row}>{catalog?.profiles.map(profile => <Choice key={profile.id} label={profile.label} selected={slot.profile === profile.id} onPress={() => changeSlot(i, 'llm', profile.id)} />)}</View> : null}
      </View>)}
      {!catalog?.profiles.length ? <Text style={styles.muted}>服务器尚未配置可用模型。规则机器人可用于测试，但不是大模型玩家。</Text> : <Text style={styles.muted}>模型不可用、超出调用预算或响应不合法时使用保底策略，复盘可查看调用与兜底统计。</Text>}
    </Card>
    <Card><Text style={styles.heading}>每席发言时间</Text><View style={styles.row}>{[30, 60, 90, 120].map(value => <Choice key={value} label={`${value}秒`} selected={speechSeconds === value} onPress={() => setSpeechSeconds(value)} />)}</View>
      <Text style={styles.muted}>其他行动限时 90 秒。超时默认：跳过发言、反对队伍、任务成功；组队和刺杀选择合法菜单第一项。这是房间协议，不是原版规则。</Text>
    </Card>
    <Button testID="confirm-create" label={busy ? '创建中…' : '创建圆桌'} disabled={busy || !catalog || invalid} onPress={() => void create()} />
  </Page>;
}
