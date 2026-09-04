import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  tone?: "neutral" | "sage" | "amber" | "brick";
  className?: string;
}

const toneMap = {
  neutral: "border-border text-muted",
  sage: "border-sage/40 text-sage",
  amber: "border-amber/40 text-amber",
  brick: "border-brick/40 text-brick",
};

export function Badge({ children, tone = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[11px] leading-relaxed",
        toneMap[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
