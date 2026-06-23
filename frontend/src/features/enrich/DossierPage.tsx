import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowLeft,
  AtSign,
  BadgeCheck,
  Camera,
  ExternalLink,
  Fingerprint,
  Globe,
  Loader2,
  MapPin,
  Network,
  Phone,
  ShieldAlert,
  UserSearch,
} from "lucide-react";

import { api } from "@/lib/api";
import type { BiasVerdict, PivotLink, Tweet } from "@/lib/types";
import { formatFull, formatDate } from "@/lib/format";
import { Pill } from "@/components/Pill";
import { ErrorState, LoadingState } from "@/components/states";
import "../bias/bias.css";
import "./dossier.css";

const BIAS_FLAG_LABELS: { key: keyof BiasVerdict; label: string }[] = [
  { key: "is_antisemitic",            label: "Antisemitic" },
  { key: "is_anti_jew",               label: "Anti-Jewish" },
  { key: "is_anti_israel",            label: "Anti-Israel" },
  { key: "is_anti_zionist",           label: "Anti-Zionist" },
  { key: "is_pro_islamist_extremist", label: "Pro-Islamist Extremism" },
  { key: "is_pro_hamas_hezbollah",    label: "Pro-Hamas/Hezbollah" },
  { key: "is_pro_palestine",          label: "Pro-Palestine" },
  { key: "is_white_supremacist",      label: "White Supremacist" },
  { key: "is_neo_nazi",               label: "Neo-Nazi" },
];

function bigAvatar(url: string | null | undefined): string | null {
  if (!url) return null;
  return url.replace("_normal.", "_400x400.");
}

const PIVOT_META: { key: string; label: string; icon: typeof Globe }[] = [
  { key: "identity", label: "Identity", icon: Globe },
  { key: "dork", label: "Web search", icon: Network },
  { key: "breach", label: "Breach / exposure", icon: ShieldAlert },
];

function LinkChips({ links }: { links: PivotLink[] }) {
  return (
    <div className="dossier__chips">
      {links.map((l) => (
        <a
          key={l.label}
          className="dossier__chip mono"
          href={l.url}
          target="_blank"
          rel="noreferrer"
          title={l.url}
        >
          <span>{l.label}</span>
          <ExternalLink size={11} />
        </a>
      ))}
    </div>
  );
}

function tweetKind(tw: Tweet): "reply" | "retweet" | "quote" | "post" {
  if (tw.reply_to) return "reply";
  if (tw.retweeted_from) return "retweet";
  if (tw.quote_url) return "quote";
  return "post";
}

const KIND_LABEL: Record<string, string> = {
  reply: "↩ reply",
  retweet: "↻ retweet",
  quote: "❝ quote",
  post: "post",
};

function TweetCard({ tw }: { tw: Tweet }) {
  const kind = tweetKind(tw);
  return (
    <div className={`dossier__tweet dossier__tweet--${kind}`}>
      <div className="dossier__tweet-meta mono">
        <span className={`dossier__tweet-kind dossier__tweet-kind--${kind}`}>
          {KIND_LABEL[kind]}
        </span>
        {tw.timestamp && (
          <span className="dossier__tweet-ts">
            {new Date(tw.timestamp).toLocaleString()}
          </span>
        )}
        {tw.tweet_url && (
          <a
            href={tw.tweet_url}
            target="_blank"
            rel="noreferrer"
            className="dossier__tweet-link mono"
            title="Open on X"
          >
            ↗
          </a>
        )}
      </div>
      <p className="dossier__tweet-text">{tw.text}</p>
      {tw.media_urls.length > 0 && (
        <div className="dossier__tweet-media">
          {tw.media_urls.map((url) => (
            <a key={url} href={url} target="_blank" rel="noreferrer">
              <img src={url} alt="tweet media" className="dossier__tweet-thumb" loading="lazy" />
            </a>
          ))}
        </div>
      )}
      {(tw.reply_to || tw.retweeted_from) && (
        <span className="dossier__tweet-ref mono">
          {tw.reply_to ? `→ @${tw.reply_to}` : `RT @${tw.retweeted_from}`}
        </span>
      )}
    </div>
  );
}

