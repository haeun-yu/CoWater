import type { PlatformState } from "@/types";

const STALE_WARNING_MS = 45_000;
const STALE_CRITICAL_MS = 120_000;

export type PlatformFreshness = "live" | "stale" | "lost";

export function getPlatformAgeMs(lastSeen: string | null | undefined): number | null {
  if (!lastSeen) return null;
  const ts = new Date(lastSeen).getTime();
  if (Number.isNaN(ts)) return null;
  return Math.max(0, Date.now() - ts);
}

export function getPlatformFreshness(lastSeen: string | null | undefined): PlatformFreshness {
  const age = getPlatformAgeMs(lastSeen);
  if (age == null) return "lost";
  if (age < STALE_WARNING_MS) return "live";
  if (age < STALE_CRITICAL_MS) return "stale";
  return "lost";
}

export function countPlatformsByFreshness(platforms: PlatformState[]) {
  return platforms.reduce(
    (acc, platform) => {
      const freshness = getPlatformFreshness(platform.last_seen);
      acc[freshness] += 1;
      return acc;
    },
    { live: 0, stale: 0, lost: 0 },
  );
}

export function formatLastSeen(lastSeen: string | null | undefined): string {
  const age = getPlatformAgeMs(lastSeen);
  if (age == null) return "수신 정보 없음";

  const seconds = Math.floor(age / 1000);
  if (seconds < 10) return "방금 전";
  if (seconds < 60) return `${seconds}초 전`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;

  const hours = Math.floor(minutes / 60);
  return `${hours}시간 전`;
}
