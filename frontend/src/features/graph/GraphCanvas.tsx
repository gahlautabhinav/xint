import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { buildStylesheet } from "./cytoStyle";

let registered = false;
if (!registered) {
  cytoscape.use(fcose);
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

function layoutOptions(randomize: boolean, animate: boolean) {
  return {
    name: "fcose",
    quality: "default",
    randomize,
    animate,
    animationDuration: 480,
    animationEasing: "ease-out",
    fit: true,
    padding: 48,
    nodeSeparation: 95,
    idealEdgeLength: 95,
    nodeRepulsion: 6500,
    gravity: 0.25,
    numIter: 2500,
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
  const firstLayoutDone = useRef(false);
  // Keep latest callbacks in refs so the cy event handlers (bound once) stay current.
  const handlers = useRef({ onSelectNode, onExpandNode });
  handlers.current = { onSelectNode, onExpandNode };

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

    onReady?.(cy);

    return () => {
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

    const animate = !reducedMotion;
    const randomize = !firstLayoutDone.current;
    cy.layout(layoutOptions(randomize, animate)).run();
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
    const cy = cyRef.current;
    if (!cy || cy.elements().empty()) return;
    cy.layout(layoutOptions(false, !reducedMotion)).run();
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
