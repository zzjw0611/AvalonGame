import { Kind } from './types';

export function roomSetupError(n: number, humans: number, hostPlays: boolean, roles: string[], evil: number, aiAvailable: boolean): string | null {
  if (!Number.isInteger(n) || n < 5 || n > 10) return '游戏人数必须为 5–10 人';
  if (!Number.isInteger(humans) || humans < (hostPlays ? 1 : 0) || humans > n) return '真人席位数量不正确';
  if (humans < n && !aiAvailable) return 'AI 暂不可用，请选择全真人对局';
  if (1 + roles.filter(r => r !== 'PERCIVAL').length > evil) return '特殊邪恶角色超过阵营名额';
  if (n === 5 && roles.includes('PERCIVAL') && !roles.some(r => r === 'MORGANA' || r === 'MORDRED')) return '五人局派西维尔需搭配莫甘娜或莫德雷德';
  return null;
}
export function makeSeats(n: number, humans: number, profile: string | null): { kind: Kind; profile: string | null }[] {
  if (!Number.isInteger(n) || !Number.isInteger(humans) || n < 5 || n > 10 || humans < 0 || humans > n) throw new Error('人数配置不正确');
  if (humans < n && !profile) throw new Error('AI 暂不可用');
  return Array.from({ length: n }, (_, i) => i < humans ? { kind: 'human', profile: null } : { kind: 'llm', profile });
}
