// API response types — mirror the FastAPI Pydantic schemas in api/schemas/.

export interface GraphNode {
  node_id: string; // "platform:@handle", lower-cased
  labels: string[]; // e.g. ["Account"]
  props: NodeProps;
}

export interface NodeProps {
  display_name?: string;
  bio?: string;
  followers_count?: number;
  is_verified?: boolean;
  scrape_depth?: number;
  platform?: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  src: string;
  dst: string;
  rel_type: RelType | string;
  props: EdgeProps;
}

export interface EdgeProps {
  weight?: number;
  platform?: string;
  [key: string]: unknown;
}

export interface SubgraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface NeighborsResponse {
  node_id: string;
  neighbors: GraphNode[];
}

// Relationship types — mirror graph/schema/edges.py
export const REL_TYPES = [
  "FOLLOWS",
  "MENTIONS",
  "REPLIES_TO",
  "QUOTE_TWEETS",
  "CROSS_PLATFORM_LINK",
] as const;

export type RelType = (typeof REL_TYPES)[number];

// ── Jobs ──────────────────────────────────────────────────────────────
export type JobStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface Job {
  id: string;
  seed_username: string;
  platform: string;
  max_depth: number;
  max_accounts: number;
  status: JobStatus | string;
  accounts_scraped: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobListResponse {
  items: Job[];
  total: number;
}

export interface JobEvent {
  id: string;
  job_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface JobEventsResponse {
  events: JobEvent[];
  last_sequence: number;
}

export interface JobCreate {
  seed_username: string;
  max_depth: number;
  max_accounts: number;
  max_following: number;
  max_followers: number;
  rate_profile: "conservative" | "moderate" | "aggressive";
  proxy_urls: string[];
}

// ── Accounts ──────────────────────────────────────────────────────────
export interface Account {
  id: string;
  username: string;
  platform: string;
  display_name: string | null;
  bio: string | null;
  website: string | null;
  followers_count: number;
  following_count: number;
  is_verified: boolean;
  scraped_at: string | null;
  scrape_depth: number;
}

export interface AccountListResponse {
  items: Account[];
  total: number;
}
