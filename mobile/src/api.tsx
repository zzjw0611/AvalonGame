import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { Identity } from './types';
import { restoreIdentity, SERVER_URL } from './config';

const SESSION_KEY = 'avalon.session.v1';
export const PENDING_KEY = 'avalon.pending.v1';
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function request<T>(base: string, token: string | null, path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(base + path, {
      method, signal: controller.signal,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await response.text();
    let data: any;
    try { data = raw ? JSON.parse(raw) : null; } catch { throw new ApiError('服务器响应无法解析', response.status); }
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail) ? data.detail.map((x: any) => x.msg).join('；') : '请求失败';
      throw new ApiError(detail, response.status);
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('连接失败或超时，请检查网络后重试', 0);
  } finally { clearTimeout(timer); }
}

type SessionContextValue = {
  identity: Identity | null; ready: boolean;
  login: (name: string, accessCode: string) => Promise<void>;
  logout: () => Promise<void>;
};
const SessionContext = createContext<SessionContextValue | null>(null);
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const raw = await SecureStore.getItemAsync(SESSION_KEY);
        if (raw && active) {
          const saved = restoreIdentity(raw);
          if (active) setIdentity(saved);
          if (!saved) { await SecureStore.deleteItemAsync(SESSION_KEY); await SecureStore.deleteItemAsync(PENDING_KEY); }
        }
      } catch { await SecureStore.deleteItemAsync(SESSION_KEY); }
      finally { if (active) setReady(true); }
    })();
    return () => { active = false; };
  }, []);
  async function login(name: string, accessCode: string) {
    const baseUrl = SERVER_URL;
    const session = await request<Omit<Identity, 'baseUrl'>>(baseUrl, null, '/api/sessions', 'POST', { name, access_code: accessCode });
    const next = { ...session, baseUrl };
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(next));
    await SecureStore.deleteItemAsync(PENDING_KEY);
    setIdentity(next);
  }
  async function logout() {
    if (identity) {
      try { await request(identity.baseUrl, identity.token, '/api/sessions', 'DELETE'); } catch { /* Local credentials are removed even when offline. */ }
    }
    await SecureStore.deleteItemAsync(SESSION_KEY);
    await SecureStore.deleteItemAsync(PENDING_KEY);
    setIdentity(null);
  }
  return <SessionContext.Provider value={{ identity, ready, login, logout }}>{children}</SessionContext.Provider>;
}
export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('SessionProvider is missing');
  return value;
}
