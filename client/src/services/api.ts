const registryUrl = (import.meta.env.VITE_REGISTRY_URL as string | undefined) || 'http://127.0.0.1:8280';

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${registryUrl}${path}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

