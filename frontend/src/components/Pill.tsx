import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "outline" | "primary";

interface PillProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "md" | "sm";
  active?: boolean;
  icon?: ReactNode;
  loading?: boolean;
  children?: ReactNode;
}

/** The brand's universal interactive shape — an outline pill. */
export function Pill({
  variant = "outline",
  size = "md",
  active = false,
  icon,
  loading = false,
  children,
  className,
  disabled,
  ...rest
}: PillProps) {
  const classes = [
    "pill",
    size === "sm" ? "pill--sm" : "",
    variant === "primary" ? "pill--primary" : "",
    active ? "pill--active" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading ? (
        <span className="spinner pill__icon" aria-hidden />
      ) : (
        icon && (
          <span className="pill__icon" aria-hidden>
            {icon}
          </span>
        )
      )}
      {children}
    </button>
  );
}
