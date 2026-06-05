import { useEffect, useRef } from "react";
import cytoscape, {
  type Core,
  type ElementDefinition,
  type Layouts,
  type NodeSingular,
} from "cytoscape";
import cola from "cytoscape-cola";
import { buildStylesheet } from "./cytoStyle";

let registered = false;
if (!registered) {
  cytoscape.use(cola);
  registered = true;
}

export interface EdgeSelection {
  id: string;
  source: string;
  target: string;
  rel: string;
  tweet_ids: string[];
  source_handle: string | null;
}

interface GraphCanvasProps {
  elements: ElementDefinition[];
  rootId: string | null;
  hiddenRelTypes: Set<string>;
  selectedId: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (edge: EdgeSelection | null) => void;
  onExpandNode: (id: string) => void;
  fitSignal: number;
  relayoutSignal: number;
  reducedMotion: boolean;
  focusMode: boolean;
  focusHops: number;
  onReady?: (cy: Core) => void;
}

// Below this zoom, fade labels of "minor" nodes so the canvas stays legible.
const LABEL_ZOOM = 0.6;
// A node keeps its label at any zoom if it's the root, selected, a high-degree
// hub, or a large account.
function isLabelHub(n: NodeSingular): boolean {
  return (
    Boolean(n.data("isRoot")) ||
    n.selected() ||
    n.degree(false) >= 4 ||
    (Number(n.data("followers")) || 0) >= 100_000
  );
}

// Force-directed layout via cola. `infinite:false` settles within
// maxSimulationTime then stops, so a settled graph costs nothing.
function colaBounded(randomize: boolean, fit: boolean, animate: boolean) {
  return {
    name: "cola",
    animate,
    randomize,
    fit,
    padding: 48,
    maxSimulationTime: 2000,
    convergenceThreshold: 0.01,
    nodeSpacing: 14,
    edgeLength: 110,
    avoidOverlap: true,
    handleDisconnected: true,
    infinite: false,
  } as unknown as cytoscape.LayoutOptions;
}

// Live simulation kicked while a node is being dragged — neighbours repel and
// relax in real time (Obsidian-like). Runs only for the duration of the drag
// (started on grab, stopped on free), so the perpetual loop is user-bounded.
function colaLive(animate: boolean) {
  return {
    name: "cola",
    animate,
    fit: false,
    infinite: true,
    nodeSpacing: 14,
    edgeLength: 110,
    avoidOverlap: true,
    handleDisconnected: true,
  } as unknown as cytoscape.LayoutOptions;
}

