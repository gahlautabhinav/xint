import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, Network } from "lucide-react";
import { api } from "@/lib/api";
import type { JobEvent } from "@/lib/types";
import { formatDate, formatTime, relativeTime } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Pill } from "@/components/Pill";
import { ErrorState, LoadingState } from "@/components/states";

const ACTIVE = new Set(["RUNNING", "PENDING"]);

function eventSummary(e: JobEvent): string {
  const p = e.payload ?? {};
  if (typeof p.username === "string") return `@${p.username}`;
  if (typeof p.handle === "string") return `@${p.handle}`;
  if (typeof p.count === "number") return String(p.count);
  if (typeof p.message === "string") return p.message;
  const keys = Object.keys(p);
  return keys.length ? JSON.stringify(p) : "";
}

export function JobDetail({ jobId }: { jobId: string }) {
  const jobQuery = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => api.getJob(jobId),
    refetchInterval: (q) =>
      q.state.data && ACTIVE.has(q.state.data.status) ? 2500 : false,
    retry: false,
  });

  const active = jobQuery.data ? ACTIVE.has(jobQuery.data.status) : false;

  const eventsQuery = useQuery({
    queryKey: ["jobs", jobId, "events"],
    queryFn: () => api.getJobEvents(jobId, 0),
    enabled: !!jobQuery.data,
    // `active` derives from the *job* query (a different query), so the
    // self-referential `(q) => …` form can't see job status here. The closure
    // captures the latest `active` each render and TanStack re-reads it after
    // every fetch, so polling stops cleanly once the job leaves an active state.
    refetchInterval: () => (active ? 2500 : false),
  });

  if (jobQuery.isLoading) return <LoadingState title="Loading job…" />;
  if (jobQuery.isError || !jobQuery.data) {
    return (
      <ErrorState
        title="Job not found"
        body={(jobQuery.error as Error)?.message}
        action={
          <Link to="/jobs">
            <Pill icon={<ArrowLeft size={14} />}>All jobs</Pill>
          </Link>
        }
      />
    );
  }

  const job = jobQuery.data;
  const events = [...(eventsQuery.data?.events ?? [])].sort(
    (a, b) => b.sequence - a.sequence,
  );
  const pct =
    job.max_accounts > 0
      ? Math.min(100, Math.round((job.accounts_scraped / job.max_accounts) * 100))
      : 0;

  return (
    <div className="jobdetail">
      <div className="row row--between">
        <Link to="/jobs" className="backlink mono">
          <ArrowLeft size={15} /> All jobs
        </Link>
        <Link to={`/?q=${job.seed_username}`}>
          <Pill size="sm" icon={<Network size={14} />}>
            View in explorer
          </Pill>
        </Link>
      </div>

      <div className="card jobdetail__summary">
        <div className="jobdetail__title-row">
          <div>
            <span className="eyebrow eyebrow--sm">SEED</span>
            <h2 className="display-sm">@{job.seed_username}</h2>
          </div>
          <StatusBadge status={job.status} />
        </div>

        <div className="jobdetail__progress">
          <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div
              className={`progress__bar${active ? " progress__bar--active" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="mono jobdetail__progress-label">
            <span className="tabular">{job.accounts_scraped}</span> /{" "}
            {job.max_accounts} accounts · {pct}%
          </span>
        </div>

        <dl className="jobdetail__meta">
          <div>
            <dt className="eyebrow eyebrow--sm">Depth</dt>
            <dd className="tabular">{job.max_depth}</dd>
          </div>
          <div>
            <dt className="eyebrow eyebrow--sm">Platform</dt>
            <dd>{job.platform}</dd>
          </div>
          <div>
            <dt className="eyebrow eyebrow--sm">Started</dt>
            <dd>{formatDate(job.started_at ?? job.created_at)}</dd>
          </div>
          <div>
            <dt className="eyebrow eyebrow--sm">Finished</dt>
            <dd>{job.completed_at ? formatDate(job.completed_at) : "—"}</dd>
          </div>
        </dl>

        {job.error_message && (
          <p className="field__error" role="alert">
            {job.error_message}
          </p>
        )}
      </div>

      <section className="jobdetail__events">
        <div className="row row--between">
          <span className="eyebrow">
            EVENT&nbsp;LOG{" "}
            {active && <span className="badge badge--running"><span className="badge__dot" />LIVE</span>}
          </span>
          <span className="mono text-mute" style={{ fontSize: 12 }}>
            {events.length} events
          </span>
        </div>

        {events.length === 0 ? (
          <p className="text-mute" style={{ padding: "var(--s-lg) 0" }}>
            No events yet{active ? " — waiting for the crawler…" : "."}
          </p>
        ) : (
          <ol className="timeline">
            {events.map((e) => (
              <li className="timeline__item" key={e.id}>
                <span className="timeline__dot" aria-hidden />
                <div className="timeline__body">
                  <div className="timeline__head">
                    <span className="timeline__type mono">{e.event_type}</span>
                    <time className="timeline__time mono" dateTime={e.created_at} title={formatDate(e.created_at)}>
                      {formatTime(e.created_at)} · {relativeTime(e.created_at)}
                    </time>
                  </div>
                  {eventSummary(e) && (
                    <span className="timeline__summary">{eventSummary(e)}</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
