import { ExternalLink, X } from "lucide-react";
import { parseNodeId } from "@/lib/nodeId";
import { REL_META } from "./relTypes";
import type { EdgeSelection } from "./GraphCanvas";
import type { RelType } from "@/lib/types";

interface EdgeInspectorProps {
  edge: EdgeSelection;
  onClose: () => void;
}

export function EdgeInspector({ edge, onClose }: EdgeInspectorProps) {
  const { bareHandle: srcHandle } = parseNodeId(edge.source);
  const { bareHandle: dstHandle } = parseNodeId(edge.target);
  const meta = REL_META[edge.rel as RelType];
  // Source handle for tweet URL construction: stored prop takes precedence,
  // then fall back to the source node handle.
  const tweetAuthor = edge.source_handle ?? srcHandle;
  const hasTweets = edge.tweet_ids.length > 0;

  return (
    <aside className="inspector reveal" aria-label={`Edge from @${srcHandle} to @${dstHandle}`}>
      <div className="inspector__head">
        <span className="eyebrow eyebrow--sm">EDGE</span>
        <button
          className="iconbtn"
          onClick={onClose}
          aria-label="Close edge inspector"
          type="button"
        >
          <X size={16} />
        </button>
      </div>

      <div className="edge-inspector__rel">
        <span
          className="edge-inspector__swatch"
          style={{ background: meta?.color ?? "#7d8187" }}
          aria-hidden
        />
        <span className="edge-inspector__label display-sm">
          {meta?.label ?? edge.rel}
        </span>
      </div>

      <div className="edge-inspector__accounts">
        <a
          className="edge-inspector__handle mono"
          href={`/?q=${srcHandle}`}
          title={`Open @${srcHandle} in graph`}
        >
          @{srcHandle}
        </a>
        <span className="edge-inspector__arrow">→</span>
        <a
          className="edge-inspector__handle mono"
          href={`/?q=${dstHandle}`}
          title={`Open @${dstHandle} in graph`}
        >
          @{dstHandle}
        </a>
      </div>

      {meta?.description && (
        <p className="inspector__bio">{meta.description}</p>
      )}

      {hasTweets ? (
        <div className="edge-inspector__evidence">
          <span className="eyebrow eyebrow--sm">
            Source tweets ({edge.tweet_ids.length})
          </span>
          <div className="edge-inspector__tweets">
            {edge.tweet_ids.map((tid, i) => {
              const url = `https://x.com/${tweetAuthor}/status/${tid}`;
              return (
                <a
                  key={tid}
                  className="edge-inspector__tweet"
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={12} aria-hidden />
                  <span className="mono">Tweet #{i + 1}</span>
                  <span className="edge-inspector__tid mono">{tid}</span>
                </a>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="inspector__stub">
          {edge.rel === "FOLLOWS"
            ? "Discovered via the following list — no single tweet is the source."
            : edge.rel === "CROSS_PLATFORM_LINK"
            ? "Detected from the account bio or pinned tweet."
            : "No tweet IDs recorded for this edge yet. Re-crawl to capture evidence."}
        </p>
      )}
    </aside>
  );
}
