import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition, type Layouts } from "cytoscape";
import cola from "cytoscape-cola";
import { buildStylesheet } from "./cytoStyle";

let registered = false;
if (!registered) {
  cytoscape.use(cola);
  registered = true;
}

interface GraphCanvasProps {
  elements: ElementDefinition[];
  rootId: string | null;
  hiddenRelTypes: Set<string>;
  selectedId: string | null;
  onSelectNode: (id: string | null) => void;
  onExpandNode: (id: string) => void;
  fitSignal: number;
  relayoutSignal: number;
  reducedMotion: boolean;
  onReady?: (cy: Core) => void;
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
  onExpandNode,
  fitSignal,
  relayoutSignal,
  reducedMotion,
  onReady,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const layoutRef = useRef<Layouts | null>(null);
  const firstLayoutDone = useRef(false);
  // Keep latest callbacks in refs so the cy event handlers (bound once) stay current.
  const handlers = useRef({ onSelectNode, onExpandNode });
  handlers.current = { onSelectNode, onExpandNode };
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

    cy.on("tap", "node", (evt) => handlers.current.onSelectNode(evt.target.id()));
    cy.on("tap", (evt) => {
      if (evt.target === cy) handlers.current.onSelectNode(null);
    });
    cy.on("dbltap", "node", (evt) => handlers.current.onExpandNode(evt.target.id()));

    // Hover focus — dim everything except the node's closed neighborhood.
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      const nbhd = node.closedNeighborhood();
      cy.elements().not(nbhd).addClass("dimmed");
      node.addClass("hl-node");
      node.connectedEdges().addClass("hl-edge");
      const el = cy.container();
      if (el) el.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dimmed hl-node hl-edge");
      const el = cy.container();
      if (el) el.style.cursor = "default";
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

    if (newOnes.length === 0) return;

    const randomize = !firstLayoutDone.current;
    runLayout(colaBounded(randomize, true, !reducedMotion));
    firstLayoutDone.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements, reducedMotion]);

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
