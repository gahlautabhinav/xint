import type { ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";

interface StateProps {
  title: string;
  body?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, body, icon, action }: StateProps) {
  return (
    <div className="state" role="status">
      <span className="state__icon" aria-hidden>
        {icon ?? <Inbox size={40} strokeWidth={1.25} />}
      </span>
      <span className="state__title">{title}</span>
      {body && <p className="state__body">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title, body, action }: StateProps) {
  return (
    <div className="state state--error" role="alert">
      <span className="state__icon" aria-hidden>
        <AlertTriangle size={40} strokeWidth={1.25} />
      </span>
      <span className="state__title">{title}</span>
      {body && <p className="state__body">{body}</p>}
      {action}
    </div>
  );
}

export function LoadingState({ title = "Loading…" }: { title?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="state__icon spin-icon" aria-hidden>
        <Loader2 size={32} className="lucide-spin" />
      </span>
      <span className="state__title">{title}</span>
    </div>
  );
}
