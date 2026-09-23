import { useCallback, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { AppState } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { ApiError, PENDING_KEY, request } from './api';
import { Command, Identity, Room } from './types';
import { isNewer } from './protocol';

type Pending = { code: string; userId: string; baseUrl: string; command: Command };
export function useRoom(identity: Identity | null, code: string) {
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('连接中');
  const [busy, setBusy] = useState(false);
  const [serverOffset, setServerOffset] = useState(0);
  const [pending, setPending] = useState<Pending | null>(null);
  const sending = useRef(false);
  const mounted = useRef(true);
  const currentCode = useRef(code);
  currentCode.current = code;
  const accept = useCallback((next: Room) => {
    if (mounted.current && next.code === currentCode.current) setRoom(previous => isNewer(previous, next) ? next : previous);
  }, []);
  const refresh = useCallback(async () => {
    if (!identity) return;
    try {
      accept(await request<Room>(identity.baseUrl, identity.token, `/api/rooms/${code}`));
      if (mounted.current) setError('');
    } catch (err) { if (mounted.current) setError((err as Error).message); }
  }, [identity, code, accept]);
  useFocusEffect(useCallback(() => {
    mounted.current = true;
    setRoom(null); setPending(null);
    if (!identity) return;
    let stopped = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1000;
    let lastMessage = Date.now();
    let active = AppState.currentState !== 'background';
    function connect() {
      if (stopped || !active) return;
      if (retry) { clearTimeout(retry); retry = null; }
      socket?.close();
      setConnection('连接中');
      const base = identity!.baseUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
      const ws = new WebSocket(`${base}/ws/rooms/${code}`);
      socket = ws;
      ws.onopen = () => { if (socket === ws && !stopped) ws.send(JSON.stringify({ token: identity!.token })); };
      ws.onmessage = event => {
        if (stopped || socket !== ws) return;
        lastMessage = Date.now(); backoff = 1000;
        try {
          const data = JSON.parse(event.data);
          if (typeof data.server_time === 'number') setServerOffset(data.server_time - Date.now() / 1000);
          if (data.type === 'snapshot') { accept(data.data); setError(''); }
          setConnection('实时连接');
        } catch { ws.close(); }
      };
      ws.onerror = () => { if (!stopped) setConnection('正在重连'); ws.close(); };
      ws.onclose = () => {
        if (stopped || socket !== ws || !active) return;
        setConnection('正在重连');
        retry = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 15000);
      };
    }
    void refresh();
    void SecureStore.getItemAsync(PENDING_KEY).then(raw => {
      if (!raw || stopped) return;
      try {
        const value = JSON.parse(raw) as Pending;
        if (value.userId === identity.id && value.code === code && value.baseUrl === identity.baseUrl) setPending(value);
      } catch { void SecureStore.deleteItemAsync(PENDING_KEY); }
    });
    connect();
    const stateSubscription = AppState.addEventListener('change', state => {
      active = state === 'active';
      if (active) { void refresh(); connect(); }
      else { if (retry) clearTimeout(retry); socket?.close(); setConnection('后台暂停连接'); }
    });
    const polling = setInterval(() => {
      if (!active || stopped) return;
      void refresh();
      if (Date.now() - lastMessage > 40000) socket?.close();
    }, 12000);
    return () => {
      stopped = true; mounted.current = false; stateSubscription.remove(); clearInterval(polling);
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [identity, code, refresh, accept]));

  async function send(command: Command, retrying = false) {
    if (!identity || sending.current || (pending && !retrying)) return;
    const record: Pending = { code, userId: identity.id, baseUrl: identity.baseUrl, command };
    sending.current = true; setBusy(true); setError('');
    try {
      // Persist exact command before sending; retries cannot change a secret ballot.
      await SecureStore.setItemAsync(PENDING_KEY, JSON.stringify(record));
      if (mounted.current) setPending(record);
      const next = await request<Room>(identity.baseUrl, identity.token, `/api/rooms/${code}/actions`, 'POST', command);
      accept(next);
      await SecureStore.deleteItemAsync(PENDING_KEY);
      if (mounted.current) setPending(null);
    } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 429) {
        await SecureStore.deleteItemAsync(PENDING_KEY);
        if (mounted.current) setPending(null);
      }
      if (mounted.current) setError((err as Error).message);
      void refresh();
    } finally { sending.current = false; if (mounted.current) setBusy(false); }
  }
  async function start() {
    if (!identity || sending.current) return;
    sending.current = true; setBusy(true);
    try { accept(await request<Room>(identity.baseUrl, identity.token, `/api/rooms/${code}/start`, 'POST')); }
    catch (err) { setError((err as Error).message); }
    finally { sending.current = false; setBusy(false); }
  }
  return { room, error, connection, busy, pending, refresh, start, send, serverOffset,
    retry: () => pending ? send(pending.command, true) : Promise.resolve() };
}
