import type { RelType } from "@/lib/types";

export interface RelMeta {
  type: RelType;
  label: string;
  color: string; // resolved hex (cytoscape can't read CSS vars)
  description: string;
}

// Accent map mirrors --rel-* tokens in tokens.css (cytoscape needs literals).
export const REL_META: Record<RelType, RelMeta> = {
  FOLLOWS: {
    type: "FOLLOWS",
    label: "Follows",
    color: "#a0c3ec",
    description: "Account follows another account.",
  },
  MENTIONS: {
    type: "MENTIONS",
    label: "Mentions",
    color: "#ff7a17",
    description: "Mentioned @handle in a post body.",
  },
  REPLIES_TO: {
    type: "REPLIES_TO",
    label: "Replies",
    color: "#ffc285",
    description: "Posted a direct reply.",
  },
  QUOTE_TWEETS: {
    type: "QUOTE_TWEETS",
    label: "Quotes",
    color: "#c4b5fd",
    description: "Quote-tweeted a post.",
  },
  RETWEETS: {
    type: "RETWEETS",
    label: "Reposts",
    color: "#34d399",
    description: "Reposted (retweeted) a post.",
  },
  CROSS_PLATFORM_LINK: {
    type: "CROSS_PLATFORM_LINK",
    label: "Cross-platform",
    color: "#7c3aed",
    description: "Linked profile on another platform.",
  },
};

export const REL_LIST: RelMeta[] = Object.values(REL_META);

export function relColor(rel: string): string {
  return REL_META[rel as RelType]?.color ?? "#7d8187";
}

// Platform → node accent (cross-platform pivots get distinct colors).
export const PLATFORM_COLOR: Record<string, string> = {
  twitter: "#ffffff",
  github: "#c4b5fd",
  instagram: "#ff7a17",
  linkedin: "#a0c3ec",
  tiktok: "#ffc285",
};

export function platformColor(platform: string): string {
  return PLATFORM_COLOR[platform.toLowerCase()] ?? "#dadbdf";
}
