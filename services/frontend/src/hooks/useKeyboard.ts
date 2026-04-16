import { useEffect, useCallback } from "react";

interface KeyboardHookOptions {
  onOpenShortcuts?: () => void;
  onQuickSearch?: () => void;
  onNavigateUp?: () => void;
  onNavigateDown?: () => void;
  onConfirm?: () => void;
  onAcknowledge?: () => void;
  onClose?: () => void;
  onNavigateToPage?: (pageIndex: 1 | 2 | 3 | 4 | 5) => void;
  enabled?: boolean;
}

export const useKeyboard = (options: KeyboardHookOptions) => {
  const {
    onOpenShortcuts,
    onQuickSearch,
    onNavigateUp,
    onNavigateDown,
    onConfirm,
    onAcknowledge,
    onClose,
    onNavigateToPage,
    enabled = true,
  } = options;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      // 텍스트 입력 필드에서는 특수 단축키 비활성화 (Esc 제외)
      const isInputField =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement;

      if (isInputField && e.key !== "Escape") return;

      switch (e.key.toLowerCase()) {
        // ? : 단축키 오버레이 열기 (Shift+/ 조합으로 입력되므로 shiftKey 조건 불필요)
        case "?":
          if (!e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            onOpenShortcuts?.();
          }
          break;

        // ⌘K / Ctrl+K : 빠른 플랫폼 검색
        case "k":
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            onQuickSearch?.();
          }
          break;

        // ↑ : 이전 항목
        case "arrowup":
          if (!isInputField) {
            e.preventDefault();
            onNavigateUp?.();
          }
          break;

        // ↓ : 다음 항목
        case "arrowdown":
          if (!isInputField) {
            e.preventDefault();
            onNavigateDown?.();
          }
          break;

        // Enter : 확인 / 상세 보기
        case "enter":
          if (!isInputField) {
            e.preventDefault();
            onConfirm?.();
          }
          break;

        // A : 선택 경보 확인(Acknowledge)
        case "a":
          if (!isInputField && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            onAcknowledge?.();
          }
          break;

        // Esc : 드로어/패널 닫기
        case "escape":
          e.preventDefault();
          onClose?.();
          break;

        // 1~5 : 페이지 빠른 이동
        case "1":
        case "2":
        case "3":
        case "4":
        case "5":
          if (!e.ctrlKey && !e.metaKey && !isInputField) {
            e.preventDefault();
            onNavigateToPage?.(parseInt(e.key) as 1 | 2 | 3 | 4 | 5);
          }
          break;

        default:
          break;
      }
    },
    [
      enabled,
      onOpenShortcuts,
      onQuickSearch,
      onNavigateUp,
      onNavigateDown,
      onConfirm,
      onAcknowledge,
      onClose,
      onNavigateToPage,
    ]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
};

// 단축키 맵 (UI에 표시용)
export const KEYBOARD_SHORTCUTS = [
  {
    key: "?",
    description: "단축키 오버레이 열기",
    category: "General",
  },
  {
    key: "⌘K / Ctrl+K",
    description: "빠른 플랫폼 검색",
    category: "Navigation",
  },
  {
    key: "↑ ↓",
    description: "목록 항목 탐색",
    category: "Navigation",
  },
  {
    key: "Enter",
    description: "선택 항목 확인",
    category: "Navigation",
  },
  {
    key: "A",
    description: "경보 확인(Acknowledge)",
    category: "Alert",
  },
  {
    key: "Esc",
    description: "드로어/패널 닫기",
    category: "General",
  },
  {
    key: "1-5",
    description: "페이지 빠른 이동 (1=홈, 2=플랫폼, 3=경보, 4=에이전트, 5=리포트)",
    category: "Navigation",
  },
];
