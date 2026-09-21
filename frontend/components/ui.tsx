"use client";

import { cn } from "@/lib/utils";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("glass rounded-2xl shadow-card", className)}>{children}</div>;
}

export function Button({
  className,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition focus-visible:outline-2 disabled:opacity-50 disabled:cursor-not-allowed";
  const variants: Record<string, string> = {
    primary: "bg-accent text-white shadow-glow hover:bg-accent-soft",
    ghost: "border border-border text-white/80 hover:bg-white/5",
    danger: "bg-red-600/90 text-white hover:bg-red-600",
  };
  return <button className={cn(base, variants[variant], className)} {...props} />;
}

export function Badge({ tone = "default", children }: { tone?: "default" | "success" | "warning" | "danger" | "info"; children: React.ReactNode }) {
  const tones: Record<string, string> = {
    default: "bg-white/10 text-white/80",
    success: "bg-emerald-500/15 text-emerald-300",
    warning: "bg-amber-500/15 text-amber-300",
    danger: "bg-red-500/15 text-red-300",
    info: "bg-violet-500/15 text-violet-300",
  };
  return <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-white/5", className)} />;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border py-16 text-center">
      <p className="text-lg font-medium text-white/80">{title}</p>
      {description && <p className="max-w-sm text-sm text-white/50">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/5 py-12 text-center">
      <p className="font-medium text-red-300">Something went wrong</p>
      <p className="max-w-sm text-sm text-white/50">{message}</p>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-accent focus:outline-none",
        props.className
      )}
    />
  );
}
