import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import rules
from app.agents import ModelAgent, ModelProfile, ModelUnavailable
from tests.simulation import configure_mock
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ('LLM_API_KEY', 'LLM_MODEL', 'LLM_PROFILES_JSON', 'ACCESS_CODE', 'APP_ENV'):
        monkeypatch.delenv(key, raising=False)
    app = create_app(f'sqlite:///{tmp_path}/game.db', scheduler=False)
    with TestClient(app) as c:
        configure_mock(c.app.state.runtime)
        yield c


def guest(c, name='测试玩家'):
    response = c.post('/api/sessions', json={'name': name})
    assert response.status_code == 201
    data = response.json()
    return data, {'Authorization': 'Bearer ' + data['token']}


def create(c, headers, n=5, humans=1, host_plays=True):
    if humans < n:
        configure_mock(c.app.state.runtime)
    response = c.post('/api/rooms', headers=headers, json={
        'num_players': n, 'host_plays': host_plays,
        'seats': [{'kind': 'human'} if i < humans else {'kind': 'llm', 'profile': 'test'} for i in range(n)],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_and_own_room_projection(client):
    owner, headers = guest(client)
    room = create(client, headers)
    code = room['code']
    assert 'user_id' not in json.dumps(room)
    assert 'host_id' not in room
    assert client.get(f'/api/rooms/{code}').status_code == 401
    other, other_headers = guest(client, 'other')
    assert client.get(f'/api/rooms/{code}', headers=other_headers).status_code == 403
    assert client.post(f'/api/rooms/{code}/start', headers=other_headers).status_code == 403
    started = client.post(f'/api/rooms/{code}/start', headers=headers).json()
    assert started['game']['private']['seat'] == 1
    assert 'roles' not in started['game']
    assert 'receipts' not in started['game']
    assert 'revealed_roles' not in started['game']
    assert isinstance(started['game']['submitted'], bool)
    public = client.post(f'/api/rooms/{code}/join', headers=other_headers, json={'spectate': True}).json()
    assert public['seat'] is None and public['game']['private'] is None
    assert public['game']['allowed_actions'] == []


def test_seat_cannot_be_spoofed_and_humans_must_join(client):
    _, headers = guest(client)
    room = create(client, headers, humans=5)
    code = room['code']
    assert client.post(f'/api/rooms/{code}/start', headers=headers).status_code == 409
    participants = [headers]
    for i in range(4):
        _, h = guest(client, str(i))
        participants.append(h)
        assert client.post(f'/api/rooms/{code}/join', headers=h, json={}).status_code == 200
    assert client.post(f'/api/rooms/{code}/start', headers=headers).status_code == 200
    response = client.post(f'/api/rooms/{code}/actions', headers=headers,
                           json={'request_id': 'x', 'action_id': 'approve', 'seat': 2})
    assert response.status_code == 422
    assert client.post(f'/api/rooms/{code}/actions', headers=headers,
                       json={'request_id': 'x', 'action_id': 'approve'}).status_code == 409


def test_http_secret_ballot_and_retry(client):
    _, headers = guest(client)
    room = create(client, headers, humans=5)
    code = room['code']
    users = [headers]
    for i in range(4):
        _, h = guest(client, f'p{i}')
        users.append(h)
        client.post(f'/api/rooms/{code}/join', headers=h, json={})
    client.post(f'/api/rooms/{code}/start', headers=headers)
    rt = client.app.state.runtime
    def to_vote(state):
        g = state['game']; g['phase'] = 'TEAM_VOTE'; g['epoch'] += 1
        g['team'] = [1, 2]; g['deadline_at'] = time.time() + 90
    rt.db.transact(code, to_vote)
    before = client.get(f'/api/rooms/{code}', headers=users[1]).json()
    mine = client.get(f'/api/rooms/{code}', headers=headers).json()
    body = {'request_id': mine['game']['request_id'], 'action_id': 'approve', 'text': ''}
    result = client.post(f'/api/rooms/{code}/actions', headers=headers, json=body)
    assert result.status_code == 200 and result.json()['game']['submitted']
    assert client.get(f'/api/rooms/{code}', headers=users[1]).json() == before
    assert client.post(f'/api/rooms/{code}/actions', headers=headers, json=body).json() == result.json()
    assert client.post(f'/api/rooms/{code}/actions', headers=headers, json={**body, 'action_id': 'reject'}).status_code == 409


def test_ws_reconnection_and_auth(client):
    session, headers = guest(client)
    room = create(client, headers)
    code = room['code']
    client.post(f'/api/rooms/{code}/start', headers=headers)
    with client.websocket_connect(f'/ws/rooms/{code}') as ws:
        ws.send_json({'token': session['token']})
        first = ws.receive_json()
        assert first['type'] == 'snapshot'
        assert first['data']['game']['private']['seat'] == 1
    with client.websocket_connect(f'/ws/rooms/{code}') as ws:
        ws.send_json({'token': session['token']})
        second = ws.receive_json()
        assert second['data'] == first['data']
    with client.websocket_connect(f'/ws/rooms/{code}') as ws:
        ws.send_json({'token': 'not-a-valid-token'})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


@pytest.mark.parametrize('n', range(5, 11))
def test_full_api_mock_llm_games(client, n):
    _, headers = guest(client)
    room = create(client, headers, n=n, humans=0, host_plays=False)
    code = room['code']
    started = client.post(f'/api/rooms/{code}/start', headers=headers).json()
    assert started['game']['private'] is None
    rt = client.app.state.runtime
    for _ in range(600):
        client.portal.call(rt.tick)
        client.portal.call(asyncio.sleep, 0.003)
        state = client.get(f'/api/rooms/{code}', headers=headers).json()
        if state['status'] == 'FINISHED':
            assert state['game']['winner'] in {'GOOD', 'EVIL'}
            assert len(state['game']['revealed_roles']) == n
            assert state['metrics']['calls'] > 0
            assert 'fallbacks' not in state['metrics']
            break
    else:
        pytest.fail('mock LLM game did not finish')


def test_restart_restores_roles_and_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv('ACCESS_CODE', raising=False)
    path = f'sqlite:///{tmp_path}/restart.db'
    with TestClient(create_app(path, scheduler=False)) as first:
        _, headers = guest(first)
        room = create(first, headers)
        code = room['code']
        expected = first.post(f'/api/rooms/{code}/start', headers=headers).json()
    with TestClient(create_app(path, scheduler=False)) as second:
        assert second.get(f'/api/rooms/{code}', headers=headers).json() == expected


def test_deadline_and_timeout_are_server_owned(client):
    _, headers = guest(client)
    room = create(client, headers)
    code = room['code']
    client.post(f'/api/rooms/{code}/start', headers=headers)
    rt = client.app.state.runtime
    def expire(state):
        state['game']['leader'] = 1
        state['game']['deadline_at'] = 0
    rt.db.transact(code, expire)
    view = client.get(f'/api/rooms/{code}', headers=headers).json()['game']
    action = {'request_id': view['request_id'], 'action_id': view['allowed_actions'][0]['id']}
    assert client.post(f'/api/rooms/{code}/actions', headers=headers, json=action).status_code == 409
    client.portal.call(rt.tick)
    assert rt.db.read(code)['game']['phase'] == 'DISCUSS'
    assert rt.db.read(code)['metrics']['timeouts'] == 1


def test_model_configuration_validation_and_body_limit(client):
    _, headers = guest(client)
    response = client.post('/api/rooms', headers=headers, json={'num_players': 5,
        'seats': [{'kind': 'human'}] + [{'kind': 'llm', 'profile': 'not-configured'}] * 4})
    assert response.status_code == 422
    assert client.post('/api/sessions', content='x' * 20000).status_code == 413
    client.delete('/api/sessions', headers=headers)
    assert client.get('/api/me', headers=headers).status_code == 401


def test_invitation_gate_and_production_config(monkeypatch, tmp_path):
    monkeypatch.setenv('ACCESS_CODE', 'a-long-test-invitation-code')
    with TestClient(create_app(f'sqlite:///{tmp_path}/gate.db', scheduler=False)) as c:
        assert c.post('/api/sessions', json={'name': 'x'}).status_code == 403
        assert c.post('/api/sessions', json={'name': 'x', 'access_code': 'a-long-test-invitation-code'}).status_code == 201
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('ACCESS_CODE')
    with pytest.raises(RuntimeError):
        create_app('sqlite:///:memory:', scheduler=False)


def test_model_adapter_repairs_then_validates():
    g = rules.create_game({'num_players': 5, 'optional_roles': [], 'speech_seconds': 60, 'action_seconds': 90})
    view = rules.observe(g, g['leader'])
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        text = 'bad JSON' if len(calls) == 1 else json.dumps({'request_id': view['request_id'], 'action_id': view['allowed_actions'][0]['id'], 'text': ''})
        return httpx.Response(200, json={'choices': [{'message': {'content': text}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})
    agent = ModelAgent(transport=httpx.MockTransport(respond))
    profile = ModelProfile('test', 'Test', 'https://model.invalid/v1', 'test-model', 'TEST_KEY_NOT_REAL')
    cmd, stats = asyncio.run(agent.decide(profile, view))
    assert cmd['action_id'] in {a['id'] for a in view['allowed_actions']}
    assert stats['calls'] == 2 and stats['errors'] == 1 and 'fallbacks' not in stats
    assert stats['input_tokens'] == 20
    assert 'TEST_KEY_NOT_REAL' not in repr(profile)
    assert all('response_format' not in payload for payload in calls)


def test_model_adapter_raises_on_provider_failure():
    g = rules.create_game({'num_players': 5, 'optional_roles': [], 'speech_seconds': 60, 'action_seconds': 90})
    view = rules.observe(g, g['leader'])
    agent = ModelAgent(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    profile = ModelProfile('test', 'Test', 'https://model.invalid/v1', 'test-model', 'TEST_KEY_NOT_REAL')
    with pytest.raises(ModelUnavailable) as error:
        asyncio.run(agent.decide(profile, view))
    assert error.value.stats['calls'] == 2
    assert 'fallbacks' not in error.value.stats
