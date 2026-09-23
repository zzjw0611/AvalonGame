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
from .agents import ModelAgent, bot_decide, load_profiles
from .storage import Database

log = logging.getLogger('avalon')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class SessionInput(StrictModel):
    name: str = Field(min_length=1, max_length=24)
    access_code: str = Field(default='', max_length=128)


class SeatInput(StrictModel):
    kind: Literal['human', 'bot', 'llm'] = 'bot'
    profile: str | None = Field(default=None, max_length=64)


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
        'seats': [{k: s[k] for k in ('seat', 'name', 'kind', 'profile')} | {
            'occupied': s['kind'] != 'human' or s.get('user_id') is not None,
            'is_you': s.get('user_id') == user['id'],
        } for s in room['seats']],
        'game': rules.observe(room['game'], seat) if room['game'] else None,
    }
    if room['status'] == 'FINISHED':
        result['metrics'] = room['metrics']
    return result


class Runtime:
    def __init__(self, database: Database):
        self.db = database
        self.profiles = load_profiles()
        self.agent = ModelAgent(timeout=float(os.getenv('LLM_TIMEOUT_SECONDS', '25')),
                                max_tokens=int(os.getenv('LLM_MAX_TOKENS', '450')))
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.pending: dict[tuple[str, str], asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(int(os.getenv('LLM_CONCURRENCY', '4')))
        self.bot_delay = float(os.getenv('BOT_DELAY_SECONDS', '1.2'))
        self.budget = int(os.getenv('LLM_CALL_BUDGET', '300'))
        self.loop_task: asyncio.Task | None = None
        self.ws_counts: dict[str, int] = defaultdict(int)

    def notify(self, code: str) -> None:
        for queue in self.queues.get(code, set()):
            if queue.empty():
                queue.put_nowait(True)

    def get(self, code: str) -> dict:
        room = self.db.read(code)
        if not room:
            raise HTTPException(404, '房间不存在')
        return room

    async def action(self, code: str, user: dict, command: ActionInput) -> dict:
        self.get(code)
        async with self.locks[code]:
            def mutate(room):
                seat = seat_of(room, user['id'])
                if seat is None or not room['game']:
                    raise HTTPException(403, '当前没有可操作的参赛座位')
                game = room['game']
                if command.request_id not in game['receipts'] and game['deadline_at'] is not None and game['deadline_at'] <= time.time():
                    raise rules.RuleError('操作已超时，正在刷新阶段')
                new, changed = rules.apply(game, seat, command.request_id, command.action_id, command.text)
                room['game'] = new
                if new['winner']:
                    room['status'] = 'FINISHED'
                return project_room(room, user), changed
            view, changed = self.db.transact(code, mutate)
        if changed:
            self.notify(code)
        return view

    async def _agent_turn(self, code: str, seat: int, req: str) -> None:
        await asyncio.sleep(self.bot_delay)
        async with self.semaphore:
            async with self.locks[code]:
                room = self.get(code)
                game = room['game']
                if not game or rules.request_id(game, seat) != req or not rules.actions(game, seat) or (game['deadline_at'] is not None and game['deadline_at'] <= time.time()):
                    return
                view = rules.observe(game, seat)
                record = room['seats'][seat - 1]
                profile = self.profiles.get(record['profile']) if record['kind'] == 'llm' else None
                use_llm = profile is not None and len(view['allowed_actions']) > 1 and room['metrics']['reserved_calls'] + 2 <= self.budget
                if use_llm:
                    self.db.transact(code, lambda state: state['metrics'].__setitem__('reserved_calls', state['metrics']['reserved_calls'] + 2))
            # Database transaction AND room lock are released while awaiting API.
            if use_llm:
                command, stats = await self.agent.decide(profile, view)
            else:
                command = bot_decide(view)
                stats = {'calls': 0, 'errors': 0, 'fallbacks': int(record['kind'] == 'llm' and len(view['allowed_actions']) > 1),
                         'input_tokens': 0, 'output_tokens': 0}
            async with self.locks[code]:
                def commit(state):
                    for key, value in stats.items():
                        state['metrics'][key] += value
                    if state['game']['deadline_at'] is not None and state['game']['deadline_at'] <= time.time():
                        return False
                    try:
                        new, changed = rules.apply(state['game'], seat, command['request_id'], command['action_id'], command['text'])
                    except rules.RuleError:
                        return False  # A timeout may already have advanced the phase.
                    state['game'] = new
                    if new['winner']:
                        state['status'] = 'FINISHED'
                    return changed
                self.db.transact(code, commit)
            self.notify(code)

    async def tick(self) -> None:
        for room in self.db.list_states('PLAYING', 100):
            code, game = room['code'], room['game']
            if game['deadline_at'] is not None and game['deadline_at'] <= time.time():
                async with self.locks[code]:
                    def expire(state):
                        current = state['game']
                        if current['phase'] == 'GAME_OVER' or current['deadline_at'] is None or current['deadline_at'] > time.time():
                            return
                        epoch = current['epoch']
                        for seat in range(1, current['n'] + 1):
                            if current['epoch'] != epoch:
                                break
                            view = rules.observe(current, seat)
                            if view['allowed_actions']:
                                cmd = rules.timeout_action(view)
                                current, _ = rules.apply(current, seat, cmd['request_id'], cmd['action_id'], cmd['text'])
                                state['metrics']['timeouts'] += 1
                        state['game'] = current
                        if current['winner']:
                            state['status'] = 'FINISHED'
                    self.db.transact(code, expire)
                self.notify(code)
                continue
            for seat in room['seats']:
                if seat['kind'] == 'human' or not rules.actions(game, seat['seat']):
                    continue
                req = rules.request_id(game, seat['seat'])
                key = (code, req)
                if key not in self.pending:
                    task = asyncio.create_task(self._agent_turn(code, seat['seat'], req))
                    self.pending[key] = task
                    def done(completed, key=key):
                        self.pending.pop(key, None)
                        if not completed.cancelled() and completed.exception():
                            log.error('agent task failed: %s', type(completed.exception()).__name__)
                    task.add_done_callback(done)

    async def drive(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:
                log.error('scheduler iteration failed: %s', type(exc).__name__)
            await asyncio.sleep(0.5)

    async def close(self) -> None:
        tasks = list(self.pending.values()) + ([self.loop_task] if self.loop_task else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.db.engine.dispose()


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
        # PostgreSQL schema is managed by `alembic upgrade head` before startup.
        if scheduler:
            runtime.loop_task = asyncio.create_task(runtime.drive())
        yield
        await runtime.close()

    app = FastAPI(title='Avalon Native API', version='0.1.0', lifespan=lifespan)
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
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/api/config')
    def config():
        return {'min_players': 5, 'max_players': 10, 'roles': rules.ROLE_NAMES,
                'presets': {str(n): {'good': p[0][0], 'evil': p[0][1], 'quest_sizes': p[1], 'fail_thresholds': p[2]} for n, p in rules.PRESETS.items()},
                'profiles': [{'id': p.id, 'label': p.label} for p in runtime.profiles.values()],
                'requires_access_code': bool(access_code)}

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
        if len(db.list_states('PLAYING', 100)) >= 100 or len(db.list_states('LOBBY', 100)) >= 100:
            raise HTTPException(503, '当前房间容量已满')
        for seat in data.seats:
            if seat.kind == 'llm' and seat.profile not in runtime.profiles:
                raise HTTPException(422, '选择的模型未在服务器配置')
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        while db.read(code):
            code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
        settings = data.model_dump(exclude={'seats', 'host_plays'})
        seats = [{'seat': i + 1, 'kind': s.kind, 'profile': s.profile if s.kind == 'llm' else None,
                  'name': f'规则机器人 {i + 1}' if s.kind == 'bot' else (f'模型玩家 {i + 1}' if s.kind == 'llm' else '等待加入'),
                  'user_id': None} for i, s in enumerate(data.seats)]
        if data.host_plays:
            seats[0].update(user_id=user['id'], name=user['name'])
        room = {'code': code, 'host_id': user['id'], 'status': 'LOBBY', 'config': settings, 'seats': seats,
                'observers': [], 'game': None, 'lobby_version': 1,
                'metrics': dict.fromkeys(['reserved_calls', 'calls', 'errors', 'fallbacks', 'input_tokens', 'output_tokens', 'timeouts'], 0)}
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
                if room['game']:
                    return project_room(room, user)
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
        return await runtime.action(code.upper(), user, command)

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
