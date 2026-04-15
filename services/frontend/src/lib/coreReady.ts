"use client";

import { getCoreApiUrl } from "@/lib/publicUrl";

const CORE_READY_INITIAL_DELAY_MS = 500;
const CORE_READY_MAX_DELAY_MS = 5000;

function abortError() {
  return new DOMException("Aborted", "AbortError");
}

export async function waitForCoreReady(signal?: AbortSignal) {
  const healthUrl = `${getCoreApiUrl()}/health`;
  let delay = CORE_READY_INITIAL_DELAY_MS;

  while (!signal?.aborted) {
    try {
      const response = await fetch(healthUrl, {
        cache: "no-store",
        signal,
      });

      if (response.ok) {
        return true;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
    }

    await new Promise<void>((resolve, reject) => {
      const finish = () => {
        signal?.removeEventListener("abort", abortHandler);
      };
      const timer = window.setTimeout(() => {
        finish();
        resolve();
      }, delay);

      const abortHandler = () => {
        window.clearTimeout(timer);
        finish();
        reject(abortError());
      };

      signal?.addEventListener("abort", abortHandler, { once: true });
    });

    delay = Math.min(delay * 2, CORE_READY_MAX_DELAY_MS);
  }

  throw abortError();
}
