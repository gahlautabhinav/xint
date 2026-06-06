import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AtSign,
  BadgeCheck,
  ExternalLink,
  Globe,
  Loader2,
  MapPin,
  Maximize2,
  Network,
  Crosshair,
  Phone,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { parseNodeId } from "@/lib/nodeId";
import { formatFull, formatDate } from "@/lib/format";
import { Pill } from "@/components/Pill";
import type { NodeDatum } from "./transform";

interface NodeInspectorProps {
  node: NodeDatum;
  onClose: () => void;
  onExpand: (id: string) => void;
  onFocus: (id: string) => void;
  expanding: boolean;
}

export function NodeInspector({
  node,
  onClose,
  onExpand,
  onFocus,
  expanding,
}: NodeInspectorProps) {
  const { platform, bareHandle, handle } = parseNodeId(node.id);
  const [enumStarted, setEnumStarted] = useState(false);

  // Pull the full account record from the relational store (richer than graph props).
  const { data: account } = useQuery({
    queryKey: ["account", platform, bareHandle],
    queryFn: () => api.getAccount(platform, bareHandle),
    enabled: node.hasProfile,
    retry: false,
  });

  // Cross-platform username enumeration (Sherlock-style) — lazy, on click.
  const enumQuery = useQuery({
    queryKey: ["enum-username", bareHandle],
    queryFn: () => api.enumUsername(bareHandle),
    enabled: enumStarted,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const foundSites = (enumQuery.data?.results ?? []).filter((r) => r.status === "found");
  const unknownCount = (enumQuery.data?.results ?? []).filter(
    (r) => r.status === "unknown",
  ).length;

  const displayName = account?.display_name || node.displayName || handle;
  const followers = account?.followers_count ?? node.followers;
  const following = account?.following_count;
  const bio = account?.bio;
  const website = account?.website;
  const verified = account?.is_verified ?? node.verified;
  const location = account?.location;
  const joinDate = account?.join_date;
  const tzOffset = account?.timezone_utc_offset;
  const emails = account?.emails ?? [];
  const phones = account?.phones ?? [];
  const tweetCount = account?.tweet_count;

  return (
    <aside className="inspector reveal" aria-label={`Details for ${handle}`}>
      <div className="inspector__head">
        <span className="eyebrow eyebrow--sm">{platform}</span>
        <button
          className="iconbtn"
          onClick={onClose}
          aria-label="Close inspector"
          type="button"
        >
          <X size={16} />
        </button>
      </div>

      <div className="inspector__id">
        <span className="inspector__name display-sm">{displayName}</span>
        <span className="inspector__handle mono">{handle}</span>
        {verified && (
          <span className="inspector__verified" title="Verified">
            <BadgeCheck size={16} /> verified
          </span>
        )}
        {node.isRoot && <span className="badge badge--running">SEED</span>}
      </div>

      {bio && <p className="inspector__bio">{bio}</p>}

      <dl className="inspector__stats">
        <div>
          <dt className="eyebrow eyebrow--sm">Followers</dt>
          <dd className="tabular">{formatFull(followers)}</dd>
        </div>
        {following !== undefined && (
          <div>
            <dt className="eyebrow eyebrow--sm">Following</dt>
            <dd className="tabular">{formatFull(following)}</dd>
          </div>
        )}
        {tweetCount != null && tweetCount > 0 && (
          <div>
            <dt className="eyebrow eyebrow--sm">Tweets</dt>
            <dd className="tabular">{formatFull(tweetCount)}</dd>
          </div>
        )}
        <div>
          <dt className="eyebrow eyebrow--sm">Depth</dt>
          <dd className="tabular">{node.depth >= 99 ? "—" : node.depth}</dd>
        </div>
        {joinDate && (
          <div>
            <dt className="eyebrow eyebrow--sm">Joined</dt>
            <dd className="mono">{joinDate}</dd>
          </div>
        )}
        {tzOffset != null && (
          <div>
            <dt className="eyebrow eyebrow--sm">Est. timezone</dt>
            <dd className="mono">
              UTC{tzOffset >= 0 ? "+" : ""}{tzOffset}
            </dd>
          </div>
        )}
      </dl>

      {location && (
        <span className="inspector__meta">
          <MapPin size={12} aria-hidden /> {location}
        </span>
      )}

      {emails.length > 0 && (
        <div className="inspector__contacts">
          {emails.map((e) => (
            <span key={e} className="inspector__contact mono">
              <AtSign size={12} aria-hidden /> {e}
            </span>
          ))}
        </div>
      )}

      {phones.length > 0 && (
        <div className="inspector__contacts">
          {phones.map((p) => (
            <span key={p} className="inspector__contact mono">
              <Phone size={12} aria-hidden /> {p}
            </span>
          ))}
        </div>
      )}

      {website && (
        <a
          className="inspector__link"
          href={website.startsWith("http") ? website : `https://${website}`}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={14} />
          <span className="grow">{website}</span>
        </a>
      )}

      {account?.scraped_at && (
        <span className="inspector__meta mono">
          scraped {formatDate(account.scraped_at)}
        </span>
      )}

      {!node.hasProfile && (
        <p className="inspector__stub">
          Not yet scraped — discovered via a relationship. Run a crawl seeded on
          this handle to fetch its profile.
        </p>
      )}

      {/* Cross-platform username enumeration */}
      <div className="inspector__enum">
        <div className="inspector__enum-head">
          <span className="eyebrow eyebrow--sm">Same handle elsewhere</span>
          {enumQuery.data && (
            <span className="inspector__enum-stat mono">
              {enumQuery.data.found}/{enumQuery.data.checked}
            </span>
          )}
        </div>

        {!enumStarted ? (
          <Pill
            size="sm"
            icon={<Globe size={14} />}
            onClick={() => setEnumStarted(true)}
            title="Check ~30 sites for this username (public profile URLs)"
          >
            Find accounts
          </Pill>
        ) : enumQuery.isLoading ? (
          <span className="inspector__enum-loading mono">
            <Loader2 size={13} className="spin" /> checking ~30 sites…
          </span>
        ) : enumQuery.isError ? (
          <span className="inspector__enum-empty mono">
            Lookup failed.{" "}
            <button
              type="button"
              className="ulink"
              onClick={() => enumQuery.refetch()}
            >
              Retry
            </button>
          </span>
        ) : foundSites.length > 0 ? (
          <>
            <div className="inspector__enum-grid">
              {foundSites.map((s) => (
                <a
                  key={s.name}
                  className="inspector__enum-hit mono"
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  title={`${s.name} · ${s.category}`}
                >
                  <span className="inspector__enum-name">{s.name}</span>
                  <ExternalLink size={11} />
                </a>
              ))}
            </div>
            <p className="inspector__enum-note mono">
              same username — may be different people.
              {unknownCount > 0 && ` ${unknownCount} site${unknownCount > 1 ? "s" : ""} inconclusive.`}
            </p>
          </>
        ) : (
          <span className="inspector__enum-empty mono">
            No matches on the checked sites.
            {unknownCount > 0 && ` (${unknownCount} inconclusive.)`}
          </span>
        )}
      </div>

      <div className="inspector__actions">
        <Pill
          variant="primary"
          size="sm"
          icon={<Network size={14} />}
          onClick={() => onExpand(node.id)}
          loading={expanding}
        >
          Expand
        </Pill>
        <Pill size="sm" icon={<Crosshair size={14} />} onClick={() => onFocus(node.id)}>
          Focus
        </Pill>
        <a
          className="pill pill--sm pill__icon"
          href={`https://x.com/${bareHandle}`}
          target="_blank"
          rel="noreferrer"
          aria-label="Open on X"
        >
          <Maximize2 size={14} /> X&nbsp;↗
        </a>
      </div>
    </aside>
  );
}
