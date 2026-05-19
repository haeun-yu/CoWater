export const REGISTRY_URL = (import.meta.env.VITE_REGISTRY_URL as string | undefined) || 'http://127.0.0.1:8280';
export const SYSTEM_AGENT_URL = (import.meta.env.VITE_SYSTEM_AGENT_URL as string | undefined) || 'http://127.0.0.1:9116';

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${REGISTRY_URL}${path}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

