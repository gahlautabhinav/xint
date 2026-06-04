import { useState } from "react";
import { ChevronDown } from "lucide-react";

export function Legend() {
  const [open, setOpen] = useState(false);
  return (
    <div className={`legend${open ? " legend--open" : ""}`}>
      <button
        className="legend__toggle eyebrow eyebrow--sm"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        type="button"
      >
        Legend <ChevronDown size={13} />
      </button>
      {open && (
        <div className="legend__body">
          <div className="legend__row">
            <span className="legend__dot" style={{ background: "#ff7a17" }} />
            <span>Seed account</span>
          </div>
          <div className="legend__row">
            <span
              className="legend__dot"
              style={{ background: "#ffffff", boxShadow: "0 0 0 2px #a0c3ec inset" }}
            />
            <span>Verified</span>
          </div>
          <div className="legend__row">
            <span className="legend__dot" style={{ background: "#ffffff" }} />
            <span>Twitter / X</span>
          </div>
          <div className="legend__row">
            <span
              className="legend__dot"
              style={{ background: "#ffffff", opacity: 0.45 }}
            />
            <span>Discovered (not yet scraped)</span>
          </div>
          <div className="legend__row">
            <span className="legend__dot" style={{ background: "#7c3aed" }} />
            <span>Cross-platform node</span>
          </div>
          <p className="legend__hint mono">node size ∝ reach · double-click to expand</p>
        </div>
      )}
    </div>
  );
}
