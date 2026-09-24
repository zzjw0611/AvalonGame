import asyncio
import copy
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import rules
from app.agents import ModelAgent, ModelUnavailable
from app.main import create_app
from tests.test_api import client, create, guest
from tests.simulation import configure_mock


def start_ai_game(c, headers):
    room = create(c, headers, humans=0, host_plays=False)
    code = room['code']
    assert c.post(f'/api/rooms/{code}/start', headers=headers).status_code == 200
    return code


def drive_current(c, code):
    rt = c.app.state.runtime
    room = rt.get(code)
    seat = next(s['seat'] for s in room['seats'] if rules.actions(room['game'], s['seat']))
    c.portal.call(rt._agent_turn, code, seat, rules.request_id(room['game'], seat), room.get('ai_generation', 0))


def test_removed_kind_rejected_even_from_old_client(client):
    _, h = guest(client)
    response = client.post('/api/rooms', headers=h, json={'num_players': 5, 'seats': [{'kind': 'human'}] + [{'kind': 'bot'}] * 4})
    assert response.status_code == 422
    assert client.get('/api/config').json()['player_kinds'] == ['human', 'llm']
    assert not hasattr(__import__('app.agents', fromlist=['bot_decide']), 'bot_decide')


@pytest.mark.parametrize('seat', [{'kind': 'human', 'profile': 'test'}, {'kind': 'llm'}, {'kind': 'unknown'}])
def test_invalid_seat_configuration(client, seat):
    _, h = guest(client)
    response = client.post('/api/rooms', headers=h, json={'num_players': 5, 'seats': [{'kind': 'human'}] + [seat] * 4})
    assert response.status_code == 422


def test_without_models_all_human_room_still_works(client):
    rt = client.app.state.runtime
    rt.profiles.clear()
    _, h = guest(client)
    room = create(client, h, humans=5)
    assert all(s['kind'] == 'human' for s in room['seats'])
    assert client.get('/api/config').json()['profiles'] == []


