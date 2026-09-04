import * as React from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
}

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
        variant === "primary" &&
          "bg-amber text-base hover:bg-amber/90",
        variant === "ghost" &&
          "text-muted hover:text-text hover:bg-surface2 border border-border",
        className
      )}
      {...props}
    />
  );
}
