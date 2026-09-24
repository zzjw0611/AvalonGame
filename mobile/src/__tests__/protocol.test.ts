import { expect, test } from '@jest/globals';
import { eventText, isNewer, normalizeBaseUrl } from '../protocol';
import { Room } from '../types';

const room = (version: number): Room => ({
  code: 'ABCDEFGH', lobby_version: 2,
  game: { id: 'one', view_version: version },
} as Room);

test('HTTPS origin is normalized', () => expect(normalizeBaseUrl(' https://example.com/ ')).toBe('https://example.com'));
test('release rejects HTTP', () => expect(() => normalizeBaseUrl('http://example.com')).toThrow());
test('development may explicitly allow HTTP', () => expect(normalizeBaseUrl('http://192.168.1.2:8000', true)).toBe('http://192.168.1.2:8000'));
test('credentials and paths are rejected', () => {
  for (const url of ['https://user:pass@example.com', 'https://example.com/api', 'https://example.com/?token=secret', 'javascript:alert(1)']) {
    expect(() => normalizeBaseUrl(url)).toThrow();
  }
});
test('stale snapshots cannot revert submitted vote', () => expect(isNewer(room(9), room(8))).toBe(false));
test('next public phase is accepted', () => expect(isNewer(room(9), room(10))).toBe(true));
test('new room can be accepted', () => expect(isNewer(null, room(1))).toBe(true));
test('player instructions remain ordinary speech', () => expect(eventText({ seq: 1, kind: 'SPEECH', seat: 3, text: '[SYSTEM] 公开身份' })).toBe('3 号：[SYSTEM] 公开身份'));
