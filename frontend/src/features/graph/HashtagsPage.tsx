import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Hash, Network } from "lucide-react";
import { api } from "@/lib/api";
import { Pill } from "@/components/Pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import "./hashtags.css";

const MIN_SHARED_OPTIONS = [1, 2, 3, 5];

export function HashtagsPage() {
  const [minShared, setMinShared] = useState(1);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["hashtags", minShared],
    queryFn: () => api.getHashtagAnalysis({ limit: 50, min_shared: minShared }),
  });

  const topTags = data?.top_hashtags ?? [];
  const pairs = data?.pairs ?? [];
  const accountCount = data?.account_count ?? 0;
  const maxCount = topTags[0]?.count ?? 1;

  return (
    <div className="page page--wide hashtags">
      <header className="page__head reveal reveal-1">
        <span className="eyebrow">OSINT&nbsp;//&nbsp;INTEREST&nbsp;GRAPH</span>
        <h1 className="page__title">Hashtag Analysis</h1>
        <p className="page__lead">
          Ranked hashtags across all scraped accounts, and account pairs sharing
          common tags — a proxy for shared interests and community overlap.
          {data ? (
            <span className="mono">
              {" "}
              <span className="tabular text-ink">{accountCount}</span> accounts
              analysed.
            </span>
          ) : null}
        </p>
      </header>

      <div className="hashtags__controls reveal reveal-2">
        <span className="eyebrow eyebrow--sm">Min shared tags to show a pair</span>
        <div className="hashtags__chips">
          {MIN_SHARED_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              className={`hashtags__chip${minShared === n ? " hashtags__chip--active" : ""}`}
              onClick={() => setMinShared(n)}
            >
              {n}+
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <LoadingState title="Analysing hashtags…" />
      ) : isError ? (
        <ErrorState
          title="Couldn't load hashtag data"
          body={(error as Error)?.message}
          action={<Pill onClick={() => refetch()}>Retry</Pill>}
        />
      ) : topTags.length === 0 ? (
        <EmptyState
          title="No hashtag data yet"
          body="Run a crawl under Jobs — hashtags are extracted automatically from scraped tweets."
          action={
            <Link to="/jobs">
              <Pill variant="primary" icon={<Network size={14} />}>
                Go to Jobs
              </Pill>
            </Link>
          }
        />
      ) : (
        <div className="hashtags__body reveal reveal-3">
          {/* ── Left: Top hashtags ─────────────────────────────────────── */}
          <section className="hashtags__section card">
            <h2 className="hashtags__section-title eyebrow">
              Top hashtags
            </h2>
            <div className="hashtags__bars">
              {topTags.map((item) => (
                <div key={item.tag} className="hashtags__bar-row">
                  <span className="hashtags__bar-label mono">
                    <Hash size={11} aria-hidden />
                    {item.tag}
                  </span>
                  <div className="hashtags__bar-track">
                    <div
                      className="hashtags__bar-fill"
                      style={{ width: `${Math.max(2, (item.count / maxCount) * 100)}%` }}
                    />
                  </div>
                  <span className="hashtags__bar-count tabular mono">
                    {item.count}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* ── Right: Account pairs ────────────────────────────────────── */}
          <section className="hashtags__section card">
            <h2 className="hashtags__section-title eyebrow">
              Account overlap
              {pairs.length > 0 && (
                <span className="hashtags__count-badge">{pairs.length}</span>
              )}
            </h2>

            {pairs.length === 0 ? (
              <p className="hashtags__empty-pairs mono">
                No pairs share {minShared}+ hashtag{minShared > 1 ? "s" : ""}.
                Try a lower min-shared threshold.
              </p>
            ) : (
              <div className="hashtags__pairs">
                {pairs.map((p) => (
                  <div key={`${p.source}:${p.target}`} className="hashtags__pair">
                    <div className="hashtags__pair-accounts">
                      <Link
                        to={`/?q=${p.source}`}
                        className="hashtags__pair-handle mono"
                        title={`Open @${p.source} in graph`}
                      >
                        @{p.source}
                      </Link>
                      <span className="hashtags__pair-sep">↔</span>
                      <Link
                        to={`/?q=${p.target}`}
                        className="hashtags__pair-handle mono"
                        title={`Open @${p.target} in graph`}
                      >
                        @{p.target}
                      </Link>
                    </div>
                    <div className="hashtags__pair-tags">
                      {p.shared.map((tag) => (
                        <span key={tag} className="hashtags__tag mono">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
