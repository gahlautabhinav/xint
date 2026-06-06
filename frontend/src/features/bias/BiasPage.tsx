import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ShieldAlert, Wifi, WifiOff } from "lucide-react";

import { api } from "@/lib/api";
import type { BiasVerdict } from "@/lib/types";
import { LoadingState } from "@/components/states";
import "./bias.css";

const FLAG_LABELS: { key: keyof BiasVerdict; label: string }[] = [
  { key: "is_antisemitic",           label: "Antisemitic" },
  { key: "is_anti_jew",              label: "Anti-Jewish" },
  { key: "is_anti_israel",           label: "Anti-Israel" },
  { key: "is_anti_zionist",          label: "Anti-Zionist" },
  { key: "is_pro_islamist_extremist",label: "Pro-Islamist Extremism" },
  { key: "is_pro_hamas_hezbollah",   label: "Pro-Hamas/Hezbollah" },
  { key: "is_pro_palestine",         label: "Pro-Palestine" },
  { key: "is_white_supremacist",     label: "White Supremacist" },
  { key: "is_neo_nazi",              label: "Neo-Nazi" },
];

function activeFlags(verdict: BiasVerdict): string[] {
  return FLAG_LABELS
    .filter(({ key }) => verdict[key] === true)
    .map(({ label }) => label);
}

export function BiasPage() {
  const statusQuery = useQuery({
    queryKey: ["bias-status"],
    queryFn: api.getBiasStatus,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const flagsQuery = useQuery({
    queryKey: ["bias-flags"],
    queryFn: api.listBiasFlags,
    enabled: statusQuery.data?.connected === true,
    staleTime: 60_000,
  });

  const connected = statusQuery.data?.connected ?? false;
  const agentUrl = statusQuery.data?.url;
  const rows = flagsQuery.data ?? [];

  return (
    <div className="page">
      <header className="page__head reveal reveal-1">
        <span className="eyebrow">OSINT&nbsp;//&nbsp;BIAS ANALYSIS</span>
        <h1 className="page__title">Bias Flags</h1>
      </header>

      {/* ── Status bar ── */}
      <div className="bias-status-bar reveal reveal-2">
        <span
          className={`bias-dot ${connected ? "bias-dot--online" : "bias-dot--offline"}`}
          aria-hidden
        />
        <span
          className={`bias-badge ${connected ? "bias-badge--online" : "bias-badge--offline"} mono`}
        >
          {connected ? <Wifi size={11} /> : <WifiOff size={11} />}
          {connected ? "Agent online" : "Agent offline"}
        </span>
        {agentUrl && (
          <span className="mono" style={{ fontSize: 11, color: "var(--c-mute)" }}>
            {agentUrl}
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--c-mute)" }} className="mono">
          {rows.length} accounts analyzed
        </span>
      </div>

      {/* ── Setup instructions when offline ── */}
      {!connected && (
        <div className="bias-setup-card reveal reveal-3">
          <ShieldAlert size={22} />
          <div>
            <p>Bias agent not connected.</p>
            <p style={{ marginTop: 6 }}>
              1. Add <code>BIAS_AGENT_URL=http://127.0.0.1:5000</code> to <code>.env</code>
            </p>
            <p>
              2. In <code>../xint-bias-agent</code>: add <code>GEMINI_API_KEY</code> to its <code>.env</code>,
              then run <code>py -3.10 -m src.server</code>
            </p>
            <p>
              3. Restart the xint backend. Crawls will auto-send timelines to the agent.
            </p>
          </div>
        </div>
      )}

      {/* ── Flags table ── */}
      {connected && (
        <div className="reveal reveal-3">
          {flagsQuery.isLoading ? (
            <LoadingState title="Loading flags…" />
          ) : rows.length === 0 ? (
            <p className="bias-empty">
              No accounts analyzed yet. Run a crawl — xint will auto-send timelines to the bias agent.
            </p>
          ) : (
            <div className="bias-table-wrap">
              <table className="bias-table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Flags</th>
                    <th>Confidence</th>
                    <th>Evidence</th>
                    <th>Analyzed</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const flags = row.verdict ? activeFlags(row.verdict) : [];
                    const conf = row.verdict?.confidence ?? 0;
                    return (
                      <tr key={row.username}>
                        <td>
                          <Link
                            to={`/dossier/twitter/${row.username}`}
                            className="bias-handle-link"
                          >
                            @{row.username}
                          </Link>
                        </td>
                        <td>
                          {flags.length > 0 ? (
                            <div className="bias-flags">
                              {flags.map((f) => (
                                <span key={f} className="bias-flag">{f}</span>
                              ))}
                            </div>
                          ) : (
                            <span className="bias-flag--none">none</span>
                          )}
                        </td>
                        <td>
                          <div className="bias-conf">
                            <div className="bias-conf__bar">
                              <div
                                className="bias-conf__fill"
                                style={{ width: `${Math.round(conf * 100)}%` }}
                              />
                            </div>
                            <span className="bias-conf__pct">{Math.round(conf * 100)}%</span>
                          </div>
                        </td>
                        <td>
                          {row.verdict?.evidence ? (
                            <span className="bias-evidence" title={row.verdict.evidence}>
                              {row.verdict.evidence}
                            </span>
                          ) : (
                            <span className="bias-flag--none">—</span>
                          )}
                        </td>
                        <td>
                          <span className="mono" style={{ fontSize: 11, color: "var(--c-mute)" }}>
                            {row.updated_at ? row.updated_at.slice(0, 10) : "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
