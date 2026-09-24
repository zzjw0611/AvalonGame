"""Test-only simulated choices; never imported by application code."""
import json
import httpx
from app.agents import ModelAgent, ModelProfile


def choose_action(view):
    ids = {a['id'] for a in view['allowed_actions']}
    action = next((a for a in ('skip', 'approve', 'success') if a in ids), view['allowed_actions'][0]['id'])
    return {'request_id': view['request_id'], 'action_id': action, 'text': ''}


def mock_provider(request):
    payload = json.loads(request.content)
    facts = json.loads(payload['messages'][1]['content'].split('\n', 1)[1])
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(choose_action(facts))}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})


def configure_mock(runtime):
    runtime.ai_delay = 0
    runtime.profiles['test'] = ModelProfile('test', 'Test AI', 'https://model.invalid/v1', 'test-model', 'TEST_ONLY_NOT_REAL')
    runtime.agent = ModelAgent(transport=httpx.MockTransport(mock_provider))
