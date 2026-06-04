import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { formatCount, relativeTime } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { NewCrawlForm } from "./NewCrawlForm";
import { JobDetail } from "./JobDetail";
import "./jobs.css";

const ACTIVE = new Set(["RUNNING", "PENDING"]);

function JobsList() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.listJobs({ limit: 50 }),
    refetchInterval: (q) =>
      q.state.data?.items.some((j: Job) => ACTIVE.has(j.status)) ? 3000 : false,
  });

  if (isLoading) return <LoadingState title="Loading jobs…" />;
  if (isError)
    return (
      <ErrorState
        title="Couldn't load jobs"
        body={(error as Error)?.message}
        action={<button className="pill" onClick={() => refetch()}>Retry</button>}
      />
    );

  const jobs = data?.items ?? [];
  if (jobs.length === 0)
    return (
      <EmptyState
        title="No crawls yet"
        body="Start your first crawl above to begin building the network graph."
      />
    );

  return (
    <div className="card card--flush jobs-table-wrap">
      <table className="jobs-table">
        <thead>
          <tr>
            <th>Seed</th>
            <th>Status</th>
            <th className="num">Scraped</th>
            <th className="num">Depth</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="jobs-row">
              <td>
                <Link to={`/jobs/${job.id}`} className="jobs-row__seed">
                  @{job.seed_username}
                </Link>
              </td>
              <td>
                <StatusBadge status={job.status} />
              </td>
              <td className="num tabular">
                {formatCount(job.accounts_scraped)} / {formatCount(job.max_accounts)}
              </td>
              <td className="num tabular">{job.max_depth}</td>
              <td className="mono jobs-row__time">
                {relativeTime(job.started_at ?? job.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function JobsPage() {
  const { jobId } = useParams();

  if (jobId) {
    return (
      <div className="page">
        <JobDetail jobId={jobId} />
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page__head reveal reveal-1">
        <span className="eyebrow">CRAWL&nbsp;CONTROL</span>
        <h1 className="page__title">Jobs</h1>
        <p className="page__lead">
          Launch and monitor network crawls. Running jobs stream live progress.
        </p>
      </header>

      <div className="reveal reveal-2">
        <NewCrawlForm />
      </div>

      <div className="reveal reveal-3">
        <JobsList />
      </div>
    </div>
  );
}
