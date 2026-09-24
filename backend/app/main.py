"""Single-worker mobile API, authenticated views, durable rooms and AI scheduler."""

import asyncio
import contextlib
import hmac
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import rules
from .runtime import Runtime
from .storage import Database

log = logging.getLogger('avalon')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class SessionInput(StrictModel):
    name: str = Field(min_length=1, max_length=24)
    access_code: str = Field(default='', max_length=128)


class SeatInput(StrictModel):
    kind: Literal['human', 'llm'] = 'human'
    profile: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def validate_profile(self):
        if self.kind == 'llm' and not self.profile:
            raise ValueError('AI 玩家必须选择可用模型')
        if self.kind == 'human' and self.profile is not None:
            raise ValueError('真人席位不能配置 AI 模型')
        return self


class RoomInput(StrictModel):
    num_players: int = Field(default=7, ge=5, le=10)
    optional_roles: list[str] = Field(default_factory=lambda: ['PERCIVAL', 'MORGANA'], max_length=4)
    seats: list[SeatInput] = Field(min_length=5, max_length=10)
    host_plays: bool = True
    speech_seconds: int = Field(default=60, ge=15, le=180)
    action_seconds: int = Field(default=90, ge=15, le=300)

    @model_validator(mode='after')
    def validate_room(self):
        rules.role_deck(self.num_players, self.optional_roles)
        if len(self.seats) != self.num_players:
            raise ValueError('座位数量必须等于总人数')
        if self.host_plays and self.seats[0].kind != 'human':
            raise ValueError('参赛房主的第一席必须是真人')
        return self


class JoinInput(StrictModel):
    spectate: bool = False


