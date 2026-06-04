import type { EdgeSingular, NodeSingular, StylesheetStyle } from "cytoscape";
import { platformColor, relColor } from "./relTypes";

type StyleObj = StylesheetStyle["style"];

// Node radius scales with reach: followers (log) blended with live degree.
function nodeSize(ele: NodeSingular): number {
  const followers = Number(ele.data("followers")) || 0;
  const degree = ele.degree(false);
  const followerScale = followers > 0 ? Math.log10(followers + 1) * 6 : 0; // ~0–42
  const degreeScale = Math.min(degree * 2.2, 26);
  const base = 16 + Math.max(followerScale, degreeScale);
  return ele.data("isRoot") ? Math.max(base, 46) : base;
}

export function buildStylesheet(): StylesheetStyle[] {
  return [
    {
      selector: "node",
      style: {
        width: nodeSize,
        height: nodeSize,
        "background-color": (ele: NodeSingular) =>
          ele.data("isRoot") ? "#ff7a17" : platformColor(String(ele.data("platform"))),
        "background-opacity": (ele: NodeSingular) =>
          ele.data("hasProfile") || ele.data("isRoot") ? 1 : 0.45,
        "border-width": 1.5,
        "border-color": "#0a0a0a",
        "border-opacity": 1,
        label: "data(label)",
        color: "#dadbdf",
        "font-family": "Geist Mono Variable, Geist Mono, monospace",
        "font-size": 11,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 5,
        "min-zoomed-font-size": 9,
        "text-background-color": "#0a0a0a",
        "text-background-opacity": 0.55,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "transition-property": "background-opacity, border-color, opacity",
        "transition-duration": 140,
      } as StyleObj,
    },
    {
      selector: "node[?isRoot]",
      style: {
        "border-width": 2,
        "border-color": "#ffc285",
        color: "#ffffff",
        "font-size": 13,
      } as StyleObj,
    },
    {
      selector: "node[?verified]",
      style: {
        "border-width": 2.5,
        "border-color": "#a0c3ec",
      } as StyleObj,
    },
    {
      selector: "node:selected",
      style: {
        "border-width": 3,
        "border-color": "#ffffff",
        color: "#ffffff",
        "z-index": 999,
      } as StyleObj,
    },
    // ── Edges ──────────────────────────────────────────────────────────
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        width: (ele: EdgeSingular) => 1 + Math.min(Number(ele.data("weight")) || 1, 6) * 0.4,
        "line-color": (ele: EdgeSingular) => relColor(String(ele.data("rel"))),
        "target-arrow-color": (ele: EdgeSingular) => relColor(String(ele.data("rel"))),
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.8,
        "line-opacity": 0.5,
        "transition-property": "line-opacity, width",
        "transition-duration": 140,
      } as StyleObj,
    },
    {
      selector: "edge:selected",
      style: {
        "line-opacity": 1,
        width: 3,
      } as StyleObj,
    },
    // ── Interaction classes ────────────────────────────────────────────
    {
      selector: ".hl-node",
      style: {
        "border-color": "#ffffff",
        "border-width": 3,
        "z-index": 998,
      } as StyleObj,
    },
    {
      selector: ".hl-edge",
      style: {
        "line-opacity": 1,
        width: 2.5,
        "z-index": 997,
      } as StyleObj,
    },
    {
      selector: ".dimmed",
      style: {
        opacity: 0.12,
      } as StyleObj,
    },
    {
      selector: ".rel-hidden",
      style: {
        display: "none",
      } as StyleObj,
    },
  ];
}
