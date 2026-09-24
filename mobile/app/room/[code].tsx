import React, { useEffect, useState } from 'react';
import { Alert, AppState, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useSession } from '../../src/api';
import { useRoom } from '../../src/useRoom';
import { eventText } from '../../src/protocol';
import { ROLE_NAMES } from '../../src/types';
import { Button, Card, Choice, colors, Input, Loading, styles } from '../../src/ui';

const WHY: Record<string, string> = {
  FIVE_REJECTIONS: '同一任务连续五次组队被否决', THREE_FAILED_QUESTS: '三个任务失败',
  MERLIN_FOUND: '刺客命中梅林', MERLIN_SURVIVED: '三个任务成功，且梅林躲过刺杀',
};
export default function RoomScreen() {
  const params = useLocalSearchParams<{ code: string }>();
  const code = String(params.code || '').toUpperCase();
  const { identity, ready } = useSession();
  const live = useRoom(identity, code);
  const [identityOpen, setIdentityOpen] = useState(false);
  const [tab, setTab] = useState<'chat' | 'history' | 'rules'>('chat');
  const [selection, setSelection] = useState<number[]>([]);
  const [speech, setSpeech] = useState('');
  const [now, setNow] = useState(Date.now() / 1000);
  const game = live.room?.game;
  useEffect(() => { setSelection([]); setSpeech(''); }, [game?.request_id]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    const listener = AppState.addEventListener('change', state => { if (state !== 'active') setIdentityOpen(false); });
    return () => { clearInterval(timer); listener.remove(); };
  }, []);
  if (!ready) return <Loading />;
  if (!identity) return <Redirect href="/" />;
  if (!live.room) return <SafeAreaView style={[styles.page, styles.content]}><Text style={styles.text}>{live.error || '正在恢复你的对局视角…'}</Text><Button label="重试连接" onPress={() => void live.refresh()} /></SafeAreaView>;
  const room = live.room;
  const allowed = game?.allowed_actions || [];
  const menu = new Set(allowed.map(a => a.id));
  const canTeam = allowed.some(a => a.kind === 'PROPOSE');
  const canTarget = allowed.some(a => a.kind === 'ASSASSINATE');
  const locked = live.busy || !!live.pending || live.room?.status === 'PAUSED_AI' || live.room?.status === 'ARCHIVED';
  const selectedId = canTeam ? `team:${[...selection].sort((a, b) => a - b).join(',')}` : `target:${selection[0]}`;
  const remaining = game?.deadline_at ? Math.max(0, Math.ceil(game.deadline_at - now - live.serverOffset)) : null;
  const own = game?.private;
  function send(actionId: string, text = '') {
    if (!game?.request_id) return;
    void live.send({ request_id: game.request_id, action_id: actionId, text });
  }
  function choose(seat: number) {
    if (locked) return;
    if (canTarget && menu.has(`target:${seat}`)) setSelection([seat]);
    if (canTeam) setSelection(previous => previous.includes(seat) ? previous.filter(s => s !== seat) : [...previous, seat]);
  }
  return <SafeAreaView style={styles.page} edges={['bottom']}>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={[styles.row, { justifyContent: 'space-between' }]}><View><Text style={styles.eyebrow}>ROOM / {room.config.num_players} PLAYERS</Text><Text selectable style={[styles.heading, { letterSpacing: 3, marginTop: 6 }]}>{code}</Text></View><Text style={styles.muted}>{live.connection}</Text></View>
        {live.error ? <Text accessibilityRole="alert" style={styles.error}>{live.error}</Text> : null}
        {room.ai_issue ? <Card><Text style={styles.heading}>{room.status === 'ARCHIVED' ? '历史房间' : '对局已暂停'}</Text><Text style={styles.text}>{room.ai_issue.message}</Text>{room.is_host && room.status === 'PAUSED_AI' ? <Button testID="retry-ai" label="重试 AI 服务" disabled={live.busy} onPress={() => void live.retryAI()} /> : null}</Card> : null}
        {live.pending ? <Card><Text style={styles.text}>上次行动尚待确认</Text><Text style={styles.muted}>重新发送相同请求不会重复投票。确认前不能改投另一张牌。</Text><Button label="确认 / 重试原行动" disabled={live.busy} onPress={() => void live.retry()} /></Card> : null}
        {game ? <>
          <View style={local.quests}>{game.quest_sizes.map((size, index) => <View key={index} style={[local.quest, game.results[index] === true && { borderColor: colors.green }, game.results[index] === false && { borderColor: colors.red }]}><Text style={styles.muted}>任务 {index + 1}</Text><Text style={[styles.heading, { color: game.results[index] === true ? colors.green : game.results[index] === false ? colors.red : colors.ink }]}>{game.results[index] === true ? '成功' : game.results[index] === false ? '失败' : `${size}人`}</Text><Text style={[styles.muted, { fontSize: 10 }]}>{game.fail_thresholds[index]} 失败门槛</Text></View>)}</View>
          <View style={[styles.row, { justifyContent: 'space-between' }]}><Text style={styles.heading}>{game.phase_name}</Text>{remaining !== null ? <Text style={[styles.text, { color: colors.gold }]}>{remaining > 0 ? `${remaining}s` : '等待服务器结算'}</Text> : null}</View>
          {game.winner ? <Card><Text style={styles.eyebrow}>GAME OVER</Text><Text style={styles.title}>{game.winner === 'GOOD' ? '好人阵营获胜' : '邪恶阵营获胜'}</Text><Text style={styles.text}>{WHY[game.win_reason || '']}</Text></Card> : <Text style={styles.muted}>队长 {game.leader} 号 · 连续否决 {game.rejections}/5{game.speaker ? ` · 轮到 ${game.speaker} 号发言` : ''}</Text>}
          {own ? <Button ghost label={`查看我的身份 · ${room.seat} 号`} onPress={() => setIdentityOpen(true)} /> : <Text style={styles.muted}>你正在以公共视角观战，不会收到隐藏身份和密票。</Text>}
        </> : <Card><Text style={styles.heading}>等待好友加入</Text><Text style={styles.text}>分享上方房间号给好友。真人席全部加入后，房主可以开局。</Text><Text style={styles.muted}>特殊角色：梅林、刺客{room.config.optional_roles.map(r => `、${ROLE_NAMES[r]}`).join('')}。其余按阵营人数补齐。</Text></Card>}
        <View style={local.seats}>{room.seats.map(player => {
          const selected = selection.includes(player.seat);
          const team = game?.team.includes(player.seat);
          const targetAllowed = canTarget && menu.has(`target:${player.seat}`);
          return <Pressable key={player.seat} testID={`seat-${player.seat}`} accessibilityRole="button" accessibilityLabel={`${player.seat}号 ${player.name}${team ? '，当前任务队员' : ''}`} accessibilityState={{ selected, disabled: !(canTeam || targetAllowed) || locked }} disabled={!(canTeam || targetAllowed) || locked} onPress={() => choose(player.seat)} style={[local.seat, team && { borderColor: '#607892' }, selected && { borderColor: colors.gold, backgroundColor: '#2C2B28' }]}>
            <View style={styles.row}><View style={local.avatar}><Text style={[styles.heading, { color: colors.gold }]}>{player.seat}</Text></View><View style={{ flex: 1 }}><Text numberOfLines={1} style={styles.text}>{player.name}</Text><Text style={styles.muted}>{player.is_you ? '你 · ' : ''}{{ human: '真人', llm: 'AI 玩家', legacy: '历史玩家' }[player.kind]}{!player.occupied ? ' · 空席' : ''}</Text></View></View>
            {team ? <Text style={[styles.muted, { color: colors.gold }]}>当前任务队员</Text> : null}
          </Pressable>;
        })}</View>
        {game?.revealed_roles ? <Card><Text style={styles.heading}>身份揭晓</Text>{game.revealed_roles.map(r => <Text key={r.seat} style={styles.text}>{r.seat} 号 · {room.seats[r.seat - 1]?.name} · {ROLE_NAMES[r.role]}</Text>)}
          {room.metrics ? <Text style={styles.muted}>模型调用 {room.metrics.calls} 次 · 错误 {room.metrics.errors} 次 · AI 暂停 {room.metrics.ai_pauses || 0} 次 · 超时行动 {room.metrics.timeouts} 次{ '\n' }输入 / 输出 token：{room.metrics.input_tokens} / {room.metrics.output_tokens}</Text> : null}
        </Card> : null}
        <View style={styles.row}>{(['chat', 'history', 'rules'] as const).map(value => <Choice key={value} label={{ chat: '讨论', history: '行动记录', rules: '本局规则' }[value]} selected={tab === value} onPress={() => setTab(value)} />)}</View>
        {tab === 'rules' ? <Card><Text style={styles.heading}>经典顺序任务</Text><Text style={styles.text}>全体表决需严格多数赞成；平票否决。同一任务连续五次否决，邪恶直接获胜。好人只能出成功牌；邪恶可成功或失败。7–10 人仅第四任务需要两张失败牌。三个任务成功后仍需经过刺杀。</Text><Text style={styles.muted}>房间协议：每次组队后从队长下一席开始，按座位顺序发言一轮；每席 {room.config.speech_seconds} 秒，其他行动 {room.config.action_seconds} 秒。三次成功后全员最终陈述一轮，再由刺客指认。真人超时默认跳过发言、反对队伍、任务成功；组队与刺杀选择菜单第一项。刺杀任何非梅林目标均按未命中结算。本版不启用湖中仙女及其他扩展。</Text><Text style={styles.muted}>玩家可以游戏内伪装角色，但不能展示后台角色面板作为认证。任务成功不等于队内全是好人。AI 异常、超时或预算耗尽时暂停对局，不代替 AI 做决定。</Text></Card> : <View style={{ gap: 10 }}>
          {(game?.history || []).filter(e => tab === 'history' ? e.kind !== 'SPEECH' : true).slice(-100).map(event => <View key={event.seq} style={[styles.card, { padding: 14 }]}><Text style={styles.eyebrow}>#{event.seq} / {event.kind === 'SPEECH' ? '玩家发言' : '服务器事件'}</Text><Text style={event.kind === 'SPEECH' ? styles.text : styles.muted}>{eventText(event)}</Text></View>)}
          {!game?.history.length ? <Text style={styles.muted}>开局后，公开发言与已揭晓的行动会出现在这里。</Text> : null}
        </View>}
      </ScrollView>
      <View style={local.actionBar}>
        {!game ? room.is_host ? <Button testID="start-game" label="开始对局" disabled={locked || room.seats.some(s => !s.occupied)} onPress={() => void live.start()} /> : <Text style={styles.muted}>等待房主开始对局</Text> : null}
        {canTeam ? <><Text style={styles.muted}>点击座位选择 {game?.quest_sizes[game.quest]} 位队员，已选 {selection.length} 位</Text><Button testID="submit-team" label="确认组队" disabled={locked || !menu.has(selectedId)} onPress={() => send(selectedId)} /></> : null}
        {menu.has('speak') ? <><Input testID="speech-input" accessibilityLabel="公开发言" multiline value={speech} onChangeText={setSpeech} placeholder="依据公开证据，说出你的判断…" maxLength={240} style={{ maxHeight: 110 }} /><View style={styles.row}><Button label={`公开发言 ${speech.length}/240`} disabled={locked || !speech.trim()} onPress={() => send('speak', speech.trim())} /><Button label="跳过" ghost disabled={locked} onPress={() => send('skip')} /></View></> : null}
        {menu.has('approve') ? <><Text style={styles.muted}>所有票锁定后统一公开。其他玩家暂时看不到你的选择。</Text><View style={styles.row}><Button testID="vote-approve" label="赞成队伍" disabled={locked} onPress={() => send('approve')} /><Button label="反对队伍" ghost disabled={locked} onPress={() => send('reject')} /></View></> : null}
        {menu.has('success') ? <><Text style={styles.muted}>秘密提交任务牌，只公开汇总结果。</Text><View style={styles.row}><Button label="提交成功" disabled={locked} onPress={() => send('success')} />{menu.has('fail') ? <Button label="提交失败" ghost disabled={locked} onPress={() => send('fail')} /> : null}</View></> : null}
        {canTarget ? <><Text style={styles.muted}>选择最可能的梅林。最终只有一次指认。</Text><Button label={selection.length ? `指认 ${selection[0]} 号` : '先点击目标座位'} disabled={locked || !menu.has(selectedId)} onPress={() => Alert.alert('确认最终指认', `确定指认 ${selection[0]} 号为梅林？此行动不能撤销。`, [{ text: '取消' }, { text: '确认指认', onPress: () => send(selectedId) }])} /></> : null}
        {game && !allowed.length ? <Text style={styles.muted}>{room.status === 'PAUSED_AI' ? '等待 AI 服务恢复，倒计时已暂停。' : room.status === 'ARCHIVED' ? '历史房间为只读，请返回大厅创建新房间。' : game.winner ? '对局已保存，可从大厅再次查看复盘。' : game.submitted ? '你的行动已锁定，等待其他玩家。' : '等待当前行动者；切后台或断线后可重新进入。'}</Text> : null}
      </View>
    </KeyboardAvoidingView>
    <Modal visible={identityOpen} transparent animationType="fade" onRequestClose={() => setIdentityOpen(false)}><View style={local.modal}><View style={[styles.card, { width: '100%', maxWidth: 440 }]}><Text style={styles.eyebrow}>PRIVATE / 仅你可见</Text><Text style={styles.title}>{own ? ROLE_NAMES[own.role] : '公共观战'}</Text>{own ? <><Text style={styles.text}>{own.alignment === 'GOOD' ? '好人阵营' : '邪恶阵营'} · {own.seat} 号</Text>{own.known_evil.length ? <Text style={styles.text}>规则赋予的已知邪恶座位：{own.known_evil.join('、')}</Text> : null}{own.merlin_candidates.length ? <Text style={styles.text}>梅林候选：{own.merlin_candidates.join('、')}。名单顺序不代表具体身份。</Text> : null}<Text style={styles.muted}>未提供的信息不代表确定好人。请勿展示此面板作为身份认证。</Text></> : null}<Button label="收起身份" onPress={() => setIdentityOpen(false)} /></View></View></Modal>
  </SafeAreaView>;
}
const local = StyleSheet.create({
  quests: { flexDirection: 'row', gap: 5 },
  quest: { flex: 1, alignItems: 'center', gap: 4, paddingVertical: 12, borderRadius: 12, backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border },
  seats: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  seat: { width: '48%', flexGrow: 1, minWidth: 140, padding: 12, gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: 15, backgroundColor: colors.panel },
  avatar: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg },
  actionBar: { padding: 16, gap: 10, borderTopWidth: 1, borderColor: colors.border, backgroundColor: colors.bg },
  modal: { flex: 1, padding: 24, backgroundColor: '#000B', justifyContent: 'center', alignItems: 'center' },
});
