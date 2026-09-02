"use client";

import { useTheme } from "@/lib/ThemeProvider";

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const options: { value: "light" | "dark" | "system"; icon: string; label: string }[] = [
    { value: "light", icon: "☀", label: "Light" },
    { value: "dark", icon: "☾", label: "Dark" },
    { value: "system", icon: "◐", label: "System" },
  ];

  return (
    <div className="flex items-center rounded-md border border-border bg-surface-subtle p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => setTheme(opt.value)}
          className={`flex h-7 w-7 items-center justify-center rounded text-xs transition-colors ${
            theme === opt.value
              ? "bg-accent text-white shadow-sm"
              : "text-fg-muted hover:text-fg"
          }`}
          title={opt.label}
          aria-label={`${opt.label} theme`}
        >
          {opt.icon}
        </button>
      ))}
    </div>
  );
}
