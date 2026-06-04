import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Play } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { normalizeHandle } from "@/lib/nodeId";
import type { JobCreate } from "@/lib/types";
import { Pill } from "@/components/Pill";
import { SelectField, TextField } from "@/components/Field";

const ACCOUNT_PRESETS = [10, 25, 50, 100, 200, 500, 1000, 5000];

const RATE_OPTIONS = [
  { value: "conservative", label: "Conservative — slowest, safest" },
  { value: "moderate", label: "Moderate — balanced" },
  { value: "aggressive", label: "Aggressive — fastest, riskier" },
];

export function NewCrawlForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [seed, setSeed] = useState("");
  const [depth, setDepth] = useState(2);
  const [maxAccounts, setMaxAccounts] = useState(200);
  const [maxFollowing, setMaxFollowing] = useState(50);
  const [maxFollowers, setMaxFollowers] = useState(50);
  const [rate, setRate] = useState<JobCreate["rate_profile"]>("moderate");
  const [proxies, setProxies] = useState("");
  const [seedError, setSeedError] = useState<string | undefined>();

  const mutation = useMutation({
    mutationFn: (body: JobCreate) => api.createJob(body),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/jobs/${job.id}`);
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const handle = normalizeHandle(seed);
    if (!handle) {
      setSeedError("Enter a seed username.");
      return;
    }
    setSeedError(undefined);
    mutation.mutate({
      seed_username: handle,
      max_depth: depth,
      max_accounts: maxAccounts,
      max_following: maxFollowing,
      max_followers: maxFollowers,
      rate_profile: rate,
      proxy_urls: proxies
        .split(/[\n,]/)
        .map((p) => p.trim())
        .filter(Boolean),
    });
  }

  return (
    <form className="card crawlform" onSubmit={submit}>
      <div className="crawlform__head">
        <span className="eyebrow">NEW&nbsp;CRAWL</span>
        <p className="text-mute crawlform__sub">
          Seed a username; the crawler walks its network up to the chosen depth.
        </p>
      </div>

      <div className="crawlform__grid">
        <TextField
          label="Seed username"
          placeholder="elonmusk"
          value={seed}
          error={seedError}
          onChange={(e) => setSeed(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <SelectField
          label="Max depth"
          value={String(depth)}
          onChange={(e) => setDepth(Number(e.target.value))}
          options={[1, 2, 3, 4, 5].map((d) => ({ value: String(d), label: String(d) }))}
        />
        <div className="field">
          <label className="field__label">Max accounts</label>
          <input
            type="number"
            className="input"
            min={1}
            max={10000}
            value={maxAccounts}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v) && v >= 1) setMaxAccounts(v);
            }}
          />
          <div className="crawlform__presets">
            {ACCOUNT_PRESETS.map((n) => (
              <button
                key={n}
                type="button"
                className={`crawlform__preset${maxAccounts === n ? " crawlform__preset--active" : ""}`}
                onClick={() => setMaxAccounts(n)}
              >
                {n >= 1000 ? `${n / 1000}k` : n}
              </button>
            ))}
          </div>
          <span className="field__hint">Type any value or pick a preset.</span>
        </div>
        <div className="field">
          <label className="field__label">Max following / account</label>
          <input
            type="number"
            className="input"
            min={1}
            max={5000}
            value={maxFollowing}
            onChange={(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v) && v >= 1) setMaxFollowing(v); }}
          />
          <div className="crawlform__presets">
            {[25, 50, 100, 200, 500].map((n) => (
              <button key={n} type="button"
                className={`crawlform__preset${maxFollowing === n ? " crawlform__preset--active" : ""}`}
                onClick={() => setMaxFollowing(n)}>{n}</button>
            ))}
          </div>
        </div>
        <div className="field">
          <label className="field__label">Max followers / account</label>
          <input
            type="number"
            className="input"
            min={1}
            max={5000}
            value={maxFollowers}
            onChange={(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v) && v >= 1) setMaxFollowers(v); }}
          />
          <div className="crawlform__presets">
            {[25, 50, 100, 200, 500].map((n) => (
              <button key={n} type="button"
                className={`crawlform__preset${maxFollowers === n ? " crawlform__preset--active" : ""}`}
                onClick={() => setMaxFollowers(n)}>{n}</button>
            ))}
          </div>
        </div>
        <SelectField
          label="Rate profile"
          value={rate}
          onChange={(e) => setRate(e.target.value as JobCreate["rate_profile"])}
          options={RATE_OPTIONS}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="proxies">
          Proxies (optional)
        </label>
        <textarea
          id="proxies"
          className="input crawlform__proxies"
          placeholder="http://user:pass@host:port — one per line"
          value={proxies}
          onChange={(e) => setProxies(e.target.value)}
          rows={2}
          spellCheck={false}
        />
        <span className="field__hint">
          Bring your own proxies. Leave blank to crawl from your own IP.
        </span>
      </div>

      {mutation.isError && (
        <p className="field__error" role="alert">
          {mutation.error instanceof ApiError
            ? mutation.error.message
            : "Failed to start crawl."}
        </p>
      )}

      <div className="crawlform__actions">
        <Pill
          variant="primary"
          type="submit"
          icon={<Play size={15} />}
          loading={mutation.isPending}
        >
          Start crawl
        </Pill>
      </div>
    </form>
  );
}