export function DossierPage() {
  const { platform = "twitter", handle = "" } = useParams();

  const accountQuery = useQuery({
    queryKey: ["account", platform, handle],
    queryFn: () => api.getAccount(platform, handle),
    retry: false,
  });

  const pivotsQuery = useQuery({
    queryKey: ["pivots", platform, handle],
    queryFn: () => api.getPivots(platform, handle),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const enumQuery = useQuery({
    queryKey: ["enum-username", handle],
    queryFn: () => api.enumUsername(handle),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const identityQuery = useQuery({
    queryKey: ["identity", handle],
    queryFn: () => api.resolveIdentity(handle),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const biasStatusQuery = useQuery({
    queryKey: ["bias-status"],
    queryFn: api.getBiasStatus,
    staleTime: 30_000,
  });

  const biasQuery = useQuery({
    queryKey: ["bias-flags", handle],
    queryFn: () => api.getBiasFlags(handle),
    retry: false,
    staleTime: 5 * 60_000,
    enabled: biasStatusQuery.data?.connected === true,
  });

  const [tweetOffset, setTweetOffset] = useState(0);
  const TWEET_PAGE = 25;
  const tweetsQuery = useQuery({
    queryKey: ["tweets", platform, handle, tweetOffset],
    queryFn: () => api.getTweets(platform, handle, { limit: TWEET_PAGE, offset: tweetOffset }),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const account = accountQuery.data;
  const identityHits = identityQuery.data?.hits ?? [];
  const links = pivotsQuery.data?.links ?? [];
  const reverseImage = links.filter((l) => l.group === "reverse_image");
  const foundSites = (enumQuery.data?.results ?? []).filter((r) => r.status === "found");
  const unknownCount = (enumQuery.data?.results ?? []).filter((r) => r.status === "unknown").length;
  const avatar = bigAvatar(account?.profile_image_url);

  return (
    <div className="page page--wide dossier">
      <header className="page__head reveal reveal-1">
        <Link to="/accounts" className="dossier__back mono">
          <ArrowLeft size={14} /> Accounts
        </Link>
        <span className="eyebrow">OSINT&nbsp;//&nbsp;DOSSIER</span>
        <h1 className="page__title">@{handle}</h1>
      </header>

      {accountQuery.isLoading ? (
        <LoadingState title="Loading dossier…" />
      ) : accountQuery.isError ? (
        <ErrorState
          title="Account not found"
          body={`@${handle} isn't in the database yet — crawl it first (Explorer → search → Discover All).`}
          action={
            <Link to="/accounts">
              <Pill>Back to accounts</Pill>
            </Link>
          }
        />
      ) : account ? (
        <>
        {/* ── Identity resolution (headline deanon) ── */}
        <section className="dossier__identity reveal reveal-2">
          <h2 className="dossier__section-title">
            <UserSearch size={14} /> Identity resolution
            <span className="dossier__id-sub mono">
              public APIs · only when the handle was reused
            </span>
          </h2>
          {identityQuery.isLoading ? (
            <span className="dossier__loading mono">
              <Loader2 size={13} className="spin" /> querying GitHub · GitLab · Keybase…
            </span>
          ) : identityHits.length === 0 ? (
            <p className="dossier__empty mono">
              No public identity match — @{handle} wasn't found on GitHub, GitLab
              or Keybase (or it carries no real-name data there).
            </p>
          ) : (
            <div className="dossier__id-hits">
              {identityHits.map((h) => (
                <div key={h.source} className="dossier__id-hit">
                  <div className="dossier__id-hit-head">
                    <span className="dossier__id-source mono">{h.source}</span>
                    {h.url && (
                      <a href={h.url} target="_blank" rel="noreferrer" className="dossier__id-link mono">
                        open <ExternalLink size={10} />
                      </a>
                    )}
                  </div>
                  {h.real_name ? (
                    <span className="dossier__id-name">{h.real_name}</span>
                  ) : (
                    <span className="dossier__id-name dossier__id-name--none">no name set</span>
                  )}
                  <div className="dossier__id-meta mono">
                    {[h.company, h.location, h.email].filter(Boolean).join(" · ")}
                  </div>
                  {h.linked_accounts.length > 0 && (
                    <div className="dossier__chips">
                      {h.linked_accounts.map((la, i) =>
                        la.url ? (
                          <a
                            key={`${la.service}-${i}`}
                            href={la.url}
                            target="_blank"
                            rel="noreferrer"
                            className="dossier__chip mono"
                          >
                            <span>{la.service}: {la.value}</span>
                            <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span key={`${la.service}-${i}`} className="dossier__chip mono">
                            {la.service}: {la.value}
                          </span>
                        ),
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="dossier__grid reveal reveal-3">
          {/* ── Profile card ── */}
          <section className="dossier__card dossier__profile">
            <div className="dossier__id">
              {avatar ? (
                <img className="dossier__avatar" src={avatar} alt="" loading="lazy" />
              ) : (
                <div className="dossier__avatar dossier__avatar--empty">
                  <AtSign size={22} />
                </div>
              )}
              <div className="dossier__id-text">
                <span className="display-sm">{account.display_name || `@${account.username}`}</span>
                <span className="mono text-mute">@{account.username}</span>
                {account.is_verified && (
                  <span className="inspector__verified">
                    <BadgeCheck size={15} /> verified
                  </span>
                )}
              </div>
            </div>

            {account.bio && <p className="dossier__bio">{account.bio}</p>}

            <dl className="dossier__stats">
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
                    UTC{account.timezone_utc_offset >= 0 ? "+" : ""}
                    {account.timezone_utc_offset}
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
            {account.emails.map((e) => (
              <span key={e} className="inspector__contact mono">
                <AtSign size={12} aria-hidden /> {e}
              </span>
            ))}
            {account.phones.map((p) => (
              <span key={p} className="inspector__contact mono">
                <Phone size={12} aria-hidden /> {p}
              </span>
            ))}

            <div className="dossier__actions">
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
            {account.scraped_at && (
              <span className="inspector__meta mono">scraped {formatDate(account.scraped_at)}</span>
            )}
          </section>

          {/* ── Reverse image ── */}
          <section className="dossier__card">
            <h2 className="dossier__section-title">
              <Camera size={14} /> Reverse image
            </h2>
            {avatar ? (
              <div className="dossier__reverse">
                <img className="dossier__reverse-img" src={avatar} alt="profile" loading="lazy" />
                <div className="dossier__chips">
                  {reverseImage.map((l) => (
                    <a
                      key={l.label}
                      className="dossier__chip mono"
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span>{l.label}</span>
                      <ExternalLink size={11} />
                    </a>
                  ))}
                </div>
              </div>
            ) : (
              <p className="dossier__empty mono">No profile photo on record.</p>
            )}
          </section>

          {/* ── Accounts elsewhere ── */}
          <section className="dossier__card">
            <h2 className="dossier__section-title">
              <Globe size={14} /> Same handle elsewhere
              {enumQuery.data && (
                <span className="dossier__count mono">
                  {enumQuery.data.found}/{enumQuery.data.checked}
                </span>
              )}
            </h2>
            {enumQuery.isLoading ? (
              <span className="dossier__loading mono">
                <Loader2 size={13} className="spin" /> checking ~28 sites…
              </span>
            ) : foundSites.length > 0 ? (
              <>
                <div className="dossier__chips">
                  {foundSites.map((s) => (
                    <a
                      key={s.name}
                      className="dossier__chip dossier__chip--hit mono"
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      title={`${s.name} · ${s.category}`}
                    >
                      <span>{s.name}</span>
                      <ExternalLink size={11} />
                    </a>
                  ))}
                </div>
                <p className="dossier__note mono">
                  same username — may be different people.
                  {unknownCount > 0 && ` ${unknownCount} inconclusive.`}
                </p>
              </>
            ) : (
              <p className="dossier__empty mono">
                No matches.{unknownCount > 0 && ` (${unknownCount} inconclusive.)`}
              </p>
            )}
          </section>

          {/* ── Pivots ── */}
          <section className="dossier__card">
            <h2 className="dossier__section-title">
              <Fingerprint size={14} /> Pivots
            </h2>
            {pivotsQuery.isLoading ? (
              <span className="dossier__loading mono">
                <Loader2 size={13} className="spin" /> building…
              </span>
            ) : (
              PIVOT_META.map(({ key, label, icon: Icon }) => {
                const group = links.filter((l) => l.group === key);
                if (group.length === 0) return null;
                return (
                  <div key={key} className="dossier__pivot-group">
                    <span className="dossier__pivot-label">
                      <Icon size={12} /> {label}
                    </span>
                    <LinkChips links={group} />
                  </div>
                );
              })
            )}
            <p className="dossier__note mono">
              Opens third-party search tools. Verify before concluding.
            </p>
          </section>

          {/* ── Bias analysis ── */}
          {biasStatusQuery.data?.connected && (
            <section className="dossier__card">
              <h2 className="dossier__section-title">
                <ShieldAlert size={14} /> Bias Analysis
                <span
                  className="bias-dot bias-dot--online"
                  aria-label="bias agent online"
                  title="xint-bias-agent connected"
                  style={{ marginLeft: 6 }}
                />
              </h2>
              {biasQuery.isLoading ? (
                <span className="dossier__loading mono">
                  <Loader2 size={13} className="spin" /> querying bias agent…
                </span>
              ) : !biasQuery.data?.analyzed ? (
                <p className="dossier__empty mono">
                  Not analyzed yet — will run after next crawl of @{handle}.
                </p>
              ) : biasQuery.data.verdict ? (
                <>
                  {(() => {
                    const activeFlags = BIAS_FLAG_LABELS.filter(
                      ({ key }) => biasQuery.data!.verdict![key] === true,
                    );
                    return activeFlags.length > 0 ? (
                      <div className="dossier__bias-flags">
                        {activeFlags.map(({ key, label }) => (
                          <span key={key} className="dossier__bias-flag">{label}</span>
                        ))}
                      </div>
                    ) : (
                      <p className="dossier__empty mono">No bias flags raised.</p>
                    );
                  })()}
                  <span className="dossier__bias-conf mono">
                    confidence: {Math.round((biasQuery.data.verdict.confidence) * 100)}%
                  </span>
                  {biasQuery.data.verdict.evidence && (
                    <p className="dossier__bias-evidence mono">
                      {biasQuery.data.verdict.evidence}
                    </p>
                  )}
                </>
              ) : null}
              <p className="dossier__note mono">
                AI-generated classification · verify independently.
              </p>
            </section>
          )}
        </div>

        {/* ── Posts & Replies ── */}
        <section className="dossier__card reveal">
          <h2 className="dossier__section-title">
            <AtSign size={14} /> Posts &amp; Replies
            {tweetsQuery.data && (
              <span className="dossier__id-sub mono">
                {tweetsQuery.data.total} scraped
              </span>
            )}
          </h2>
          {tweetsQuery.isLoading ? (
            <span className="dossier__loading mono">
              <Loader2 size={13} className="spin" /> loading tweets…
            </span>
          ) : tweetsQuery.isError ? (
            <p className="dossier__empty mono">Could not load tweets.</p>
          ) : (tweetsQuery.data?.items.length ?? 0) === 0 ? (
            <p className="dossier__empty mono">
              No tweets stored yet — rescrape this account to populate.
            </p>
          ) : (
            <>
              <div className="dossier__tweet-feed">
                {tweetsQuery.data!.items.map((tw) => (
                  <TweetCard key={tw.id} tw={tw} />
                ))}
              </div>
              {tweetsQuery.data!.total > TWEET_PAGE && (
                <div className="dossier__tweet-pager mono">
                  <button
                    className="dossier__tweet-nav"
                    disabled={tweetOffset === 0}
                    onClick={() => setTweetOffset((p) => Math.max(0, p - TWEET_PAGE))}
                  >
                    ← prev
                  </button>
                  <span>
                    {tweetOffset + 1}–{Math.min(tweetOffset + TWEET_PAGE, tweetsQuery.data!.total)}
                    {" "}/ {tweetsQuery.data!.total}
                  </span>
                  <button
                    className="dossier__tweet-nav"
                    disabled={tweetOffset + TWEET_PAGE >= tweetsQuery.data!.total}
                    onClick={() => setTweetOffset((p) => p + TWEET_PAGE)}
                  >
                    next →
                  </button>
                </div>
              )}
            </>
          )}
        </section>
        </>
      ) : null}
    </div>
  );
}
