import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AtSign, BadgeCheck, ExternalLink, MapPin, Network, Phone, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Account } from "@/lib/types";
import { formatFull, formatDate } from "@/lib/format";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { Pill } from "@/components/Pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import "./accounts.css";

function AccountDetail({ account, onClose }: { account: Account; onClose: () => void }) {
  return (
    <aside className="acct-detail reveal" aria-label={`Details for @${account.username}`}>
      <div className="row row--between">
        <span className="eyebrow eyebrow--sm">{account.platform}</span>
        <button className="iconbtn" onClick={onClose} aria-label="Close" type="button">
          <X size={16} />
        </button>
      </div>

      <div className="acct-detail__id">
        <span className="display-sm">{account.display_name || `@${account.username}`}</span>
        <span className="mono text-mute">@{account.username}</span>
        {account.is_verified && (
          <span className="inspector__verified">
            <BadgeCheck size={16} /> verified
          </span>
        )}
      </div>

      {account.bio && <p className="acct-detail__bio">{account.bio}</p>}

      <dl className="acct-detail__stats">
        <div>
          <dt className="eyebrow eyebrow--sm">Followers</dt>
          <dd className="tabular">{formatFull(account.followers_count)}</dd>
        </div>
        <div>
          <dt className="eyebrow eyebrow--sm">Following</dt>
          <dd className="tabular">{formatFull(account.following_count)}</dd>
        </div>
        {account.tweet_count > 0 && (
          <div>
            <dt className="eyebrow eyebrow--sm">Tweets</dt>
            <dd className="tabular">{formatFull(account.tweet_count)}</dd>
          </div>
        )}
        <div>
          <dt className="eyebrow eyebrow--sm">Depth</dt>
          <dd className="tabular">{account.scrape_depth}</dd>
        </div>
        {account.join_date && (
          <div>
            <dt className="eyebrow eyebrow--sm">Joined</dt>
            <dd className="mono">{account.join_date}</dd>
          </div>
        )}
        {account.timezone_utc_offset != null && (
          <div>
            <dt className="eyebrow eyebrow--sm">Est. timezone</dt>
            <dd className="mono">
              UTC{account.timezone_utc_offset >= 0 ? "+" : ""}{account.timezone_utc_offset}
            </dd>
          </div>
        )}
      </dl>

      {account.location && (
        <span className="inspector__meta">
          <MapPin size={12} aria-hidden /> {account.location}
        </span>
      )}

      {account.website && (
        <a
          className="inspector__link"
          href={account.website.startsWith("http") ? account.website : `https://${account.website}`}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={14} />
          <span className="grow">{account.website}</span>
        </a>
      )}

      {account.emails.length > 0 && (
        <div className="inspector__contacts">
          {account.emails.map((e) => (
            <span key={e} className="inspector__contact mono">
              <AtSign size={12} aria-hidden /> {e}
            </span>
          ))}
        </div>
      )}

      {account.phones.length > 0 && (
        <div className="inspector__contacts">
          {account.phones.map((p) => (
            <span key={p} className="inspector__contact mono">
              <Phone size={12} aria-hidden /> {p}
            </span>
          ))}
        </div>
      )}

      <span className="inspector__meta mono">scraped {formatDate(account.scraped_at)}</span>

      <div className="acct-detail__actions">
        <Link to={`/?q=${account.username}`}>
          <Pill variant="primary" size="sm" icon={<Network size={14} />}>
            View in graph
          </Pill>
        </Link>
        <a
          className="pill pill--sm"
          href={`https://x.com/${account.username}`}
          target="_blank"
          rel="noreferrer"
        >
          Open on X&nbsp;↗
        </a>
      </div>
    </aside>
  );
}

export function AccountsPage() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Account | null>(null);
  const debounced = useDebouncedValue(search.trim(), 300);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["accounts", debounced],
    queryFn: () => api.listAccounts({ q: debounced || undefined, limit: 100 }),
  });

  const accounts = data?.items ?? [];

  return (
    <div className="page page--wide accounts">
      <header className="page__head reveal reveal-1">
        <span className="eyebrow">SCRAPED&nbsp;ACCOUNTS</span>
        <h1 className="page__title">Accounts</h1>
        <p className="page__lead">
          Every profile captured across all crawls.{" "}
          {data ? (
            <span className="mono">
              <span className="tabular text-ink">{formatFull(data.total)}</span> total
            </span>
          ) : null}
        </p>
      </header>

      <div className="searchbar accounts__search reveal reveal-2">
        <span className="searchbar__icon">
          <Search size={18} />
        </span>
        <input
          className="searchbar__input"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search username or bio…"
          aria-label="Search accounts"
          autoComplete="off"
          spellCheck={false}
        />
      </div>

      <div className="accounts__split reveal reveal-3">
        <div className="accounts__list-wrap card card--flush">
          {isLoading ? (
            <LoadingState title="Loading accounts…" />
          ) : isError ? (
            <ErrorState
              title="Couldn't load accounts"
              body={(error as Error)?.message}
              action={<Pill onClick={() => refetch()}>Retry</Pill>}
            />
          ) : accounts.length === 0 ? (
            <EmptyState
              title={debounced ? "No matches" : "No accounts yet"}
              body={
                debounced
                  ? `Nothing matches “${debounced}”.`
                  : "Run a crawl under Jobs to populate accounts."
              }
            />
          ) : (
            <table className="accounts-table">
              <thead>
                <tr>
                  <th>Handle</th>
                  <th>Platform</th>
                  <th className="num">Followers</th>
                  <th className="num">Following</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr
                    key={a.id}
                    className={`accounts-row${selected?.id === a.id ? " accounts-row--active" : ""}`}
                    onClick={() => setSelected(a)}
                    tabIndex={0}
                    role="button"
                    aria-pressed={selected?.id === a.id}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelected(a);
                      }
                    }}
                  >
                    <td>
                      <span className="accounts-row__handle">
                        @{a.username}
                        {a.is_verified && (
                          <BadgeCheck size={13} className="accounts-row__check" aria-label="verified" />
                        )}
                      </span>
                      {a.display_name && (
                        <span className="accounts-row__name">{a.display_name}</span>
                      )}
                    </td>
                    <td className="mono">{a.platform}</td>
                    <td className="num tabular">{formatFull(a.followers_count)}</td>
                    <td className="num tabular">{formatFull(a.following_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {selected && <AccountDetail account={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}
