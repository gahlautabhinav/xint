// node_id helpers — mirror graph/schema/nodes.py.
// Canonical format: "<platform>:<@handle>", all lower-case.

export interface ParsedNodeId {
  platform: string;
  handle: string; // includes leading "@"
  bareHandle: string; // without "@"
}

export function makeNodeId(platform: string, handle: string): string {
  const h = handle.startsWith("@") ? handle : `@${handle}`;
  return `${platform.toLowerCase()}:${h.toLowerCase()}`;
}

export function parseNodeId(nodeId: string): ParsedNodeId {
  const idx = nodeId.indexOf(":");
  if (idx === -1) {
    // Defensive: treat the whole string as a twitter handle.
    const handle = nodeId.startsWith("@") ? nodeId : `@${nodeId}`;
    return { platform: "twitter", handle, bareHandle: handle.slice(1) };
  }
  const platform = nodeId.slice(0, idx);
  const handle = nodeId.slice(idx + 1);
  const bareHandle = handle.startsWith("@") ? handle.slice(1) : handle;
  return { platform, handle, bareHandle };
}

/** Strip a leading "@" and lower-case — for normalizing search input. */
export function normalizeHandle(raw: string): string {
  return raw.trim().replace(/^@+/, "").toLowerCase();
}
