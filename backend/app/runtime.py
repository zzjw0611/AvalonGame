"""Single-worker scheduler. LLM failures pause the room, never simulate a player."""
import asyncio
import logging
import os
import time
from collections import defaultdict

from fastapi import HTTPException

from . import rules
from .agents import ModelAgent, ModelUnavailable, load_profiles
from .storage import Database

log = logging.getLogger('avalon')
ISSUES = {
    'PROVIDER_ERROR': 'AI 服务暂不可用，对局已暂停。房主可稍后重试。',
    'NOT_CONFIGURED': 'AI 服务未配置，对局已暂停，请联系管理员。',
    'BUDGET_EXHAUSTED': '本局 AI 调用额度已用完，对局已暂停，请联系管理员。',
    'TIMEOUT': 'AI 未能在时限内完成行动，对局已暂停。房主可稍后重试。',
}


class Runtime:
    def __init__(self, database: Database):
        self.db = database
        self.profiles = load_profiles()
        self.agent = ModelAgent(timeout=float(os.getenv('LLM_TIMEOUT_SECONDS', '25')),
                                max_tokens=int(os.getenv('LLM_MAX_TOKENS', '450')))
        self.locks = defaultdict(asyncio.Lock)
        self.queues = defaultdict(set)
        self.pending = {}
        self.semaphore = asyncio.Semaphore(max(1, int(os.getenv('LLM_CONCURRENCY', '4'))))
        self.ai_delay = max(0, float(os.getenv('AI_DELAY_SECONDS', '0.6')))
        self.budget = max(0, int(os.getenv('LLM_CALL_BUDGET', '300')))
        self.loop_task = None
        self.ws_counts = defaultdict(int)

    def notify(self, code):
        for queue in self.queues.get(code, set()):
            if queue.empty():
                queue.put_nowait(True)

    def get(self, code):
        room = self.db.read(code)
        if not room:
            raise HTTPException(404, '房间不存在')
        return room

    @staticmethod
    def _pause(state, reason):
        if state['status'] != 'PLAYING':
            return
        g = state['game']
        seconds = g['config']['speech_seconds'] if g['phase'] in {'DISCUSS', 'FINAL_DISCUSS'} else g['config']['action_seconds']
        remaining = max(15, (g['deadline_at'] or time.time()) - time.time())
        state['resume_seconds'] = min(seconds, remaining)
        g['deadline_at'] = None
        state['status'] = 'PAUSED_AI'
        state['ai_generation'] = state.get('ai_generation', 0) + 1
        state['lobby_version'] += 1
        # Never expose which seat/card caused a private-phase pause.
        state['ai_issue'] = {'code': reason, 'message': ISSUES[reason]}
        state['metrics']['ai_pauses'] = state['metrics'].get('ai_pauses', 0) + 1

    async def action(self, code, user, command):
        self.get(code)
        async with self.locks[code]:
            def mutate(room):
                seat = next((s['seat'] for s in room['seats'] if s.get('user_id') == user['id']), None)
                if seat is None or not room['game']:
                    raise HTTPException(403, '当前没有可操作的参赛座位')
                if room['status'] == 'PAUSED_AI':
                    raise HTTPException(409, '对局已暂停，等待 AI 服务恢复')
                if room['status'] == 'ARCHIVED':
                    raise HTTPException(409, '此房间已只读归档')
                game = room['game']
                if command.request_id not in game['receipts'] and game['deadline_at'] is not None and game['deadline_at'] <= time.time():
                    raise rules.RuleError('操作已超时，正在刷新阶段')
                new, changed = rules.apply(game, seat, command.request_id, command.action_id, command.text)
                room['game'] = new
                if new['winner']:
                    room['status'] = 'FINISHED'
                return changed
            changed = self.db.transact(code, mutate)
        if changed:
            self.notify(code)

    async def resume(self, code, user_id):
        self.get(code)
        async with self.locks[code]:
            def mutate(state):
                if state['host_id'] != user_id:
                    raise HTTPException(403, '只有房主可以重试 AI 服务')
                if state['status'] != 'PAUSED_AI':
                    raise HTTPException(409, '当前对局不处于 AI 暂停状态')
                if any(s['kind'] == 'llm' and s['profile'] not in self.profiles for s in state['seats']):
                    raise HTTPException(409, ISSUES['NOT_CONFIGURED'])
                if state['metrics']['reserved_calls'] + 2 > self.budget:
                    raise HTTPException(409, ISSUES['BUDGET_EXHAUSTED'])
                state['status'] = 'PLAYING'
                state['ai_issue'] = None
                state['ai_generation'] = state.get('ai_generation', 0) + 1
                state['lobby_version'] += 1
                state['game']['deadline_at'] = time.time() + state.pop('resume_seconds', 60)
                # Epoch and already submitted votes stay unchanged.
            self.db.transact(code, mutate)
        self.notify(code)

    def _valid(self, state, seat, req, generation):
        g = state['game']
        return (state['status'] == 'PLAYING' and state.get('ai_generation', 0) == generation
                and g and rules.request_id(g, seat) == req and bool(rules.actions(g, seat)))

    async def _agent_turn(self, code, seat, req, generation):
        await asyncio.sleep(self.ai_delay)
        async with self.semaphore:
            async with self.locks[code]:
                room = self.get(code)
                if not self._valid(room, seat, req, generation):
                    return
                if room['game']['deadline_at'] <= time.time():
                    self.db.transact(code, lambda s: self._pause(s, 'TIMEOUT'))
                    self.notify(code)
                    return
                view = rules.observe(room['game'], seat)
                record = room['seats'][seat - 1]
                if record['kind'] != 'llm':
                    return
                profile = self.profiles.get(record['profile'])
                reason = 'NOT_CONFIGURED' if not profile else ('BUDGET_EXHAUSTED' if room['metrics']['reserved_calls'] + 2 > self.budget else None)
                if reason:
                    self.db.transact(code, lambda s: self._pause(s, reason))
                    self.notify(code)
                    return
                reserved = 2
                self.db.transact(code, lambda s: s['metrics'].__setitem__('reserved_calls', s['metrics']['reserved_calls'] + reserved))
            # Never hold a room lock or database transaction across a model request.
            failure = None
            try:
                command, stats = await self.agent.decide(profile, view)
            except ModelUnavailable as exc:
                command, stats, failure = None, exc.stats, 'PROVIDER_ERROR'
            except Exception:
                # Unexpected errors must also fail closed; log no prompts/keys/response text.
                command, stats, failure = None, {'calls': reserved, 'errors': 1}, 'PROVIDER_ERROR'
                log.error('AI turn failed unexpectedly')
            async with self.locks[code]:
                def commit(state):
                    for k, v in stats.items():
                        state['metrics'][k] = state['metrics'].get(k, 0) + v
                    state['metrics']['reserved_calls'] -= max(0, reserved - stats.get('calls', reserved))
                    if not self._valid(state, seat, req, generation):
                        return  # Pause/resume invalidates every older in-flight response.
                    if failure:
                        self._pause(state, failure)
                        return
                    if state['game']['deadline_at'] <= time.time():
                        self._pause(state, 'TIMEOUT')
                        return
                    try:
                        new, _ = rules.apply(state['game'], seat, command['request_id'], command['action_id'], command['text'])
                    except rules.RuleError:
                        self._pause(state, 'PROVIDER_ERROR')
                        return
                    state['game'] = new
                    if new['winner']:
                        state['status'] = 'FINISHED'
                self.db.transact(code, commit)
            self.notify(code)

    async def tick(self):
        for room in self.db.list_states('PLAYING', 100):
            code, game = room['code'], room['game']
            if game['deadline_at'] is not None and game['deadline_at'] <= time.time():
                async with self.locks[code]:
                    def expire(state):
                        current = state['game']
                        if state['status'] != 'PLAYING' or current['deadline_at'] is None or current['deadline_at'] > time.time():
                            return
                        if any(s['kind'] == 'llm' and rules.actions(current, s['seat']) for s in state['seats']):
                            self._pause(state, 'TIMEOUT')
                            return
                        epoch = current['epoch']
                        for seat in state['seats']:
                            if current['epoch'] != epoch:
                                break
                            if seat['kind'] != 'human':
                                continue
                            view = rules.observe(current, seat['seat'])
                            if view['allowed_actions']:
                                cmd = rules.timeout_action(view)
                                current, _ = rules.apply(current, seat['seat'], cmd['request_id'], cmd['action_id'], cmd['text'])
                                state['metrics']['timeouts'] += 1
                        state['game'] = current
                        if current['winner']:
                            state['status'] = 'FINISHED'
                    self.db.transact(code, expire)
                self.notify(code)
                continue
            generation = room.get('ai_generation', 0)
            for seat in room['seats']:
                if seat['kind'] != 'llm' or not rules.actions(game, seat['seat']):
                    continue
                req = rules.request_id(game, seat['seat'])
                key = (code, req, generation)
                if key not in self.pending:
                    task = asyncio.create_task(self._agent_turn(code, seat['seat'], req, generation))
                    self.pending[key] = task
                    def done(completed, key=key):
                        self.pending.pop(key, None)
                        if not completed.cancelled() and completed.exception():
                            log.error('AI task failed: %s', type(completed.exception()).__name__)
                    task.add_done_callback(done)

    async def drive(self):
        while True:
            try:
                await self.tick()
            except Exception as exc:
                log.error('scheduler iteration failed: %s', type(exc).__name__)
            await asyncio.sleep(0.5)

    async def close(self):
        tasks = list(self.pending.values()) + ([self.loop_task] if self.loop_task else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.db.engine.dispose()
