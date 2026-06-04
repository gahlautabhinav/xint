import { useQuery } from "@tanstack/react-query";
import {
  BadgeCheck,
  ExternalLink,
  Maximize2,
  Network,
  Crosshair,
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

  // Pull the full account record from the relational store (richer than graph props).
  const { data: account } = useQuery({
    queryKey: ["account", platform, bareHandle],
    queryFn: () => api.getAccount(platform, bareHandle),
    enabled: node.hasProfile,
    retry: false,
  });

  const displayName = account?.display_name || node.displayName || handle;
  const followers = account?.followers_count ?? node.followers;
  const following = account?.following_count;
  const bio = account?.bio;
  const website = account?.website;
  const verified = account?.is_verified ?? node.verified;

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
        <div>
          <dt className="eyebrow eyebrow--sm">Depth</dt>
          <dd className="tabular">{node.depth >= 99 ? "—" : node.depth}</dd>
        </div>
      </dl>

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