export function GraphCanvas({
  elements,
  rootId,
  hiddenRelTypes,
  selectedId,
  onSelectNode,
  onSelectEdge,
  onExpandNode,
  fitSignal,
  relayoutSignal,
  reducedMotion,
  focusMode,
  focusHops,
  onReady,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const layoutRef = useRef<Layouts | null>(null);
  const labelRaf = useRef(0);
  const firstLayoutDone = useRef(false);
  // Keep latest callbacks in refs so the cy event handlers (bound once) stay current.
  const handlers = useRef({ onSelectNode, onSelectEdge, onExpandNode });
  handlers.current = { onSelectNode, onSelectEdge, onExpandNode };
  // Mirror reducedMotion into a ref so the once-bound drag handlers read it live.
  const rmRef = useRef(reducedMotion);
  rmRef.current = reducedMotion;

  // Stable across renders; reads cy/layout from refs at call time. Always stops
  // the prior layout before starting a new one so re-runs never stack (the real
  // guard against a layout "restart storm" on rapid expands).
  const runLayout = useRef((opts: cytoscape.LayoutOptions) => {
    // Stop any prior layout FIRST — including a still-running infinite drag sim —
    // before the empty-graph bail, so a stale simulation can never survive.
    layoutRef.current?.stop();
    layoutRef.current = null;
    const cy = cyRef.current;
    if (!cy || cy.elements().empty()) return;
    const l = cy.layout(opts);
    layoutRef.current = l;
    l.run();
  }).current;

  // Toggle `label-faint` on minor nodes based on the current zoom. Stable across
  // renders; reads cy from the ref so the bound zoom handler stays current.
  const applyLabels = useRef(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const faint = cy.zoom() < LABEL_ZOOM;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        if (faint && !isLabelHub(n)) n.addClass("label-faint");
        else n.removeClass("label-faint");
      });
    });
  }).current;

  // ── Init cytoscape once ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      style: buildStylesheet(),
      elements: [],
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.25,
      boxSelectionEnabled: false,
      pixelRatio: "auto",
    });
    cyRef.current = cy;

    cy.on("tap", "node", (evt) => {
      handlers.current.onSelectEdge(null);
      handlers.current.onSelectNode(evt.target.id());
    });
    cy.on("tap", "edge", (evt) => {
      handlers.current.onSelectNode(null);
      const e = evt.target;
      handlers.current.onSelectEdge({
        id: e.id(),
        source: e.data("source") as string,
        target: e.data("target") as string,
        rel: e.data("rel") as string,
        tweet_ids: (e.data("tweet_ids") as string[]) || [],
        source_handle: (e.data("source_handle") as string) || null,
      });
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        handlers.current.onSelectNode(null);
        handlers.current.onSelectEdge(null);
      }
    });
    cy.on("dbltap", "node", (evt) => handlers.current.onExpandNode(evt.target.id()));

    // Hover focus — dim everything except the node's closed neighborhood and
    // reveal that neighborhood's labels (via `.nbr`) even when zoomed out.
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      const nbhd = node.closedNeighborhood();
      cy.elements().not(nbhd).addClass("dimmed");
      nbhd.nodes().addClass("nbr");
      node.addClass("hl-node");
      node.connectedEdges().addClass("hl-edge");
      const el = cy.container();
      if (el) el.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dimmed hl-node hl-edge nbr");
      const el = cy.container();
      if (el) el.style.cursor = "default";
    });

    // Zoom-aware labels — throttled to one update per animation frame.
    cy.on("zoom", () => {
      if (labelRaf.current) return;
      labelRaf.current = requestAnimationFrame(() => {
        labelRaf.current = 0;
        applyLabels();
      });
    });

    // Live-on-drag: start a continuous cola sim while a node is held so the
    // neighbourhood repels/relaxes in real time, then settle + stop on release.
    cy.on("grab", "node", () => {
      if (rmRef.current) return; // reduced motion → no live sim
      runLayout(colaLive(true));
    });
    cy.on("free", "node", () => {
      runLayout(colaBounded(false, false, !rmRef.current));
    });

    onReady?.(cy);

    return () => {
      if (labelRaf.current) cancelAnimationFrame(labelRaf.current);
      layoutRef.current?.stop();
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Sync elements (incremental add / remove / data update) ─────────────
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const incomingIds = new Set(elements.map((e) => String(e.data.id)));
    const newOnes: ElementDefinition[] = [];

    cy.batch(() => {
      // remove gone
      cy.elements().forEach((ele) => {
        if (!incomingIds.has(ele.id())) ele.remove();
      });
      // add new / update existing node data
      for (const el of elements) {
        const id = String(el.data.id);
        const existing = cy.getElementById(id);
        if (existing.empty()) {
          newOnes.push(el);
        } else if (el.group === "nodes") {
          existing.data(el.data);
        }
      }
      if (newOnes.length) cy.add(newOnes);
    });

    if (newOnes.length === 0) {
      applyLabels();
      return;
    }

    const randomize = !firstLayoutDone.current;
    runLayout(colaBounded(randomize, true, !reducedMotion));
    firstLayoutDone.current = true;
    applyLabels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements, reducedMotion]);

  // ── Local focus mode ───────────────────────────────────────────────────
  // Dim everything beyond the selected node's N-hop neighbourhood. Uses a
  // dedicated `.focus-dim` class so it doesn't fight hover's `.dimmed`.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass("focus-dim");
      if (focusMode && selectedId) {
        const node = cy.getElementById(selectedId);
        if (node.nonempty()) {
          let nbhd = node.closedNeighborhood();
          for (let i = 1; i < focusHops; i++) nbhd = nbhd.closedNeighborhood();
          cy.elements().not(nbhd).addClass("focus-dim");
        }
      }
    });
  }, [focusMode, focusHops, selectedId, elements]);

  // Reset the "first layout" flag whenever the root changes (new search).
  useEffect(() => {
    if (elements.length === 0) firstLayoutDone.current = false;
  }, [elements.length, rootId]);

  // ── Rel-type visibility filter ─────────────────────────────────────────
  // Depends on `elements` on purpose: when expansion adds new edges they must
  // also pick up the current hide-set, so re-run whenever the graph changes.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.edges().forEach((edge) => {
        const rel = String(edge.data("rel"));
        if (hiddenRelTypes.has(rel)) edge.addClass("rel-hidden");
        else edge.removeClass("rel-hidden");
      });
    });
  }, [hiddenRelTypes, elements]);

  // ── External selection sync ────────────────────────────────────────────
  // Depends on `elements` on purpose: selecting the root happens before its
  // node lands in cy, so re-run when the graph changes to apply it once present.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const current = cy.$(":selected");
    if (selectedId) {
      const target = cy.getElementById(selectedId);
      if (target.nonempty() && !target.selected()) {
        current.unselect();
        target.select();
      }
    } else if (current.nonempty()) {
      current.unselect();
    }
  }, [selectedId, elements]);

  // ── Fit / relayout signals ─────────────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || cy.elements().empty()) return;
    cy.animate({ fit: { eles: cy.elements(), padding: 48 } }, { duration: reducedMotion ? 0 : 320 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitSignal]);

  useEffect(() => {
    runLayout(colaBounded(false, true, !reducedMotion));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [relayoutSignal]);

  return (
    <div
      ref={containerRef}
      className="graph-canvas"
      role="application"
      aria-label="Interactive account relationship graph. Use the accounts list and node inspector for a non-visual view of the same data."
    />
  );
}
