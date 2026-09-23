"""Opt-in test against a dedicated, disposable PostgreSQL database in CI."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.mark.skipif(not os.getenv('POSTGRES_TEST_URL'), reason='Dedicated PostgreSQL test database not configured')
def test_postgres_migration_transaction_and_restart(monkeypatch):
    url = os.environ['POSTGRES_TEST_URL']
    assert url.startswith('postgresql+psycopg://')
    for key in ('ACCESS_CODE', 'APP_ENV', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_PROFILES_JSON'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('DATABASE_URL', url)
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(cfg, 'head')
    command.check(cfg)
    with TestClient(create_app(url, scheduler=False)) as first:
        session = first.post('/api/sessions', json={'name': 'PostgreSQL 验收'}).json()
        headers = {'Authorization': 'Bearer ' + session['token']}
        response = first.post('/api/rooms', headers=headers, json={
            'num_players': 7, 'host_plays': False,
            'optional_roles': ['PERCIVAL', 'MORGANA', 'OBERON'],
            'seats': [{'kind': 'bot'} for _ in range(7)],
        })
        assert response.status_code == 201, response.text
        code = response.json()['code']
        started = first.post(f'/api/rooms/{code}/start', headers=headers)
        assert started.status_code == 200
        runtime = first.app.state.runtime
        def expire(state):
            state['game']['deadline_at'] = 0
        runtime.db.transact(code, expire)
        first.portal.call(runtime.tick)
        expected = first.get(f'/api/rooms/{code}', headers=headers).json()
        assert expected['game']['phase'] == 'DISCUSS'
        assert expected['game']['private'] is None
        assert 'roles' not in expected['game']
        roles_before = runtime.db.read(code)['game']['roles']
    command.upgrade(cfg, 'head')
    with TestClient(create_app(url, scheduler=False)) as second:
        response = second.get(f'/api/rooms/{code}', headers=headers)
        assert response.status_code == 200
        assert response.json() == expected
        assert second.app.state.runtime.db.read(code)['game']['roles'] == roles_before
