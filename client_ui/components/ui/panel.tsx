import { cn } from "@/lib/utils";

export function Panel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("border border-border bg-surface", className)}>
      {children}
    </div>
  );
}

export function PanelHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-text">
      {children}
    </div>
  );
}
