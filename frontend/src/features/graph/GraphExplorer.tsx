import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { ElementDefinition } from "cytoscape";
import {
  Crosshair,
  Download,
  Network,
  Search,
  Shuffle,
  Target,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { makeNodeId, normalizeHandle, parseNodeId } from "@/lib/nodeId";
import type { RelType } from "@/lib/types";
import { Pill } from "@/components/Pill";
import { ErrorState, LoadingState } from "@/components/states";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

import { GraphCanvas, type EdgeSelection } from "./GraphCanvas";
import { EdgeInspector } from "./EdgeInspector";
import { NodeInspector } from "./NodeInspector";
import { RelTypeFilter } from "./RelTypeFilter";
import { Legend } from "./Legend";
import { mergeElements, subgraphToElements, type NodeDatum } from "./transform";
import "./graph.css";

const SUGGESTIONS = ["elonmusk", "sama", "naval", "balajis"];

export function GraphExplorer() {
  const reducedMotion = usePrefersReducedMotion();
  const [params, setParams] = useSearchParams();

  const [input, setInput] = useState(params.get("q") ?? "");
  const [depth, setDepth] = useState(Number(params.get("depth")) || 2);
  const [limit, setLimit] = useState(Number(params.get("limit")) || 200);

  const initialHandle = params.get("q") ? normalizeHandle(params.get("q")!) : null;
  const [root, setRoot] = useState<{ platform: string; handle: string } | null>(
    initialHandle ? { platform: "twitter", handle: initialHandle } : null,
  );

  const [elementsMap, setElementsMap] = useState<Map<string, ElementDefinition>>(
    new Map(),
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenRel, setHiddenRel] = useState<Set<string>>(new Set());
  const [focusMode, setFocusMode] = useState(false);
  const [focusHops, setFocusHops] = useState(1);
  const [selectedEdge, setSelectedEdge] = useState<EdgeSelection | null>(null);
  const [expandingId, setExpandingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fitSignal, setFitSignal] = useState(0);
  const [relayoutSignal, setRelayoutSignal] = useState(0);
  const noticeTimer = useRef<number | null>(null);

  const rootId = root ? makeNodeId(root.platform, root.handle) : null;

  // ── Initial subgraph query ─────────────────────────────────────────────
  const subgraphQuery = useQuery({
    queryKey: ["subgraph", root?.platform, root?.handle, depth, limit],
    queryFn: ({ signal }) =>
      api.getSubgraph(root!.handle, { platform: root!.platform, depth, limit, signal }),
    enabled: !!root,
    retry: false,
  });

  // Reset the accumulated graph whenever a fresh root subgraph arrives.
  useEffect(() => {
    if (!subgraphQuery.data || !rootId) return;
    const els = subgraphToElements(subgraphQuery.data, rootId);
    const fresh = new Map<string, ElementDefinition>();
    for (const el of els) fresh.set(String(el.data.id), el);
    setElementsMap(fresh);
    setSelectedId(rootId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subgraphQuery.data]);

  const flashNotice = useCallback((msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 4000);
  }, []);

  useEffect(() => () => {
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
  }, []);

  // ── Search submit ──────────────────────────────────────────────────────
  const runSearch = useCallback(
    (raw: string) => {
      const handle = normalizeHandle(raw);
      if (!handle) return;
      setRoot({ platform: "twitter", handle });
      setElementsMap(new Map());
      setSelectedId(null);
      setSelectedEdge(null);
      setHiddenRel(new Set());
      setFocusMode(false);
      const next = new URLSearchParams(params);
      next.set("q", handle);
      next.set("depth", String(depth));
      next.set("limit", String(limit));
      setParams(next, { replace: true });
    },
    [depth, limit, params, setParams],
  );

  // ── Expand a node (fetch its depth-1 subgraph and merge) ───────────────
  const expandNode = useCallback(
    async (id: string) => {
      const { platform, bareHandle } = parseNodeId(id);
      setExpandingId(id);
      try {
        const data = await api.getSubgraph(bareHandle, { platform, depth: 1, limit: 200 });
        const incoming = subgraphToElements(data, rootId ?? id);
        setElementsMap((prev) => {
          const { map, added } = mergeElements(prev, incoming, rootId ?? id);
          if (added.length === 0) flashNotice(`No new connections for @${bareHandle}.`);
          else flashNotice(`+${added.length} added from @${bareHandle}.`);
          return map;
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          flashNotice(`@${bareHandle} has no further connections in the graph.`);
        } else {
          flashNotice(err instanceof Error ? err.message : "Expansion failed.");
        }
      } finally {
        setExpandingId(null);
      }
    },
    [rootId, flashNotice],
  );

  // Inspector "Focus" action: isolate this node's neighbourhood + centre on it.
  const focusNode = useCallback((id: string) => {
    setSelectedId(id);
    setFocusMode(true);
    setFitSignal((s) => s + 1);
  }, []);

  const toggleRel = useCallback((rel: RelType) => {
    setHiddenRel((prev) => {
      const next = new Set(prev);
      if (next.has(rel)) next.delete(rel);
      else next.add(rel);
      return next;
    });
  }, []);

  // ── Derived ────────────────────────────────────────────────────────────
  const elements = useMemo(() => Array.from(elementsMap.values()), [elementsMap]);

  const { nodeCount, edgeCount, relCounts } = useMemo(() => {
    let nodes = 0;
    let edges = 0;
    const counts: Record<string, number> = {};
    for (const el of elementsMap.values()) {
      if (el.group === "nodes") nodes++;
      else {
        edges++;
        const rel = String(el.data.rel);
        counts[rel] = (counts[rel] ?? 0) + 1;
      }
    }
    return { nodeCount: nodes, edgeCount: edges, relCounts: counts };
  }, [elementsMap]);

  const selectedNode = useMemo<NodeDatum | null>(() => {
    if (!selectedId) return null;
    const el = elementsMap.get(selectedId);
    return el && el.group === "nodes" ? (el.data as NodeDatum) : null;
  }, [selectedId, elementsMap]);

  const exportJson = useCallback(() => {
    const out = {
      root: rootId,
      nodes: elements.filter((e) => e.group === "nodes").map((e) => e.data),
      edges: elements.filter((e) => e.group === "edges").map((e) => e.data),
    };
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${root?.handle ?? "graph"}-network.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [elements, root, rootId]);

  const hasGraph = nodeCount > 0;

  // ── Landing (no root yet) ──────────────────────────────────────────────
  if (!root) {
    return (
      <div className="explorer-landing">
        <div className="explorer-landing__inner reveal reveal-1">
          <span className="eyebrow">OSINT&nbsp;//&nbsp;NETWORK&nbsp;GRAPH</span>
          <h1 className="display-lg explorer-landing__title">
            Map the network
            <br />
            behind a handle.
          </h1>
          <p className="explorer-landing__lead body-lg text-mute">
            Enter a seed username to render its relationship graph — follows,
            mentions, replies, quotes and cross-platform links. Click any node to
            expand its neighborhood.
          </p>

          <form
            className="explorer-landing__search reveal reveal-2"
            onSubmit={(e) => {
              e.preventDefault();
              runSearch(input);
            }}
          >
            <div className="searchbar">
              <span className="searchbar__icon">
                <Search size={18} />
              </span>
              <input
                className="searchbar__input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="seed username — e.g. elonmusk"
                aria-label="Seed username"
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
              />
            </div>
            <Pill variant="primary" type="submit" icon={<Network size={15} />}>
              Render graph
            </Pill>
          </form>

          <div className="explorer-landing__suggest reveal reveal-3">
            <span className="eyebrow eyebrow--sm">Try</span>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="pill pill--sm"
                onClick={() => {
                  setInput(s);
                  runSearch(s);
                }}
                type="button"
              >
                @{s}
              </button>
            ))}
          </div>

          <p className="explorer-landing__note mono reveal reveal-4">
            Graph data comes from completed crawls. No results? Start one under{" "}
            <a className="ulink" href="/jobs">
              Jobs
            </a>
            .
          </p>
        </div>
      </div>
    );
  }

  // ── Explorer (root selected) ───────────────────────────────────────────
  return (
    <div className="explorer">
      {/* Toolbar */}
      <div className="explorer__toolbar">
        <form
          className="explorer__search"
          onSubmit={(e) => {
            e.preventDefault();
            runSearch(input);
          }}
        >
          <div className="searchbar">
            <span className="searchbar__icon">
              <Search size={16} />
            </span>
            <input
              className="searchbar__input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="seed username"
              aria-label="Seed username"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </form>

        <label className="explorer__control">
          <span className="eyebrow eyebrow--sm">Depth</span>
          <input
            className="input input--mini input--num"
            type="number"
            min={1}
            max={20}
            value={depth}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v) && v >= 1) setDepth(v);
            }}
          />
        </label>

        <label className="explorer__control">
          <span className="eyebrow eyebrow--sm">Limit</span>
          <input
            className="input input--mini input--num"
            type="number"
            min={1}
            max={10000}
            value={limit}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v) && v >= 1) setLimit(v);
            }}
          />
        </label>

        <Pill size="sm" onClick={() => runSearch(input)}>
          Apply
        </Pill>

        <div className="explorer__toolbar-spacer" />

        <Pill
          size="sm"
          icon={<Target size={14} />}
          active={focusMode}
          onClick={() => setFocusMode((f) => !f)}
          disabled={!selectedNode}
          title={
            selectedNode
              ? "Focus — dim everything beyond the selected node's neighbourhood"
              : "Select a node to focus on its neighbourhood"
          }
        >
          Focus
        </Pill>
        {focusMode && (
          <label className="explorer__control" title="Focus radius (hops)">
            <span className="eyebrow eyebrow--sm">Hops</span>
            <select
              className="input input--mini"
              value={focusHops}
              onChange={(e) => setFocusHops(Number(e.target.value))}
            >
              {[1, 2, 3].map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
        )}

        <Pill
          size="sm"
          icon={<Shuffle size={14} />}
          onClick={() => setRelayoutSignal((s) => s + 1)}
          disabled={!hasGraph}
          title="Re-run layout"
        >
          Relayout
        </Pill>
        <Pill
          size="sm"
          icon={<Crosshair size={14} />}
          onClick={() => setFitSignal((s) => s + 1)}
          disabled={!hasGraph}
          title="Fit to view"
        >
          Fit
        </Pill>
        <Pill
          size="sm"
          icon={<Download size={14} />}
          onClick={exportJson}
          disabled={!hasGraph}
          title="Export visible graph as JSON"
        >
          Export
        </Pill>
      </div>

      {/* Stage */}
      <div className="explorer__stage">
        {subgraphQuery.isLoading && (
          <div className="explorer__overlay">
            <LoadingState title={`Building @${root.handle}'s graph…`} />
          </div>
        )}

        {subgraphQuery.isError && (
          <div className="explorer__overlay">
            <ErrorState
              title={
                subgraphQuery.error instanceof ApiError &&
                subgraphQuery.error.status === 404
                  ? "Not in the graph yet"
                  : "Couldn't load the graph"
              }
              body={
                subgraphQuery.error instanceof ApiError &&
                subgraphQuery.error.status === 404 ? (
                  <>
                    @{root.handle} hasn't been crawled. Start a crawl under{" "}
                    <a className="ulink" href="/jobs">
                      Jobs
                    </a>{" "}
                    seeded on this handle, then come back.
                  </>
                ) : (
                  (subgraphQuery.error as Error)?.message
                )
              }
              action={
                <Pill onClick={() => subgraphQuery.refetch()}>Retry</Pill>
              }
            />
          </div>
        )}

        {!subgraphQuery.isLoading && !subgraphQuery.isError && (
          <>
            <GraphCanvas
              elements={elements}
              rootId={rootId}
              hiddenRelTypes={hiddenRel}
              selectedId={selectedId}
              onSelectNode={(id) => { setSelectedEdge(null); setSelectedId(id); }}
              onSelectEdge={(edge) => { setSelectedId(null); setSelectedEdge(edge); }}
              onExpandNode={expandNode}
              fitSignal={fitSignal}
              relayoutSignal={relayoutSignal}
              reducedMotion={reducedMotion}
              focusMode={focusMode}
              focusHops={focusHops}
            />

            {/* Top-left: rel filter + stats */}
            <div className="explorer__hud explorer__hud--tl">
              <RelTypeFilter
                hidden={hiddenRel}
                counts={relCounts}
                onToggle={toggleRel}
              />
              <div className="explorer__stats mono" aria-live="polite">
                <span className="tabular">{nodeCount}</span> nodes ·{" "}
                <span className="tabular">{edgeCount}</span> edges
              </div>
            </div>

            {/* Bottom-left: legend */}
            <div className="explorer__hud explorer__hud--bl">
              <Legend />
            </div>

            {/* Right: node inspector */}
            {selectedNode && !selectedEdge && (
              <NodeInspector
                key={selectedNode.id}
                node={selectedNode}
                onClose={() => setSelectedId(null)}
                onExpand={expandNode}
                onFocus={focusNode}
                expanding={expandingId === selectedNode.id}
              />
            )}

            {/* Right: edge inspector */}
            {selectedEdge && !selectedNode && (
              <EdgeInspector
                key={selectedEdge.id}
                edge={selectedEdge}
                onClose={() => setSelectedEdge(null)}
              />
            )}

            {notice && (
              <div className="explorer__toast mono" role="status">
                {notice}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
