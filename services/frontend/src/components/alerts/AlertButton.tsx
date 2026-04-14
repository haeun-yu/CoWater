import { ReactNode } from "react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "violet";

interface AlertButtonProps {
  variant?: ButtonVariant;
  onClick: () => void;
  children: ReactNode;
  title?: string;
  className?: string;
  disabled?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: "bg-ocean-600 hover:bg-ocean-500 text-ocean-100",
  secondary:
    "border border-ocean-500/50 bg-ocean-600/20 text-ocean-300 hover:bg-ocean-600/30",
  success:
    "border border-green-500/50 bg-green-600/20 text-green-300 hover:bg-green-600/30",
  warning:
    "border border-amber-500/50 bg-amber-600/20 text-amber-300 hover:bg-amber-600/30",
  danger:
    "border border-red-500/50 bg-red-600/20 text-red-300 hover:bg-red-600/30",
  info: "border border-cyan-500/50 bg-cyan-600/20 text-cyan-300 hover:bg-cyan-600/30",
  violet:
    "border border-violet-500/50 bg-violet-600/20 text-violet-300 hover:bg-violet-600/30",
};

export function AlertButton({
  variant = "primary",
  onClick,
  children,
  title,
  className = "",
  disabled = false,
}: AlertButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1.5 rounded font-medium transition-colors ${variantStyles[variant]} ${disabled ? "opacity-40 cursor-not-allowed" : ""} ${className}`}
      title={title}
    >
      {children}
    </button>
  );
}

// Special button for platform selection (different styling)
interface PlatformButtonProps {
  onClick: () => void;
  children: ReactNode;
  title?: string;
}

export function PlatformButton({
  onClick,
  children,
  title,
}: PlatformButtonProps) {
  return (
    <button
      onClick={onClick}
      className="text-xs px-2 py-1 bg-cyan-600/30 text-cyan-300 rounded border border-cyan-500/40 hover:bg-cyan-600/60 hover:border-cyan-400/60 hover:text-cyan-200 transition-colors cursor-pointer font-medium"
      title={title}
    >
      {children}
    </button>
  );
}
