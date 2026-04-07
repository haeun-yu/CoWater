"use client";

import { useEffect, useRef } from "react";
import { useToastStore, type ToastItem } from "@/stores/toastStore";

const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  distress: "조난",
  compliance: "상황 보고",
};

const SEV = {
  critical: {
    border: "border-red-500/80",
    bg: "bg-[#1a0505]/95",
    icon: "⚠",
    iconColor: "text-red-400",
    label: "위험",
    labelColor: "text-red-300",
    bar: "bg-red-500",
    ms: 8000,
  },
  warning: {
    border: "border-amber-500/70",
    bg: "bg-[#1a1005]/95",
    icon: "△",
    iconColor: "text-amber-400",
    label: "주의",
    labelColor: "text-amber-300",
    bar: "bg-amber-500",
    ms: 5000,
  },
  info: {
    border: "border-ocean-600/60",
    bg: "bg-ocean-900/95",
    icon: "ℹ",
    iconColor: "text-ocean-400",
    label: "정보",
    labelColor: "text-ocean-300",
    bar: "bg-ocean-500",
    ms: 3500,
  },
} as const;

export default function ToastOverlay() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <>
      <style>{`
        @keyframes toast-slide{from{opacity:0;transform:translateX(16px)}to{opacity:1;transform:translateX(0)}}
        .toast-enter{animation:toast-slide 0.2s ease-out forwards}
      `}</style>
      <div
        className="fixed bottom-6 right-4 z-50 flex flex-col-reverse gap-2 pointer-events-none"
        style={{ maxWidth: 340 }}
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </>
  );
}

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const cfg = SEV[toast.severity];
  const progressRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(onDismiss, cfg.ms);

    // progress bar 애니메이션
    const el = progressRef.current;
    if (el) {
      el.style.transition = `width ${cfg.ms}ms linear`;
      requestAnimationFrame(() => { el.style.width = "0%"; });
    }

    return () => clearTimeout(timer);
  }, [toast.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className={`toast-enter pointer-events-auto rounded-lg border ${cfg.border} ${cfg.bg} shadow-2xl backdrop-blur-sm overflow-hidden`}
      style={{ minWidth: 280, maxWidth: 340 }}
    >
      {/* 상단 색상 바 */}
      <div className="h-0.5 bg-ocean-800/40 relative">
        <div
          ref={progressRef}
          className={`absolute left-0 top-0 h-full ${cfg.bar} opacity-70`}
          style={{ width: "100%" }}
        />
      </div>

      <div className="px-3.5 py-3">
        <div className="flex items-start gap-2.5">
          {/* 아이콘 */}
          <span className={`text-sm flex-shrink-0 mt-0.5 ${cfg.iconColor}`}>{cfg.icon}</span>

          <div className="flex-1 min-w-0">
            {/* 헤더 행 */}
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs font-bold ${cfg.labelColor}`}>{cfg.label}</span>
              <span className="text-xs text-ocean-400">
                {ALERT_TYPE_KR[toast.alertType] ?? toast.alertType}
              </span>
              <span className="text-xs text-ocean-400 ml-auto truncate pl-1">{toast.agentName}</span>
            </div>

            {/* 메시지 */}
            <p className="text-xs text-ocean-200 leading-snug line-clamp-2">{toast.message}</p>

            {/* 관련 선박 */}
            {toast.platformIds.length > 0 && (
              <div className="mt-1.5 flex gap-1 flex-wrap">
                {toast.platformIds.slice(0, 4).map((id) => (
                  <span
                    key={id}
                    className="text-xs px-1.5 py-0.5 bg-ocean-800/60 text-ocean-400 rounded font-mono border border-ocean-700/30"
                  >
                    {id.replace(/^MMSI-/, "")}
                  </span>
                ))}
                {toast.platformIds.length > 4 && (
                  <span className="text-xs text-ocean-400">+{toast.platformIds.length - 4}</span>
                )}
              </div>
            )}
          </div>

          {/* 닫기 버튼 */}
          <button
            onClick={onDismiss}
            className="flex-shrink-0 text-ocean-400 hover:text-ocean-400 transition-colors text-base leading-none mt-0.5"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  );
}
