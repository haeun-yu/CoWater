/**
 * ThemeToggle: 다크/라이트 모드 토글 버튼
 */

import { useEffect, useState } from "react";
import { useThemeStore } from "@/lib/themeStore";

interface ThemeToggleProps {
  compact?: boolean;
}

export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const { theme, toggleTheme } = useThemeStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  if (compact) {
    return (
      <button
        onClick={toggleTheme}
        className="p-2 rounded-lg hover:bg-ocean-800/50 transition-colors"
        title={`${theme === "dark" ? "라이트" : "다크"} 모드로 전환`}
        aria-label="테마 토글"
      >
        {theme === "dark" ? "🌙" : "☀️"}
      </button>
    );
  }

  return (
    <button
      onClick={toggleTheme}
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-ocean-700/50 bg-ocean-900/30 hover:bg-ocean-800/50 transition-colors text-xs font-medium text-ocean-300"
      title={`${theme === "dark" ? "라이트" : "다크"} 모드로 전환`}
    >
      {theme === "dark" ? (
        <>
          🌙 <span>다크</span>
        </>
      ) : (
        <>
          ☀️ <span>라이트</span>
        </>
      )}
    </button>
  );
}
