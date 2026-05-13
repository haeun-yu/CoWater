import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '../services/api';

export function useRegistryPreview<T>(path: string, fallback: T) {
  return useQuery({
    queryKey: ['registry-preview', path],
    queryFn: async () => {
      try {
        return await fetchJson<T>(path);
      } catch {
        return fallback;
      }
    },
  });
}

