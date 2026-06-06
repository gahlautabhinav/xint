// Thin typed fetch client for the xint FastAPI backend.
//
// Base URL resolution:
//   - VITE_API_BASE_URL if set (e.g. "https://osint.example.com")
//   - otherwise "/api", which the Vite dev server proxies to localhost:8000
// Optional API key (X-API-Key header) via VITE_API_KEY.

import type {
  Account,
  AccountListResponse,
  DiscoverResponse,
  GeoLocationsResponse,
  HashtagAnalysisResponse,
  IntersectionResponse,
  Job,
  JobCreate,
  JobEventsResponse,
  JobListResponse,
  NeighborsResponse,
  RelType,
  SubgraphResponse,
  UsernameEnumResponse,
} from "./types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "/api";
const API_KEY: string | undefined = import.meta.env.VITE_API_KEY || undefined;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildUrl(path: string, params?: Record<string, unknown>): string {
  const url = new URL(
    `${BASE_URL}${path}`,
    // BASE_URL may be relative ("/api"); resolve against the page origin.
    window.location.origin,
  );
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const v of value) url.searchParams.append(key, String(v));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  opts: {
    method?: string;
    params?: Record<string, unknown>;
    body?: unknown;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.params), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the API. Is the backend running on :8000?",
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data?.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      /* non-JSON error body — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ── Graph ───────────────────────────────────────────────────────────────
export const api = {
  getSubgraph(
    handle: string,
    opts: { platform?: string; depth?: number; limit?: number; signal?: AbortSignal } = {},
  ): Promise<SubgraphResponse> {
    return request<SubgraphResponse>(`/graph/${encodeURIComponent(handle)}/subgraph`, {
      params: {
        platform: opts.platform ?? "twitter",
        depth: opts.depth ?? 2,
        limit: opts.limit ?? 200,
      },
      signal: opts.signal,
    });
  },

  getNeighbors(
    handle: string,
    opts: { platform?: string; depth?: number; relTypes?: RelType[]; signal?: AbortSignal } = {},
  ): Promise<NeighborsResponse> {
    return request<NeighborsResponse>(`/graph/${encodeURIComponent(handle)}/neighbors`, {
      params: {
        platform: opts.platform ?? "twitter",
        depth: opts.depth ?? 1,
        rel_types: opts.relTypes,
      },
      signal: opts.signal,
    });
  },

  // ── Jobs ───────────────────────────────────────────────────────────────
  listJobs(opts: { limit?: number; offset?: number } = {}): Promise<JobListResponse> {
    return request<JobListResponse>(`/jobs`, {
      params: { limit: opts.limit ?? 50, offset: opts.offset ?? 0 },
    });
  },

  getJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}`);
  },

  getJobEvents(jobId: string, since = 0): Promise<JobEventsResponse> {
    return request<JobEventsResponse>(`/jobs/${jobId}/events`, { params: { since } });
  },

  createJob(body: JobCreate): Promise<Job> {
    return request<Job>(`/jobs`, { method: "POST", body });
  },

  discoverAll(body: {
    seed: string;
    depth?: number;
    max_accounts?: number;
    platform?: string;
  }): Promise<DiscoverResponse> {
    return request<DiscoverResponse>(`/jobs/discover`, {
      method: "POST",
      body: {
        seed: body.seed,
        depth: body.depth ?? 2,
        max_accounts: body.max_accounts ?? 200,
        platform: body.platform ?? "twitter",
      },
    });
  },

  cancelJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/cancel`, { method: "POST" });
  },

  deleteJob(jobId: string): Promise<void> {
    return request<void>(`/jobs/${jobId}`, { method: "DELETE" });
  },

  // ── Accounts ─────────────────────────────────────────────────────────────
  listAccounts(
    opts: { q?: string; limit?: number; offset?: number } = {},
  ): Promise<AccountListResponse> {
    return request<AccountListResponse>(`/accounts`, {
      params: { q: opts.q, limit: opts.limit ?? 50, offset: opts.offset ?? 0 },
    });
  },

  getAccount(platform: string, handle: string): Promise<Account> {
    return request<Account>(
      `/accounts/${encodeURIComponent(platform)}/${encodeURIComponent(handle)}`,
    );
  },

  getHashtagAnalysis(
    opts: { limit?: number; min_shared?: number } = {},
  ): Promise<HashtagAnalysisResponse> {
    return request<HashtagAnalysisResponse>(`/graph/hashtags`, {
      params: { limit: opts.limit ?? 25, min_shared: opts.min_shared ?? 1 },
    });
  },

  getIntersection(
    seeds: string[],
    opts: { depth?: number; limit?: number; platform?: string } = {},
  ): Promise<IntersectionResponse> {
    return request<IntersectionResponse>(`/graph/intersection`, {
      params: {
        seeds,
        depth: opts.depth ?? 2,
        limit: opts.limit ?? 200,
        platform: opts.platform ?? "twitter",
      },
    });
  },

  getGeoLocations(
    opts: { maxNew?: number; limit?: number; seed?: string; depth?: number } = {},
  ): Promise<GeoLocationsResponse> {
    return request<GeoLocationsResponse>(`/geo/locations`, {
      params: {
        max_new: opts.maxNew ?? 8,
        limit: opts.limit ?? 5000,
        seed: opts.seed || undefined,
        depth: opts.depth ?? 2,
      },
    });
  },

  enumUsername(username: string): Promise<UsernameEnumResponse> {
    return request<UsernameEnumResponse>(`/enrich/username`, {
      params: { username },
    });
  },

  health(): Promise<{ status: string }> {
    return request<{ status: string }>(`/health`);
  },
};
