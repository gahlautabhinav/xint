import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import cytoscape, { type Layouts } from "cytoscape";
import cola from "cytoscape-cola";
import { Network, Search, X } from "lucide-react";

import { api } from "@/lib/api";
import { Pill } from "@/components/Pill";
import { ErrorState, LoadingState } from "@/components/states";
import "./intersection.css";

const SEED_COLORS = ["#00c2ff", "#ff6b35", "#7ed321", "#bd10e0", "#f5a623", "#e74c3c"];

let colaRegistered = false;
if (!colaRegistered) {
  cytoscape.use(cola);
  colaRegistered = true;
}

function colaBounded(randomize: boolean, fit: boolean, animate: boolean) {
  return {
    name: "cola",
    animate,
    randomize,
    fit,
    padding: 48,
    maxSimulationTime: 2000,
    convergenceThreshold: 0.01,
    nodeSpacing: 18,
    edgeLength: 110,
    avoidOverlap: true,
    handleDisconnected: true,
    infinite: false,
  } as unknown as cytoscape.LayoutOptions;
}

function colaLive() {
  return {
    name: "cola",
    animate: true,
    fit: false,
    infinite: true,
    nodeSpacing: 18,
    edgeLength: 110,
    avoidOverlap: true,
    handleDisconnected: true,
  } as unknown as cytoscape.LayoutOptions;
}

