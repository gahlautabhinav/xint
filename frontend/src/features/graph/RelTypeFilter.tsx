import type { RelType } from "@/lib/types";
import { REL_LIST } from "./relTypes";

interface RelTypeFilterProps {
  hidden: Set<string>;
  counts: Record<string, number>;
  onToggle: (rel: RelType) => void;
}

export function RelTypeFilter({ hidden, counts, onToggle }: RelTypeFilterProps) {
  return (
    <div className="relfilter" role="group" aria-label="Filter by relationship type">
      {REL_LIST.map((meta) => {
        const isHidden = hidden.has(meta.type);
        const count = counts[meta.type] ?? 0;
        return (
          <button
            key={meta.type}
            type="button"
            className={`relchip${isHidden ? " relchip--off" : ""}`}
            onClick={() => onToggle(meta.type)}
            aria-pressed={!isHidden}
            title={meta.description}
            disabled={count === 0}
          >
            <span
              className="relchip__swatch"
              style={{ background: meta.color }}
              aria-hidden
            />
            <span>{meta.label}</span>
            <span className="relchip__count mono">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
