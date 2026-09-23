import { Event, Room } from './types';

export function normalizeBaseUrl(value: string, development = false): string {
  const url = new URL(value.trim());
  if (!['https:', ...(development ? ['http:'] : [])].includes(url.protocol)) {
    throw new Error('安装包请连接 HTTPS 服务器地址');
  }
  if (url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
    throw new Error('请输入不含路径、密码和查询参数的服务器根地址');
  }
  return url.origin;
}

export function isNewer(previous: Room | null, next: Room): boolean {
  if (!previous || previous.code !== next.code) return true;
  if (next.lobby_version !== previous.lobby_version) return next.lobby_version > previous.lobby_version;
  if (!previous.game) return true;
  if (!next.game) return false;
  return next.game.id !== previous.game.id || next.game.view_version >= previous.game.view_version;
}

export function eventText(event: Event): string {
  switch (event.kind) {
    case 'TEAM': return `${event.leader} 号提议队伍：${event.team?.join('、')} 号（第 ${event.attempt} 次提案）`;
    case 'SPEECH': return `${event.seat} 号：${event.text}`;
    case 'TEAM_VOTE': return `${event.approved ? '队伍通过' : '队伍否决'} · ${Object.entries(event.votes || {}).map(([seat, vote]) => `${seat}号${vote === 'approve' ? '赞成' : '反对'}`).join(' / ')}`;
    case 'QUEST': return `任务 ${event.quest} ${event.success ? '成功' : '失败'} · ${event.fails} 张失败牌 / 门槛 ${event.threshold}`;
    case 'ASSASSINATION': return `刺客指认 ${event.target} 号，${event.hit ? '命中梅林' : '未命中梅林'}`;
    case 'GAME_OVER': return `${event.winner === 'GOOD' ? '好人' : '邪恶'}阵营获胜`;
    default: return event.kind;
  }
}
