import type { ElementDefinition } from "cytoscape";
import type { GraphEdge, GraphNode, SubgraphResponse } from "@/lib/types";
import { parseNodeId } from "@/lib/nodeId";

export interface NodeDatum {
  id: string;
  label: string; // "@handle"
  platform: string;
  displayName: string;
  followers: number;
  verified: boolean;
  depth: number;
  isRoot: boolean;
  hasProfile: boolean; // true once we have scraped props (vs a stub)
}

export function nodeToDatum(node: GraphNode, rootId: string): NodeDatum {
  const { platform, handle } = parseNodeId(node.node_id);
  const p = node.props ?? {};
  const followers = typeof p.followers_count === "number" ? p.followers_count : 0;
  const hasProfile =
    p.display_name !== undefined ||
    p.bio !== undefined ||
    p.followers_count !== undefined ||
    p.is_verified !== undefined;
  return {
    id: node.node_id,
    label: handle,
    platform: p.platform ?? platform,
    displayName: (p.display_name as string) || "",
    followers,
    verified: Boolean(p.is_verified),
    depth: typeof p.scrape_depth === "number" ? p.scrape_depth : 99,
    isRoot: node.node_id === rootId,
    hasProfile,
  };
}

function edgeId(e: GraphEdge): string {
  return `${e.src}__${e.rel_type}__${e.dst}`;
}

/** Convert an API subgraph into cytoscape elements. */
export function subgraphToElements(
  data: SubgraphResponse,
  rootId: string,
): ElementDefinition[] {
  const nodes: ElementDefinition[] = data.nodes.map((n) => ({
    group: "nodes",
    data: { ...nodeToDatum(n, rootId) },
  }));

  const edges: ElementDefinition[] = data.edges.map((e) => ({
    group: "edges",
    data: {
      id: edgeId(e),
      source: e.src,
      target: e.dst,
      rel: e.rel_type,
      weight: typeof e.props?.weight === "number" ? e.props.weight : 1,
    },
  }));

  return [...nodes, ...edges];
}

/**
 * Merge incoming elements into an existing keyed map. Returns the new map and
 * the list of element ids that are genuinely new (for targeted layout).
 */
export function mergeElements(
  existing: Map<string, ElementDefinition>,
  incoming: ElementDefinition[],
  rootId: string,
): { map: Map<string, ElementDefinition>; added: string[] } {
  const map = new Map(existing);
  const added: string[] = [];

  for (const el of incoming) {
    const id = String(el.data.id);
    if (el.group === "nodes") {
      const prev = map.get(id);
      if (!prev) {
        added.push(id);
        map.set(id, { ...el, data: { ...el.data, isRoot: id === rootId } });
      } else {
        // Merge — prefer the richer (profiled) datum so stubs upgrade in place.
        const merged = {
          ...prev.data,
          ...el.data,
          isRoot: id === rootId,
          // never downgrade a profiled node back to a stub
          hasProfile: prev.data.hasProfile || el.data.hasProfile,
          displayName: el.data.displayName || prev.data.displayName,
          followers: Math.max(Number(prev.data.followers) || 0, Number(el.data.followers) || 0),
        };
        map.set(id, { ...prev, data: merged });
      }
    } else {
      if (!map.has(id)) {
        added.push(id);
        map.set(id, el);
      }
    }
  }
  return { map, added };
}
