"""Classic sequential Avalon rules, independent of web/LLM/database code.

Adapted (2026-09-23) from xqbjs/AvalonGame, commit
c46f1d923930484ede6dbf0d44e6f3e3889b0afa, games/games/avalon/engine.py.
The preset table is retained; transitions, validation and views are rewritten.
Upstream: Copyright 2026 MinkunXue and FaLi. Apache-2.0; see LICENSE/NOTICE.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random
import time
import uuid
from collections import Counter
from typing import Any

PRESETS = {
    5: ((3, 2), (2, 3, 2, 3, 3), (1, 1, 1, 1, 1)),
    6: ((4, 2), (2, 3, 4, 3, 4), (1, 1, 1, 1, 1)),
    7: ((4, 3), (2, 3, 3, 4, 4), (1, 1, 1, 2, 1)),
    8: ((5, 3), (3, 4, 4, 5, 5), (1, 1, 1, 2, 1)),
    9: ((6, 3), (3, 4, 4, 5, 5), (1, 1, 1, 2, 1)),
    10: ((6, 4), (3, 4, 4, 5, 5), (1, 1, 1, 2, 1)),
}
GOOD = frozenset({'MERLIN', 'PERCIVAL', 'SERVANT'})
OPTIONAL = frozenset({'PERCIVAL', 'MORGANA', 'MORDRED', 'OBERON'})
ROLE_NAMES = {
    'MERLIN': '梅林', 'PERCIVAL': '派西维尔', 'SERVANT': '忠臣',
    'ASSASSIN': '刺客', 'MORGANA': '莫甘娜', 'MORDRED': '莫德雷德',
    'OBERON': '奥伯伦', 'MINION': '普通爪牙',
}
PHASE_NAMES = {
    'PROPOSE': '队长组队', 'DISCUSS': '讨论队伍', 'TEAM_VOTE': '队伍表决',
    'QUEST_PLAY': '秘密执行任务', 'FINAL_DISCUSS': '最终陈述',
    'ASSASSINATE': '刺客指认', 'GAME_OVER': '对局结束',
}


class RuleError(ValueError):
    """An action/configuration the authoritative server must reject."""


def role_deck(n: int, optional: list[str]) -> list[str]:
    if type(n) is not int or n not in PRESETS:
        raise RuleError('经典版仅支持 5–10 人')
    if len(optional) != len(set(optional)) or not set(optional) <= OPTIONAL:
        raise RuleError('特殊角色重复或不受支持')
    if n == 5 and 'PERCIVAL' in optional and not {'MORGANA', 'MORDRED'} & set(optional):
        raise RuleError('五人局加入派西维尔时需同时加入莫甘娜或莫德雷德')
    good = ['MERLIN'] + [r for r in optional if r in GOOD]
    evil = ['ASSASSIN'] + [r for r in optional if r not in GOOD]
    ng, ne = PRESETS[n][0]
    if len(good) > ng or len(evil) > ne:
        raise RuleError('特殊角色超过该人数的阵营名额')
    return good + ['SERVANT'] * (ng - len(good)) + evil + ['MINION'] * (ne - len(evil))


def create_game(config: dict, *, rng: random.Random | None = None, now: float | None = None) -> dict:
    rng = rng or random.SystemRandom()
    roles = role_deck(config['num_players'], config['optional_roles'])
    rng.shuffle(roles)
    n = len(roles)
    game = {
        'id': uuid.uuid4().hex, 'n': n, 'roles': roles, 'config': copy.deepcopy(config),
        'leader': rng.randint(1, n), 'quest': 0, 'rejections': 0,
        'team': [], 'results': [], 'quests': [], 'history': [], 'submitted': {},
        'receipts': {}, 'phase': '', 'epoch': 0, 'speaker_index': 0,
        'order': [], 'winner': None, 'win_reason': None, 'deadline_at': 0,
    }
    _phase(game, 'PROPOSE', time.time() if now is None else now)
    return game


def _event(g: dict, kind: str, **data: Any) -> None:
    g['history'].append({'seq': len(g['history']) + 1, 'kind': kind, **data})


def _phase(g: dict, phase: str, now: float) -> None:
    g['phase'] = phase
    g['epoch'] += 1
    g['submitted'] = {}
    seconds = g['config']['speech_seconds'] if phase in {'DISCUSS', 'FINAL_DISCUSS'} else g['config']['action_seconds']
    g['deadline_at'] = None if phase == 'GAME_OVER' else now + seconds
    if phase in {'DISCUSS', 'FINAL_DISCUSS'}:
        g['order'] = [(g['leader'] + i - 1) % g['n'] + 1 for i in range(1, g['n'] + 1)]
        g['speaker_index'] = 0


def _finish(g: dict, winner: str, reason: str, now: float) -> None:
    g['winner'], g['win_reason'] = winner, reason
    _event(g, 'GAME_OVER', winner=winner, reason=reason)
    _phase(g, 'GAME_OVER', now)


def private_info(g: dict, seat: int) -> dict:
    if type(seat) is not int or not 1 <= seat <= g['n']:
        raise RuleError('无效座位')
    role = g['roles'][seat - 1]
    evil = [i + 1 for i, r in enumerate(g['roles']) if r not in GOOD]
    visible: list[int] = []
    if role == 'MERLIN':
        visible = [s for s in evil if g['roles'][s - 1] != 'MORDRED']
    elif role not in GOOD and role != 'OBERON':
        visible = [s for s in evil if s != seat and g['roles'][s - 1] != 'OBERON']
    candidates = [i + 1 for i, r in enumerate(g['roles']) if r in {'MERLIN', 'MORGANA'}] if role == 'PERCIVAL' else []
    return {'seat': seat, 'role': role, 'alignment': 'GOOD' if role in GOOD else 'EVIL',
            'known_evil': sorted(visible), 'merlin_candidates': sorted(candidates)}


def request_id(g: dict, seat: int) -> str:
    return f"{g['id']}:{g['epoch']}:{seat}"


def actions(g: dict, seat: int | None) -> list[dict]:
    if seat is None or not 1 <= seat <= g['n'] or g['phase'] == 'GAME_OVER':
        return []
    phase = g['phase']
    if phase == 'PROPOSE' and seat == g['leader']:
        k = PRESETS[g['n']][1][g['quest']]
        return [{'id': 'team:' + ','.join(map(str, team)), 'kind': 'PROPOSE', 'team': list(team)}
                for team in itertools.combinations(range(1, g['n'] + 1), k)]
    if phase in {'DISCUSS', 'FINAL_DISCUSS'} and seat == g['order'][g['speaker_index']]:
        return [{'id': 'speak', 'kind': 'SPEAK'}, {'id': 'skip', 'kind': 'SKIP'}]
    if phase == 'TEAM_VOTE' and str(seat) not in g['submitted']:
        return [{'id': 'approve', 'kind': 'TEAM_VOTE'}, {'id': 'reject', 'kind': 'TEAM_VOTE'}]
    if phase == 'QUEST_PLAY' and seat in g['team'] and str(seat) not in g['submitted']:
        cards = ['success'] if g['roles'][seat - 1] in GOOD else ['success', 'fail']
        return [{'id': card, 'kind': 'QUEST_PLAY'} for card in cards]
    if phase == 'ASSASSINATE' and g['roles'][seat - 1] == 'ASSASSIN':
        # Do not filter by true alignment; the menu itself must not leak roles.
        return [{'id': f'target:{s}', 'kind': 'ASSASSINATE', 'target': s}
                for s in range(1, g['n'] + 1) if s != seat]
    return []


def observe(g: dict, seat: int | None) -> dict:
    own_submitted = seat is not None and str(seat) in g['submitted']
    public = {key: copy.deepcopy(g[key]) for key in (
        'id', 'n', 'leader', 'quest', 'rejections', 'team', 'results', 'quests',
        'history', 'phase', 'winner', 'win_reason', 'deadline_at')}
    public['phase_name'] = PHASE_NAMES[g['phase']]
    public['quest_sizes'] = list(PRESETS[g['n']][1])
    public['fail_thresholds'] = list(PRESETS[g['n']][2])
    # The deck composition is public setup information, NOT a seat-to-role map.
    # Derive it from the room configuration rather than the shuffled identity array.
    public['role_counts'] = dict(sorted(Counter(role_deck(g['n'], g['config']['optional_roles'])).items()))
    public['speaker'] = g['order'][g['speaker_index']] if g['phase'] in {'DISCUSS', 'FINAL_DISCUSS'} else None
    # Only public changes and this seat's own receipt change the version.
    public['view_version'] = g['epoch'] * 2 + int(own_submitted)
    public['private'] = private_info(g, seat) if seat else None
    public['submitted'] = own_submitted
    public['request_id'] = request_id(g, seat) if seat else None
    public['allowed_actions'] = actions(g, seat)
    if g['phase'] == 'GAME_OVER':
        public['revealed_roles'] = [{'seat': i + 1, 'role': r} for i, r in enumerate(g['roles'])]
    return public


def apply(g: dict, seat: int, req: str, action_id: str, text: str = '', *, now: float | None = None) -> tuple[dict, bool]:
    """Copy-on-write transition; failed commands never mutate the original.

    A phase/seat request is consumed exactly once. Identical retries succeed,
    changing a previously consumed request is an error. DB commits are external.
    """
    now = time.time() if now is None else now
    fingerprint = hashlib.sha256(json.dumps([seat, action_id, text], ensure_ascii=False).encode()).hexdigest()
    if req in g['receipts']:
        if g['receipts'][req] != fingerprint:
            raise RuleError('同一请求不能修改已提交的行动')
        return g, False
    if req != request_id(g, seat):
        raise RuleError('阶段已变化，请刷新局面')
    menu = {a['id']: a for a in actions(g, seat)}
    if action_id not in menu:
        raise RuleError('当前阶段无权执行该行动')
    if not isinstance(text, str) or len(text) > 240:
        raise RuleError('发言最多 240 字')
    if action_id != 'speak' and text:
        raise RuleError('非发言行动不得附带公开文本')
    if action_id == 'speak' and not text.strip():
        raise RuleError('发言不能为空，可选择跳过')
    s = copy.deepcopy(g)
    s['receipts'][req] = fingerprint
    phase = s['phase']
    if phase == 'PROPOSE':
        s['team'] = menu[action_id]['team']
        _event(s, 'TEAM', quest=s['quest'] + 1, leader=seat, team=s['team'], attempt=s['rejections'] + 1)
        _phase(s, 'DISCUSS', now)
    elif phase in {'DISCUSS', 'FINAL_DISCUSS'}:
        _event(s, 'SPEECH', seat=seat, text=text.strip() if action_id == 'speak' else '（跳过发言）')
        s['speaker_index'] += 1
        if s['speaker_index'] == s['n']:
            _phase(s, 'TEAM_VOTE' if phase == 'DISCUSS' else 'ASSASSINATE', now)
        else:
            s['epoch'] += 1
            s['deadline_at'] = now + s['config']['speech_seconds']
    elif phase == 'TEAM_VOTE':
        s['submitted'][str(seat)] = action_id
        if len(s['submitted']) == s['n']:
            votes = dict(s['submitted'])
            passed = sum(v == 'approve' for v in votes.values()) > s['n'] / 2
            _event(s, 'TEAM_VOTE', votes=votes, approved=passed)
            if passed:
                s['rejections'] = 0
                _phase(s, 'QUEST_PLAY', now)
            else:
                s['rejections'] += 1
                if s['rejections'] == 5:
                    _finish(s, 'EVIL', 'FIVE_REJECTIONS', now)
                else:
                    s['leader'] = s['leader'] % s['n'] + 1
                    s['team'] = []
                    _phase(s, 'PROPOSE', now)
    elif phase == 'QUEST_PLAY':
        s['submitted'][str(seat)] = action_id
        if len(s['submitted']) == len(s['team']):
            fails = sum(v == 'fail' for v in s['submitted'].values())
            threshold = PRESETS[s['n']][2][s['quest']]
            success = fails < threshold
            result = {'quest': s['quest'] + 1, 'team': list(s['team']), 'fails': fails, 'threshold': threshold, 'success': success}
            s['quests'].append(result)
            s['results'].append(success)
            _event(s, 'QUEST', **result)
            if s['results'].count(False) == 3:
                _finish(s, 'EVIL', 'THREE_FAILED_QUESTS', now)
            elif s['results'].count(True) == 3:
                _phase(s, 'FINAL_DISCUSS', now)
            else:
                s['quest'] += 1
                s['leader'] = s['leader'] % s['n'] + 1
                s['team'] = []
                _phase(s, 'PROPOSE', now)
    elif phase == 'ASSASSINATE':
        target = menu[action_id]['target']
        hit = s['roles'][target - 1] == 'MERLIN'
        _event(s, 'ASSASSINATION', assassin=seat, target=target, hit=hit)
        _finish(s, 'EVIL' if hit else 'GOOD', 'MERLIN_FOUND' if hit else 'MERLIN_SURVIVED', now)
    return s, True


def timeout_action(view: dict) -> dict:
    """Published room convention, not an official Avalon rule."""
    menu = view['allowed_actions']
    if not menu:
        raise RuleError('当前没有合法行动')
    ids = {a['id'] for a in menu}
    selected = next((a for a in ('skip', 'reject', 'success') if a in ids), menu[0]['id'])
    return {'request_id': view['request_id'], 'action_id': selected, 'text': ''}
