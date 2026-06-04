import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Network, Square, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { JobEvent } from "@/lib/types";
import { formatDate, formatTime } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Pill } from "@/components/Pill";
import { ErrorState, LoadingState } from "@/components/states";

const ACTIVE = new Set(["RUNNING", "PENDING"]);

function eventUser(p: Record<string, unknown>): string {
  if (typeof p.username === "string") return `@${p.username}`;
  if (typeof p.handle === "string") return `@${p.handle}`;
  return "";
}

/** One-line, terminal-friendly summary of an event's payload. */
function eventSummary(e: JobEvent): string {
  const p = e.payload ?? {};
  const user = eventUser(p);
  switch (e.event_type) {
    case "account_scraped": {
      const bits: string[] = [];
      if (typeof p.following === "number") bits.push(`${p.following} following`);
      if (typeof p.followers_n === "number") bits.push(`${p.followers_n} followers`);
      if (typeof p.mentions === "number" && p.mentions) bits.push(`${p.mentions} mentions`);
      if (typeof p.new_edges === "number") bits.push(`${p.new_edges} edges`);
      return [user, ...bits].filter(Boolean).join(" · ");
    }
    case "account_failed":
      return `${user}${typeof p.error === "string" ? ` — ${p.error}` : ""}`;
    case "account_started":
      return user;
    case "job_started":
      return typeof p.seed === "string" ? `seed @${p.seed}` : "";
    case "job_finished":
      return `${p.status ?? ""} · ${p.accounts_scraped ?? 0} scraped`;
    default: {
      if (user) return user;
      if (typeof p.message === "string") return p.message;
      const keys = Object.keys(p);
      return keys.length ? JSON.stringify(p) : "";
    }
  }
}

const TONE: Record<string, string> = {
  account_scraped: "log__line--ok",
  account_failed: "log__line--err",
  job_finished: "log__line--done",
  job_started: "log__line--info",
  account_started: "log__line--info",
};

export function JobDetail({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const jobQuery = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => api.getJob(jobId),
    refetchInterval: (q) =>
      q.state.data && ACTIVE.has(q.state.data.status) ? 1500 : false,
    retry: false,
  });

  const active = jobQuery.data ? ACTIVE.has(jobQuery.data.status) : false;

  // Accumulated event log — the API returns only events newer than `since`,
  // so we append deltas client-side rather than re-reading the whole log.
  const [events, setEvents] = useState<JobEvent[]>([]);
  const lastSeqRef = useRef(0);

  useEffect(() => {
    setEvents([]);
    lastSeqRef.current = 0;
  }, [jobId]);

  const eventsQuery = useQuery({
    queryKey: ["jobs", jobId, "events"],
    queryFn: () => api.getJobEvents(jobId, lastSeqRef.current),
    enabled: !!jobQuery.data,
    // `active` derives from the job query; the closure captures the latest value
    // each render and TanStack re-reads it after every fetch, so polling stops
    // cleanly once the job leaves an active state.
    refetchInterval: () => (active ? 1500 : false),
    // The fetch depends on lastSeqRef (a cursor), which isn't in the queryKey.
    // Without these, a remount would replay the last cached *delta* instead of
    // re-fetching the full history from since=0. refetchInterval still calls
    // queryFn directly during polling, so live deltas are unaffected.
    staleTime: 0,
    gcTime: 0,
  });

  // Merge each delta into the accumulated log (dedupe by sequence).
  const delta = eventsQuery.data;
  useEffect(() => {
    if (!delta || delta.events.length === 0) return;
    setEvents((prev) => {
      const seen = new Set(prev.map((e) => e.sequence));
      const fresh = delta.events.filter((e) => !seen.has(e.sequence));
      return fresh.length ? [...prev, ...fresh] : prev;
    });
    if (delta.last_sequence > lastSeqRef.current) lastSeqRef.current = delta.last_sequence;
  }, [delta]);

  // When the job leaves the active state, do one final fetch so the trailing
  // events (last account_scraped + job_finished) aren't missed by polling.
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) eventsQuery.refetch();
    wasActive.current = active;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Auto-scroll the terminal feed to the newest line.
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const cancelMut = useMutation({
    mutationFn: () => api.cancelJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deleteJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
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
  const pct =
    job.max_accounts > 0
      ? Math.min(100, Math.round((job.accounts_scraped / job.max_accounts) * 100))
      : 0;

  // "Currently scraping @X" — the latest event is an account_started not yet
  // followed by its scraped/failed line.
  const last = events[events.length - 1];
  const scrapingNow =
    active && last?.event_type === "account_started" ? eventUser(last.payload ?? {}) : null;

  function onDelete() {
    if (window.confirm(`Delete the crawl for @${job.seed_username}? This removes its event log.`))
      deleteMut.mutate();
  }

  const mutError = cancelMut.error ?? deleteMut.error;

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
          <div className="jobdetail__actions">
            <StatusBadge status={job.status} />
            {active ? (
              <Pill
                size="sm"
                icon={<Square size={13} />}
                onClick={() => cancelMut.mutate()}
                loading={cancelMut.isPending}
                className="pill--danger"
              >
                Stop
              </Pill>
            ) : (
              <Pill
                size="sm"
                icon={<Trash2 size={13} />}
                onClick={onDelete}
                loading={deleteMut.isPending}
                className="pill--danger"
              >
                Delete
              </Pill>
            )}
          </div>
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
            {scrapingNow && <span className="jobdetail__nowscraping"> · scraping {scrapingNow}…</span>}
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
        {mutError && (
          <p className="field__error" role="alert">
            {mutError instanceof ApiError ? mutError.message : "Action failed."}
          </p>
        )}
      </div>

      <section className="jobdetail__events">
        <div className="row row--between">
          <span className="eyebrow">
            ACTIVITY&nbsp;LOG{" "}
            {active && <span className="badge badge--running"><span className="badge__dot" />LIVE</span>}
          </span>
          <span className="mono text-mute" style={{ fontSize: 12 }}>
            {events.length} events
          </span>
        </div>

        <div className="log" ref={logRef}>
          {events.length === 0 ? (
            <p className="log__empty">
              {active ? "Waiting for the crawler…" : "No events recorded."}
            </p>
          ) : (
            events.map((e) => (
              <div className={`log__line ${TONE[e.event_type] ?? ""}`} key={e.id}>
                <time className="log__time" dateTime={e.created_at} title={formatDate(e.created_at)}>
                  {formatTime(e.created_at)}
                </time>
                <span className="log__type">{e.event_type}</span>
                <span className="log__summary">{eventSummary(e)}</span>
              </div>
            ))
          )}
          {scrapingNow && (
            <div className="log__line log__line--cursor">
              <span className="log__cursor" aria-hidden>▌</span>
              <span className="log__summary">scraping {scrapingNow}…</span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
