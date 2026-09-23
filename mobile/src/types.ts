export type Kind = 'human' | 'bot' | 'llm';
export type Profile = { id: string; label: string };
export type Catalog = {
  roles: Record<string, string>;
  presets: Record<string, { good: number; evil: number; quest_sizes: number[]; fail_thresholds: number[] }>;
  profiles: Profile[];
  requires_access_code: boolean;
};
export type Identity = { id: string; name: string; token: string; baseUrl: string };
export type Action = { id: string; kind: string; team?: number[]; target?: number };
export type Command = { request_id: string; action_id: string; text: string };
export type Event = {
  seq: number; kind: string; seat?: number; text?: string; leader?: number; team?: number[];
  quest?: number; attempt?: number; votes?: Record<string, string>; approved?: boolean;
  fails?: number; threshold?: number; success?: boolean; target?: number; hit?: boolean;
  winner?: string; reason?: string;
};
export type Game = {
  id: string; n: number; phase: string; phase_name: string; view_version: number;
  leader: number; quest: number; rejections: number; team: number[]; results: boolean[];
  quests: { quest: number; team: number[]; fails: number; threshold: number; success: boolean }[];
  history: Event[]; quest_sizes: number[]; fail_thresholds: number[];
  speaker: number | null; deadline_at: number | null; winner: string | null; win_reason: string | null;
  private: { seat: number; role: string; alignment: string; known_evil: number[]; merlin_candidates: number[] } | null;
  submitted: boolean; request_id: string | null; allowed_actions: Action[];
  revealed_roles?: { seat: number; role: string }[];
};
export type Room = {
  code: string; status: string; is_host: boolean; seat: number | null; lobby_version: number;
  config: { num_players: number; optional_roles: string[]; speech_seconds: number; action_seconds: number };
  seats: { seat: number; kind: Kind; name: string; profile: string | null; occupied: boolean; is_you: boolean }[];
  game: Game | null; metrics?: Record<string, number>;
};
export type RecentRoom = { code: string; status: string; num_players: number };
export const ROLE_NAMES: Record<string, string> = {
  MERLIN: '梅林', PERCIVAL: '派西维尔', SERVANT: '忠臣', ASSASSIN: '刺客',
  MORGANA: '莫甘娜', MORDRED: '莫德雷德', OBERON: '奥伯伦', MINION: '普通爪牙',
};