class ActionInput(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    action_id: str = Field(min_length=1, max_length=100)
    text: str = Field(default='', max_length=240)


def seat_of(room: dict, user_id: str) -> int | None:
    return next((s['seat'] for s in room['seats'] if s.get('user_id') == user_id), None)


def is_member(room: dict, user_id: str) -> bool:
    return room['host_id'] == user_id or seat_of(room, user_id) is not None or user_id in room['observers']


def project_room(room: dict, user: dict) -> dict:
    if not is_member(room, user['id']):
        raise HTTPException(403, '请先加入房间')
    seat = seat_of(room, user['id'])
    result = {
        'code': room['code'], 'status': room['status'], 'is_host': room['host_id'] == user['id'],
        'seat': seat, 'config': room['config'], 'lobby_version': room['lobby_version'],
        'ai_issue': room.get('ai_issue'),
        'seats': [{'seat': s['seat'], 'name': s['name'] if s['kind'] in {'human', 'llm'} else f"历史玩家 {s['seat']}",
                   'kind': s['kind'] if s['kind'] in {'human', 'llm'} else 'legacy', 'profile': s['profile']} | {
            'occupied': s['kind'] != 'human' or s.get('user_id') is not None,
            'is_you': s.get('user_id') == user['id'],
        } for s in room['seats']],
        'game': rules.observe(room['game'], seat) if room['game'] else None,
    }
    if result['game'] and room['status'] != 'PLAYING':
        result['game']['allowed_actions'] = []
        result['game']['deadline_at'] = None
    if room['status'] == 'FINISHED':
        result['metrics'] = {k: v for k, v in room['metrics'].items() if k != 'fallbacks'}
    return result


def create_app(database_url: str | None = None, *, scheduler: bool = True) -> FastAPI:
    url = database_url or os.getenv('DATABASE_URL', 'sqlite:///./avalon.db')
    db = Database(url)
    runtime = Runtime(db)
    access_code = os.getenv('ACCESS_CODE', '')
    production = os.getenv('APP_ENV', 'development') == 'production'
    if production and not access_code:
        raise RuntimeError('Production requires ACCESS_CODE to gate guest registration')

    @asynccontextmanager
    async def lifespan(app):
        if url.startswith('sqlite'):
            db.initialize()
        db.retire_legacy_rooms()
        # PostgreSQL schema is managed by `alembic upgrade head` before startup.
        if scheduler:
            runtime.loop_task = asyncio.create_task(runtime.drive())
        yield
        await runtime.close()

    app = FastAPI(title='Avalon Native API', version='0.2.0', lifespan=lifespan)
    app.state.runtime = runtime
    rate: dict[tuple, deque] = defaultdict(deque)

    @app.middleware('http')
    async def limits(request: Request, call_next):
        path = request.url.path
        try:
            length = int(request.headers.get('content-length', '0') or 0)
        except ValueError:
            return JSONResponse({'detail': '无效请求长度'}, status_code=400)
        if length > 16384:
            return JSONResponse({'detail': '请求过大'}, status_code=413)
        bucket = 'sessions' if path == '/api/sessions' and request.method == 'POST' else 'general'
        identity = (request.client.host if request.client else 'unknown', bucket)
        now = time.monotonic()
        events = rate[identity]
        while events and events[0] < now - 60:
            events.popleft()
        if len(events) >= (20 if bucket == 'sessions' else 600):
            return JSONResponse({'detail': '请求过于频繁'}, status_code=429, headers={'Retry-After': '60'})
        events.append(now)
        if len(rate) > 5000:
            for key in list(rate):
                if not rate[key] or rate[key][-1] < now - 60:
                    del rate[key]
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(rules.RuleError)
    async def rule_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(LookupError)
    async def missing(request, exc):
        return JSONResponse({'detail': '房间不存在'}, status_code=404)

    def auth(request: Request) -> dict:
        header = request.headers.get('authorization', '')
        user = db.authenticate(header[7:]) if header.startswith('Bearer ') else None
        if not user:
            raise HTTPException(401, '会话无效或已过期，请重新登录')
        return user

    User = Annotated[dict, Depends(auth)]

    @app.get('/healthz')
    def health():
        return {'status': 'ok', 'version': '0.2.0'}

    @app.get('/api/config')
    def config():
        return {'min_players': 5, 'max_players': 10, 'roles': rules.ROLE_NAMES,
                'presets': {str(n): {'good': p[0][0], 'evil': p[0][1], 'quest_sizes': p[1], 'fail_thresholds': p[2]} for n, p in rules.PRESETS.items()},
                'profiles': [{'id': p.id, 'label': p.label} for p in runtime.profiles.values()],
                'requires_access_code': bool(access_code), 'player_kinds': ['human', 'llm'], 'ai_failure_policy': 'pause'}

    @app.post('/api/sessions', status_code=201)
    def register(data: SessionInput):
        if access_code and not hmac.compare_digest(data.access_code.encode(), access_code.encode()):
            raise HTTPException(403, '服务器邀请码不正确')
        if not data.name.strip():
            raise HTTPException(422, '昵称不能为空')
        return db.create_guest(data.name.strip())

    @app.get('/api/me')
    def me(user: User):
        return user

    @app.delete('/api/sessions', status_code=204)
    def logout(user: User):
        db.revoke(user['id'])

    @app.get('/api/rooms')
    def my_rooms(user: User):
        return [{'code': r['code'], 'status': r['status'], 'num_players': r['config']['num_players']}
                for r in db.list_states(limit=200) if is_member(r, user['id'])][:30]

    @app.post('/api/rooms', status_code=201)
    def new_room(data: RoomInput, user: User):
        if sum(len(db.list_states(status, 100)) for status in ('PLAYING', 'PAUSED_AI', 'LOBBY')) >= 100:
            raise HTTPException(503, '当前房间容量已满')
        for seat in data.seats:
            if seat.kind == 'llm' and seat.profile not in runtime.profiles:
                raise HTTPException(422, '选择的模型未在服务器配置')
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        while db.read(code):
            code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        settings = data.model_dump(exclude={'seats', 'host_plays'})
        seats = [{'seat': i + 1, 'kind': s.kind, 'profile': s.profile if s.kind == 'llm' else None,
                  'name': f'AI 玩家 {i + 1}' if s.kind == 'llm' else '等待好友加入',
                  'user_id': None} for i, s in enumerate(data.seats)]
        if data.host_plays:
            seats[0].update(user_id=user['id'], name=user['name'])
        room = {'code': code, 'host_id': user['id'], 'status': 'LOBBY', 'config': settings, 'seats': seats,
                'observers': [], 'game': None, 'lobby_version': 1, 'ai_generation': 0, 'ai_issue': None,
                'metrics': dict.fromkeys(['reserved_calls', 'calls', 'errors', 'ai_pauses', 'input_tokens', 'output_tokens', 'timeouts'], 0)}
        db.insert_room(room)
        return project_room(room, user)

    @app.post('/api/rooms/{code}/join')
    async def join(code: str, data: JoinInput, user: User):
        code = code.upper()
        runtime.get(code)
        async with runtime.locks[code]:
            def mutate(room):
                if is_member(room, user['id']):
                    return project_room(room, user)
                if data.spectate:
                    if len(room['observers']) >= 20:
                        raise HTTPException(409, '观战席已满')
                    room['observers'].append(user['id'])
                else:
                    if room['status'] != 'LOBBY':
                        raise HTTPException(409, '对局已开始，只能观战')
                    seat = next((s for s in room['seats'] if s['kind'] == 'human' and not s['user_id']), None)
                    if not seat:
                        raise HTTPException(409, '真人席已满，可以选择观战')
                    seat.update(user_id=user['id'], name=user['name'])
                room['lobby_version'] += 1
                return project_room(room, user)
            result = db.transact(code, mutate)
        runtime.notify(code)
        return result

    @app.get('/api/rooms/{code}')
    def get_room(code: str, user: User):
        return project_room(runtime.get(code.upper()), user)

    @app.post('/api/rooms/{code}/start')
    async def start(code: str, user: User):
        code = code.upper()
        runtime.get(code)
        async with runtime.locks[code]:
            def mutate(room):
                if room['host_id'] != user['id']:
                    raise HTTPException(403, '只有房主可以开始')
                if room['status'] == 'ARCHIVED':
                    raise HTTPException(409, '旧版房间已只读归档，请创建新房间')
                if room['game']:
                    return project_room(room, user)
                if any(s['kind'] == 'llm' and s['profile'] not in runtime.profiles for s in room['seats']):
                    raise HTTPException(409, 'AI 服务未配置，暂时无法开局')
                if any(s['kind'] == 'human' and not s['user_id'] for s in room['seats']):
                    raise HTTPException(409, '请等待真人席全部加入')
                room['game'] = rules.create_game(room['config'])
                room['status'] = 'PLAYING'
                room['lobby_version'] += 1
                return project_room(room, user)
            result = db.transact(code, mutate)
        runtime.notify(code)
        return result

    @app.post('/api/rooms/{code}/actions')
    async def action(code: str, command: ActionInput, user: User):
        await runtime.action(code.upper(), user, command)
        return project_room(runtime.get(code.upper()), user)

    @app.post('/api/rooms/{code}/ai/retry')
    async def retry_ai(code: str, user: User):
        await runtime.resume(code.upper(), user['id'])
        return project_room(runtime.get(code.upper()), user)

    @app.websocket('/ws/rooms/{code}')
    async def room_socket(ws: WebSocket, code: str):
        code = code.upper()
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        user = None
        registered = False
        incoming = None
        notified = None
        try:
            # Authenticate in first frame, never in logged URL query parameters.
            first = await asyncio.wait_for(ws.receive_json(), 10)
            token = first.get('token', '') if isinstance(first, dict) else ''
            user = db.authenticate(token) if isinstance(token, str) else None
            if not user or runtime.ws_counts[user['id']] >= 3:
                await ws.close(code=1008)
                return
            project_room(runtime.get(code), user)
            runtime.ws_counts[user['id']] += 1
            runtime.queues[code].add(queue)
            registered = True
            previous = None
            incoming = asyncio.create_task(ws.receive())
            while True:
                if not db.authenticate(token):
                    await ws.close(code=1008)
                    return
                snapshot = project_room(runtime.get(code), user)
                if snapshot != previous:
                    await ws.send_json({'type': 'snapshot', 'data': snapshot, 'server_time': time.time()})
                    previous = snapshot
                notified = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({incoming, notified}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
                if incoming in done:
                    break  # Disconnect or unexpected input: actions use authenticated HTTP.
                if notified not in done:
                    notified.cancel()
                    await asyncio.gather(notified, return_exceptions=True)
                    await ws.send_json({'type': 'heartbeat', 'server_time': time.time()})
        except asyncio.CancelledError:
            pass  # ASGI shutdown or client cancellation; clean up below.
        except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, ValueError, HTTPException):
            with contextlib.suppress(Exception):
                await ws.close(code=1008)
        finally:
            # Unregister synchronously: cancellation must never retain a seat's socket quota.
            if registered:
                runtime.queues[code].discard(queue)
                runtime.ws_counts[user['id']] -= 1
            for task in (incoming, notified):
                if task is not None:
                    task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*(t for t in (incoming, notified) if t is not None), return_exceptions=True)

    return app


app = create_app()
