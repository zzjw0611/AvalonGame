import { normalizeBaseUrl } from './protocol';
import { Identity } from './types';

export const DEFAULT_SERVER_URL = 'https://42.193.181.239';
// Build-time override for developer/staging builds; never a player setting.
export const SERVER_URL = normalizeBaseUrl(process.env.EXPO_PUBLIC_API_URL || DEFAULT_SERVER_URL, __DEV__);

export function restoreIdentity(raw: string | null, server = SERVER_URL): Identity | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Identity>;
    if (typeof value.id !== 'string' || !value.id || typeof value.name !== 'string'
        || typeof value.token !== 'string' || !value.token || typeof value.baseUrl !== 'string') return null;
    if (normalizeBaseUrl(value.baseUrl, __DEV__) !== server) return null;
    // Never forward a token saved for another host to the default server.
    return { id: value.id, name: value.name, token: value.token, baseUrl: server };
  } catch { return null; }
}