export function IntersectionPage() {
  const [selectedSeeds, setSelectedSeeds] = useState<string[]>([]);
  const [querySeeds, setQuerySeeds] = useState<string[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const layoutRef = useRef<Layouts | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts-all-intersection"],
    queryFn: () => api.listAccounts({ limit: 500 }),
  });

  const intersectionQuery = useQuery({
    queryKey: ["intersection", ...querySeeds],
    queryFn: () => api.getIntersection(querySeeds),
    enabled: querySeeds.length >= 2,
    retry: false,
  });

  const addSeed = (handle: string) => {
    if (!selectedSeeds.includes(handle) && selectedSeeds.length < 6) {
      setSelectedSeeds((prev) => [...prev, handle]);
    }
    setSearchInput("");
  };

  const removeSeed = (handle: string) =>
    setSelectedSeeds((prev) => prev.filter((s) => s !== handle));

  const runAnalysis = () => {
    if (selectedSeeds.length >= 2) setQuerySeeds([...selectedSeeds]);
  };

  // Build cytoscape graph
  useEffect(() => {
    const data = intersectionQuery.data;
    if (!data || !containerRef.current) return;

    cyRef.current?.destroy();
    cyRef.current = null;

    const seedColorMap: Record<string, string> = {};
    data.seeds.forEach((s, i) => {
      seedColorMap[s.toLowerCase()] = SEED_COLORS[i % SEED_COLORS.length];
    });

    const elements: cytoscape.ElementDefinition[] = [];

    for (const node of data.combined_nodes) {
      const handle = ((node.node_id as string).split(":")[1] ?? node.node_id).replace(/^@/, "");
      const isSeed = Boolean(node.props?.is_seed);
      const membership = (node.props?.membership as string[]) ?? [];
      const isAll = !isSeed && membership.length === data.seeds.length;

      let color = "#7d8187";
      if (isSeed) {
        color = seedColorMap[handle.toLowerCase()] ?? SEED_COLORS[0];
      } else if (isAll) {
        color = "#ffd700";
      } else if (membership.length > 0) {
        color = seedColorMap[membership[0].toLowerCase()] ?? "#7d8187";
      }

      elements.push({
        group: "nodes",
        data: {
          id: node.node_id as string,
          label: `@${handle}`,
          isSeed,
          isCommon: !isSeed && membership.length >= 2,
          isAll,
          color,
        },
      });
    }

    for (const edge of data.combined_edges) {
      elements.push({
        group: "edges",
        data: {
          id: `${edge.src}__${edge.rel_type}__${edge.dst}`,
          source: edge.src,
          target: edge.dst,
        },
      });
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      minZoom: 0.15,
      maxZoom: 3,
      wheelSensitivity: 0.25,
      boxSelectionEnabled: false,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            "font-family": "Geist Mono, monospace",
            "font-size": 11,
            color: "#e8eaed",
            "text-valign": "bottom",
            "text-margin-y": 4,
            "text-outline-width": 2,
            "text-outline-color": "#0d0f12",
            width: 26,
            height: 26,
            "border-width": 0,
          },
        },
        {
          selector: "node[?isSeed]",
          style: {
            width: 46,
            height: 46,
            "border-width": 3,
            "border-color": "data(color)",
            "border-opacity": 0.9,
            "font-size": 13,
          },
        },
        {
          selector: "node[?isAll]",
          style: {
            "border-width": 3,
            "border-color": "#ffd700",
            "border-opacity": 1,
          },
        },
        {
          selector: "node[?isCommon]",
          style: {
            "border-width": 1,
            "border-color": "rgba(255,255,255,0.4)",
            "border-opacity": 1,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "rgba(255,255,255,0.1)",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "rgba(255,255,255,0.14)",
            "curve-style": "bezier",
            "arrow-scale": 0.6,
          },
        },
        {
          selector: ".ix-dimmed",
          style: { opacity: 0.12 },
        },
        {
          selector: ".ix-hl-edge",
          style: {
            "line-color": "rgba(255,255,255,0.55)",
            "target-arrow-color": "rgba(255,255,255,0.55)",
            width: 2,
          },
        },
      ],
    });

    const runLayout = (opts: cytoscape.LayoutOptions) => {
      layoutRef.current?.stop();
      layoutRef.current = null;
      const l = cy.layout(opts);
      layoutRef.current = l;
      l.run();
    };

    cy.add(elements);

    cy.on("grab", "node", () => runLayout(colaLive()));
    cy.on("free", "node", () => runLayout(colaBounded(false, false, true)));

    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      const nbhd = node.closedNeighborhood();
      cy.elements().not(nbhd).addClass("ix-dimmed");
      node.connectedEdges().addClass("ix-hl-edge");
      const el = cy.container();
      if (el) el.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("ix-dimmed ix-hl-edge");
      const el = cy.container();
      if (el) el.style.cursor = "default";
    });

    cy.on("tap", "node", (evt) => {
      const handle = ((evt.target.id() as string).split(":")[1] ?? "").replace(/^@/, "");
      if (handle) window.open(`/?q=${handle}`, "_blank");
    });

    runLayout(colaBounded(true, true, true));

    cyRef.current = cy;
  }, [intersectionQuery.data]);

  useEffect(() => {
    return () => {
      layoutRef.current?.stop();
      layoutRef.current = null;
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, []);

  const filteredAccounts =
    accountsQuery.data?.items
      .filter(
        (a) =>
          a.username.toLowerCase().includes(searchInput.toLowerCase()) &&
          !selectedSeeds.includes(a.username),
      )
      .slice(0, 8) ?? [];

  const data = intersectionQuery.data;

  return (
    <div className="ix-page">
      {/* Left panel */}
      <div className="ix-panel">
        <div className="ix-panel__header">
          <span className="eyebrow">NETWORK INTERSECTION</span>
          <p className="body-sm text-mute ix-panel__lead">
            Select 2–6 crawled accounts to find common nodes, shared followings,
            and Jaccard similarity.
          </p>
        </div>

        {/* Seed chips */}
        <div className="ix-seeds">
          <span className="eyebrow eyebrow--sm">
            Seeds ({selectedSeeds.length}/6)
          </span>
          {selectedSeeds.length > 0 && (
            <div className="ix-seeds__chips">
              {selectedSeeds.map((s, i) => (
                <span
                  key={s}
                  className="ix-chip"
                  style={
                    { "--chip-color": SEED_COLORS[i % SEED_COLORS.length] } as React.CSSProperties
                  }
                >
                  <span
                    className="ix-chip__dot"
                    style={{ background: SEED_COLORS[i % SEED_COLORS.length] }}
                  />
                  @{s}
                  <button
                    className="ix-chip__remove"
                    onClick={() => removeSeed(s)}
                    aria-label={`Remove ${s}`}
                    type="button"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Add seed search */}
          {selectedSeeds.length < 6 && (
            <div className="ix-search">
              <div className="searchbar">
                <span className="searchbar__icon">
                  <Search size={14} />
                </span>
                <input
                  className="searchbar__input"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Type handle + Enter to add…"
                  autoComplete="off"
                  spellCheck={false}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const handle = searchInput.replace(/^@/, "").trim().toLowerCase();
                      if (handle) addSeed(handle);
                    }
                  }}
                />
              </div>
              {searchInput && filteredAccounts.length > 0 && (
                <div className="ix-search__dropdown">
                  {filteredAccounts.map((a) => (
                    <button
                      key={a.username}
                      className="ix-search__item mono"
                      onClick={() => addSeed(a.username)}
                      type="button"
                    >
                      @{a.username}
                      {a.display_name && (
                        <span className="ix-search__name text-mute">
                          {a.display_name}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <Pill
            size="sm"
            icon={<Network size={14} />}
            onClick={runAnalysis}
            disabled={selectedSeeds.length < 2}
          >
            Analyze
          </Pill>
        </div>

        {/* Pairwise similarity */}
        {data && data.pairwise.length > 0 && (
          <div className="ix-section">
            <span className="eyebrow eyebrow--sm">Pairwise Similarity</span>
            <table className="ix-table">
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Jaccard</th>
                  <th>Common</th>
                  <th>Shared follows</th>
                </tr>
              </thead>
              <tbody>
                {data.pairwise.map((p) => (
                  <tr key={`${p.seed_a}-${p.seed_b}`}>
                    <td className="mono">
                      @{p.seed_a} / @{p.seed_b}
                    </td>
                    <td className="mono">
                      {(p.jaccard * 100).toFixed(1)}%
                    </td>
                    <td className="mono">{p.common_count}</td>
                    <td className="mono">{p.common_followings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Common nodes */}
        {data && data.common_nodes.length > 0 && (
          <div className="ix-section">
            <span className="eyebrow eyebrow--sm">
              Common Nodes ({data.common_nodes.length})
            </span>
            <div className="ix-common">
              {data.common_nodes.slice(0, 60).map((n) => (
                <div key={n.node_id} className="ix-common__row">
                  <a
                    className="mono ix-common__handle"
                    href={`/?q=${n.handle}`}
                    title={`Open @${n.handle} in graph`}
                  >
                    @{n.handle}
                  </a>
                  <div className="ix-common__badges">
                    {n.in_seeds.map((s) => {
                      const idx = data.seeds.indexOf(s);
                      return (
                        <span
                          key={s}
                          className="ix-badge"
                          style={{
                            background:
                              SEED_COLORS[idx >= 0 ? idx : 0],
                          }}
                          title={`In @${s}'s network`}
                        >
                          {s[0].toUpperCase()}
                        </span>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {data && data.common_nodes.length === 0 && querySeeds.length >= 2 && !intersectionQuery.isLoading && (
          <p className="body-sm text-mute" style={{ marginTop: 8 }}>
            No common nodes found between these networks.
          </p>
        )}
      </div>

      {/* Right: graph canvas */}
      <div className="ix-canvas-wrap">
        {intersectionQuery.isLoading && (
          <div className="ix-canvas-overlay">
            <LoadingState title="Computing intersection…" />
          </div>
        )}
        {intersectionQuery.isError && (
          <div className="ix-canvas-overlay">
            <ErrorState
              title="Analysis failed"
              body={(intersectionQuery.error as Error)?.message}
              action={
                <Pill onClick={() => intersectionQuery.refetch()}>Retry</Pill>
              }
            />
          </div>
        )}
        {!querySeeds.length && !intersectionQuery.isLoading && (
          <div className="ix-canvas-overlay ix-canvas-overlay--idle">
            <Network size={44} className="ix-idle-icon" />
            <p className="body-sm text-mute" style={{ marginTop: 12 }}>
              Select ≥2 seeds and click Analyze
            </p>
          </div>
        )}

        {/* Legend */}
        {data && data.seeds.length > 0 && (
          <div className="ix-legend">
            {data.seeds.map((s, i) => (
              <span key={s} className="ix-legend__item">
                <span
                  className="ix-legend__dot"
                  style={{ background: SEED_COLORS[i % SEED_COLORS.length] }}
                />
                <span className="mono">@{s}</span>
              </span>
            ))}
            <span className="ix-legend__item">
              <span className="ix-legend__dot" style={{ background: "#ffd700" }} />
              <span className="mono text-mute">all seeds</span>
            </span>
          </div>
        )}

        <div ref={containerRef} className="ix-canvas" />
      </div>
    </div>
  );
}