def test_model_failure_pauses_without_substituting_a_move(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    rt.agent = ModelAgent(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    before = copy.deepcopy(rt.get(code)['game'])
    drive_current(client, code)
    state = rt.get(code)
    assert state['status'] == 'PAUSED_AI'
    assert state['game']['deadline_at'] is None
    assert state['game']['history'] == before['history']
    assert state['game']['receipts'] == before['receipts']
    view = client.get(f'/api/rooms/{code}', headers=h).json()
    assert view['game']['allowed_actions'] == []
    assert view['ai_issue']['code'] == 'PROVIDER_ERROR'
    assert 'seat' not in view['ai_issue']
    assert state['metrics']['calls'] == 2 and state['metrics']['ai_pauses'] == 1
    assert 'fallbacks' not in state['metrics']
    # Persisted pause is not polled into another paid retry.
    client.portal.call(rt.tick)
    assert rt.get(code)['metrics']['calls'] == 2


def test_host_retry_keeps_votes_and_budget(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    def prepare(s):
        g = s['game']; g['phase'] = 'TEAM_VOTE'; g['epoch'] += 1
        g['team'] = [1, 2]; g['submitted'] = {'1': 'approve'}
        g['deadline_at'] = time.time() + 45
        rt._pause(s, 'PROVIDER_ERROR')
    rt.db.transact(code, prepare)
    _, other = guest(client, 'observer')
    assert client.post(f'/api/rooms/{code}/ai/retry', headers=other).status_code == 403
    old = rt.get(code)
    result = client.post(f'/api/rooms/{code}/ai/retry', headers=h)
    assert result.status_code == 200
    new = rt.get(code)
    assert new['status'] == 'PLAYING'
    assert new['game']['submitted'] == {'1': 'approve'}
    assert new['game']['epoch'] == old['game']['epoch']
    assert new['metrics']['reserved_calls'] == old['metrics']['reserved_calls']
    assert new['game']['deadline_at'] > time.time()
    assert new['ai_generation'] > old['ai_generation']


def test_retry_does_not_reset_exhausted_budget(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    rt.budget = 0
    drive_current(client, code)
    assert rt.get(code)['ai_issue']['code'] == 'BUDGET_EXHAUSTED'
    assert rt.get(code)['metrics']['calls'] == 0
    assert client.post(f'/api/rooms/{code}/ai/retry', headers=h).status_code == 409
    assert rt.get(code)['metrics']['reserved_calls'] == 0


def test_missing_profile_pauses_not_scripted(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    rt.profiles.clear()
    drive_current(client, code)
    assert rt.get(code)['ai_issue']['code'] == 'NOT_CONFIGURED'
    assert not rt.get(code)['game']['history']
    assert client.post(f'/api/rooms/{code}/ai/retry', headers=h).status_code == 409


def test_ai_deadline_pauses_instead_of_timeout_card(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    rt.db.transact(code, lambda s: s['game'].__setitem__('deadline_at', 0))
    client.portal.call(rt.tick)
    state = rt.get(code)
    assert state['status'] == 'PAUSED_AI'
    assert state['game']['phase'] == 'PROPOSE' and not state['game']['history']
    assert state['metrics']['timeouts'] == 0


def test_one_legal_card_uses_same_model_path(client):
    rt = client.app.state.runtime
    g = rules.create_game({'num_players': 5, 'optional_roles': [], 'speech_seconds': 60, 'action_seconds': 90})
    good = next(i + 1 for i, role in enumerate(g['roles']) if role in rules.GOOD)
    g['phase'] = 'QUEST_PLAY'; g['team'] = [good]
    view = rules.observe(g, good)
    assert len(view['allowed_actions']) == 1
    failing = ModelAgent(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    with pytest.raises(ModelUnavailable):
        client.portal.call(failing.decide, rt.profiles['test'], view)
    cmd, stats = client.portal.call(rt.agent.decide, rt.profiles['test'], view)
    assert cmd['action_id'] == 'success' and stats['calls'] == 1


def test_stale_inflight_result_after_pause_resume_cannot_commit(client):
    _, h = guest(client)
    code = start_ai_game(client, h)
    rt = client.app.state.runtime
    room = rt.get(code); seat = room['game']['leader']; req = rules.request_id(room['game'], seat)
    original_agent = rt.agent
    class PausingAgent:
        async def decide(self, profile, view):
            rt.db.transact(code, lambda state: rt._pause(state, 'PROVIDER_ERROR'))
            await rt.resume(code, rt.get(code)['host_id'])
            return await original_agent.decide(profile, view)
    rt.agent = PausingAgent()
    client.portal.call(rt._agent_turn, code, seat, req, 0)
    state = rt.get(code)
    assert state['status'] == 'PLAYING'
    assert state['game']['history'] == [] and state['game']['receipts'] == {}


def test_pause_survives_restart_and_legacy_rooms_are_archived(tmp_path, monkeypatch):
    monkeypatch.delenv('ACCESS_CODE', raising=False)
    url = f'sqlite:///{tmp_path}/retire.db'
    with TestClient(create_app(url, scheduler=False)) as c:
        _, h = guest(c)
        code = start_ai_game(c, h)
        rt = c.app.state.runtime
        rt.db.transact(code, lambda state: rt._pause(state, 'PROVIDER_ERROR'))
        paused = c.get(f'/api/rooms/{code}', headers=h).json()
        legacy = create(c, h, humans=1)
        legacy_code = legacy['code']
        rt.db.transact(legacy_code, lambda state: state['seats'][1].__setitem__('kind', 'bot'))
    with TestClient(create_app(url, scheduler=False)) as c:
        assert c.get(f'/api/rooms/{code}', headers=h).json() == paused
        archived = c.get(f'/api/rooms/{legacy_code}', headers=h).json()
        assert archived['status'] == 'ARCHIVED'
        assert archived['seats'][1]['kind'] == 'legacy'
        assert c.post(f'/api/rooms/{legacy_code}/start', headers=h).status_code == 409


def test_players_cannot_act_while_paused(client):
    _, h = guest(client)
    room = create(client, h)
    code = room['code']; client.post(f'/api/rooms/{code}/start', headers=h)
    rt = client.app.state.runtime
    def prepare(s):
        s['game']['phase'] = 'TEAM_VOTE'; s['game']['epoch'] += 1
        rt._pause(s, 'PROVIDER_ERROR')
    rt.db.transact(code, prepare)
    g = rt.get(code)['game']
    response = client.post(f'/api/rooms/{code}/actions', headers=h, json={'request_id': rules.request_id(g, 1), 'action_id': 'approve'})
    assert response.status_code == 409 and rt.get(code)['game']['submitted'] == {}
