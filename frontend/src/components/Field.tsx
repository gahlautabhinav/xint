import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

function FieldShell({ label, hint, error, children }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {children(id, describedBy)}
      {hint && !error && (
        <span className="field__hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field__error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

interface TextFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
}

export function TextField({ label, hint, error, className, ...rest }: TextFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <input
          id={id}
          className={["input", error ? "input--invalid" : "", className ?? ""]
            .filter(Boolean)
            .join(" ")}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
}

interface SelectFieldProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function SelectField({
  label,
  hint,
  error,
  options,
  className,
  ...rest
}: SelectFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <select
          id={id}
          className={["input", className ?? ""].filter(Boolean).join(" ")}
          aria-describedby={describedBy}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}
