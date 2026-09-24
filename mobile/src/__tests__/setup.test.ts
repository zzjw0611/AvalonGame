import { describe, expect, test } from '@jest/globals';
import { DEFAULT_SERVER_URL, SERVER_URL, restoreIdentity } from '../config';
import { makeSeats, roomSetupError } from '../roomSetup';

describe('fixed server', () => {
  test('uses the owner server with TLS by default', () => {
    expect(DEFAULT_SERVER_URL).toBe('https://42.193.181.239');
    expect(SERVER_URL).toBe(DEFAULT_SERVER_URL);
  });
  test('restores matching origin only', () => {
    const saved = { id: 'guest', name: 'Alice', token: 'secret', baseUrl: DEFAULT_SERVER_URL };
    expect(restoreIdentity(JSON.stringify(saved))).toEqual(saved);
    expect(restoreIdentity(JSON.stringify({ ...saved, baseUrl: 'https://other.example' }))).toBeNull();
    expect(restoreIdentity(JSON.stringify({ ...saved, baseUrl: 'http://42.193.181.239' }))).toBeNull();
  });
  test.each([null, '', 'bad json', '{}', 'null'])('handles invalid saved session %s', raw => {
    expect(restoreIdentity(raw)).toBeNull();
  });
});
describe('human and AI setup', () => {
  test.each([5, 6, 7, 8, 9, 10])('%i-player setup has no third player type', n => {
    const seats = makeSeats(n, 1, 'model-a');
    expect(seats).toHaveLength(n);
    expect(seats[0]).toEqual({ kind: 'human', profile: null });
    expect(seats.filter(s => s.kind === 'llm')).toHaveLength(n - 1);
    expect(seats.every(s => s.kind === 'human' || s.kind === 'llm')).toBe(true);
  });
  test('all human does not require model', () => {
    expect(makeSeats(7, 7, null).every(s => s.kind === 'human')).toBe(true);
    expect(roomSetupError(7, 7, true, ['PERCIVAL', 'MORGANA'], 3, false)).toBeNull();
  });
  test('all AI uses zero human seats and spectating host', () => {
    expect(makeSeats(7, 0, 'm').every(s => s.kind === 'llm')).toBe(true);
    expect(roomSetupError(7, 0, false, [], 3, true)).toBeNull();
    expect(roomSetupError(7, 0, true, [], 3, true)).not.toBeNull();
  });
  test('missing AI is explicit, never a replacement', () => {
    expect(() => makeSeats(7, 1, null)).toThrow('AI 暂不可用');
    expect(roomSetupError(7, 1, true, [], 3, false)).not.toBeNull();
  });
  test('invalid five-player role mix disables creation', () => {
    expect(roomSetupError(5, 1, true, ['PERCIVAL'], 2, true)).not.toBeNull();
    expect(roomSetupError(5, 1, true, ['MORGANA', 'MORDRED'], 2, true)).not.toBeNull();
  });
  test.each([[4, 1], [11, 1], [7, -1], [7, 8], [7, 1.5]])('rejects counts %s/%s', (n, humans) => {
    expect(() => makeSeats(n, humans, 'm')).toThrow();
  });
});
