"use client";

/**
 * 경보 알림 훅
 *
 * - critical 경보 수신 시 브라우저 Notification API로 백그라운드 알림
 * - Web Audio API로 심각도별 경보음 생성 (외부 파일 불필요)
 * - 탭이 활성화되어 있을 때는 알림을 생략하고 음원만 재생
 */

import { useEffect, useRef } from "react";
import { useAlertStore } from "@/stores/alertStore";

const SOUND_ENABLED_KEY = "cowater-alert-sound";

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    return new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
  } catch {
    return null;
  }
}

function playCriticalSound(ctx: AudioContext) {
  // 짧은 두 음 연속 (피 피)
  const now = ctx.currentTime;
  for (let i = 0; i < 2; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0, now + i * 0.25);
    gain.gain.linearRampToValueAtTime(0.18, now + i * 0.25 + 0.02);
    gain.gain.linearRampToValueAtTime(0, now + i * 0.25 + 0.15);
    osc.start(now + i * 0.25);
    osc.stop(now + i * 0.25 + 0.18);
  }
}

function playWarningSound(ctx: AudioContext) {
  // 낮은 단일 음 (딩)
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "sine";
  osc.frequency.value = 520;
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(0.12, now + 0.02);
  gain.gain.linearRampToValueAtTime(0, now + 0.3);
  osc.start(now);
  osc.stop(now + 0.35);
}

function requestNotificationPermission() {
  if (typeof Notification === "undefined") return;
  if (Notification.permission === "default") {
    void Notification.requestPermission();
  }
}

function showBrowserNotification(title: string, body: string) {
  if (typeof Notification === "undefined") return;
  if (Notification.permission !== "granted") return;
  if (document.visibilityState === "visible") return; // 탭 활성 시 생략
  try {
    new Notification(title, { body, icon: "/icon.svg", tag: "cowater-alert" });
  } catch {
    // 일부 브라우저에서 secure context 아닌 경우 실패 가능 — 무시
  }
}

export function useAlertNotifications() {
  const alerts = useAlertStore((s) => s.alerts);
  const seenRef = useRef<Set<string>>(new Set());
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioEnabledRef = useRef(false);

  useEffect(() => {
    requestNotificationPermission();

    const enableAudio = () => {
      if (audioEnabledRef.current) return;
      if (!audioCtxRef.current) {
        audioCtxRef.current = getAudioContext();
      }
      const ctx = audioCtxRef.current;
      if (!ctx) return;

      if (ctx.state === "suspended") {
        void ctx.resume()
          .then(() => {
            audioEnabledRef.current = ctx.state === "running";
          })
          .catch(() => {});
        return;
      }

      audioEnabledRef.current = ctx.state === "running";
    };

    window.addEventListener("pointerdown", enableAudio, { passive: true });
    window.addEventListener("keydown", enableAudio);

    return () => {
      window.removeEventListener("pointerdown", enableAudio);
      window.removeEventListener("keydown", enableAudio);
      audioCtxRef.current?.close();
    };
  }, []);

  useEffect(() => {
    // 새 경보만 처리
    const newAlerts = alerts.filter(
      (a) => a.status === "new" && !seenRef.current.has(a.alert_id),
    );
    if (newAlerts.length === 0) return;

    for (const alert of newAlerts) {
      seenRef.current.add(alert.alert_id);
    }

    const critical = newAlerts.filter((a) => a.severity === "critical");
    const warning = newAlerts.filter((a) => a.severity === "warning");

    // 사운드 재생 (localStorage로 음소거 여부 확인)
    const soundEnabled = localStorage.getItem(SOUND_ENABLED_KEY) !== "false";
    if (soundEnabled) {
      const ctx = audioCtxRef.current;
      if (ctx && audioEnabledRef.current && ctx.state === "running") {
        if (critical.length > 0) playCriticalSound(ctx);
        else if (warning.length > 0) playWarningSound(ctx);
      }
    }

    // 브라우저 알림 (탭이 숨겨진 경우에만)
    if (critical.length > 0) {
      showBrowserNotification(
        `위험 경보 ${critical.length}건`,
        critical.map((a) => a.message).join("\n"),
      );
    } else if (warning.length > 0) {
      showBrowserNotification(
        `경고 ${warning.length}건`,
        warning.map((a) => a.message).join("\n"),
      );
    }
  }, [alerts]);
}
