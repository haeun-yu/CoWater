import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "dark" | "light";

interface ThemeStore {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: "dark",
      setTheme: (theme: Theme) => {
        set({ theme });
        if (typeof window !== "undefined") {
          const html = document.documentElement;
          html.setAttribute("data-theme", theme);
        }
      },
      toggleTheme: () =>
        set((state) => {
          const newTheme: Theme = state.theme === "dark" ? "light" : "dark";
          if (typeof window !== "undefined") {
            const html = document.documentElement;
            html.setAttribute("data-theme", newTheme);
          }
          return { theme: newTheme };
        }),
    }),
    {
      name: "cowater-theme",
      onRehydrateStorage: () => (state) => {
        if (state && typeof window !== "undefined") {
          const html = document.documentElement;
          html.setAttribute("data-theme", state.theme);
        }
      },
    }
  )
);
