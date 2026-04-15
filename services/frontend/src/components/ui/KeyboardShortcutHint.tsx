/**
 * KeyboardShortcutHint: 단축키 오버레이 (모달)
 */

import { useEffect, useState } from "react";
import { KEYBOARD_SHORTCUTS } from "@/hooks/useKeyboard";

interface KeyboardShortcutHintProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function KeyboardShortcutHint({
  isOpen,
  onClose,
}: KeyboardShortcutHintProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!mounted || !isOpen) return null;

  // 카테고리별 그룹핑
  const grouped: Record<string, typeof KEYBOARD_SHORTCUTS> = {};
  KEYBOARD_SHORTCUTS.forEach((shortcut) => {
    if (!grouped[shortcut.category]) {
      grouped[shortcut.category] = [];
    }
    grouped[shortcut.category].push(shortcut);
  });

  return (
    <>
      {/* 백드롭 */}
      <div
        className="fixed inset-0 bg-black/60 z-50"
        onClick={onClose}
      />

      {/* 모달 */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-ocean-950 border border-ocean-700/50 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto panel-slide-in">
          {/* 헤더 */}
          <div className="sticky top-0 bg-ocean-950 border-b border-ocean-700/30 px-6 py-4 flex items-center justify-between">
            <h2 className="text-lg font-bold text-ocean-100">⌨️ 단축키</h2>
            <button
              onClick={onClose}
              className="text-ocean-400 hover:text-ocean-200 transition-colors text-lg"
            >
              ✕
            </button>
          </div>

          {/* 콘텐츠 */}
          <div className="p-6 space-y-6">
            {Object.entries(grouped).map(([category, shortcuts]) => (
              <div key={category}>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-ocean-400 mb-3">
                  {category}
                </h3>
                <div className="space-y-2">
                  {shortcuts.map((shortcut, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-4 p-3 rounded-lg bg-ocean-900/30 hover:bg-ocean-900/50 transition-colors"
                    >
                      <kbd className="px-2.5 py-1 rounded border border-ocean-600 bg-ocean-800 text-ocean-200 text-xs font-mono font-medium whitespace-nowrap">
                        {shortcut.key}
                      </kbd>
                      <span className="text-sm text-ocean-300">
                        {shortcut.description}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* 푸터 */}
          <div className="border-t border-ocean-700/30 px-6 py-3 bg-ocean-950/50 text-xs text-ocean-500 text-center">
            Esc를 눌러서 닫기
          </div>
        </div>
      </div>
    </>
  );
}
