import { fetchJson } from './api';
import type { EventItem } from '../types';

export function listEvents() {
  return fetchJson<EventItem[]>('/events');
}

