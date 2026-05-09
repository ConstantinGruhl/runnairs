import { forwardRef } from "react";

import clsx from "clsx";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button({ className, variant = "primary", ...props }, ref) {
    const base =
      "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 disabled:pointer-events-none";
    const variants: Record<string, string> = {
      primary: "bg-primary text-primary-foreground hover:opacity-90",
      secondary: "border border-border bg-background hover:bg-muted",
      danger: "bg-red-600 text-white hover:bg-red-700",
      ghost: "hover:bg-muted",
    };
    return (
      <button
        ref={ref}
        className={clsx(base, variants[variant], className)}
        {...props}
      />
    );
  },
);

export const Input = forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={clsx(
        "w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
});

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx("rounded-lg border border-border bg-background p-4", className)}
      {...props}
    />
  );
}

export function Label(props: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className="text-sm font-medium" {...props} />;
}

const BADGE_TONES = {
  muted: "bg-muted text-foreground/80",
  amber: "bg-amber-100 text-amber-900",
  blue: "bg-blue-100 text-blue-900",
  green: "bg-green-100 text-green-900",
  red: "bg-red-100 text-red-900",
  gray: "bg-gray-100 text-gray-700",
} as const;

export function Badge({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: keyof typeof BADGE_TONES;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-mono",
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
