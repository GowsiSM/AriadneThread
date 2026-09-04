"use client";

import { PageHeader } from "@/components/PageHeader";
import { LoadingState, EmptyState } from "@/components/States";
import StatusBadge from "@/components/StatusBadge";
import { useVersions } from "@/lib/useRestData";

function HashTag({ label, hash }: { label: string; hash: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-fg-secondary">{label}</span>
      <code className="rounded-md bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-fg">
        {hash}
      </code>
      <StatusBadge variant="success">active</StatusBadge>
    </div>
  );
}

export default function VersionsPage() {
  const { versions, loading, error, refresh } = useVersions();

  if (loading && !versions) return <LoadingState cycleMessages />;
  if (error && !versions)
    return (
      <EmptyState
        icon="⚠"
        title="Failed to load versions"
        description={error}
      />
    );
  if (!versions)
    return (
      <EmptyState
        icon="○"
        title="No version data"
        description="Detection has not run yet."
      />
    );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Versions"
        description="Deterministic version hashes for reproducibility and audit trail"
      >
        <button
          onClick={refresh}
          className="rounded-md border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:border-accent hover:text-accent"
        >
          ↻ Refresh
        </button>
      </PageHeader>

      {/* Version hashes */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Active Versions
        </h3>
        <div className="flex flex-col gap-2">
          <HashTag label="Detector" hash={`det-${versions.detector_version}`} />
          <HashTag label="Dataset" hash={`ds-${versions.dataset_version}`} />
          <HashTag label="Features" hash={`feat-${versions.feature_version}`} />
          <HashTag label="Run" hash={`run-${versions.run_version}`} />
        </div>
      </div>

      {/* Signal weights */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Signal Weights
        </h3>
        <div className="flex flex-col gap-2">
          {Object.entries(versions.signal_weights).map(([name, weight]) => (
            <div key={name} className="flex items-center gap-3">
              <span className="w-48 shrink-0 text-xs text-fg-secondary">
                {name.replace(/_/g, " ")}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-signal-bar-bg">
                <div
                  className="h-full rounded-full bg-signal-bar transition-all duration-300"
                  style={{ width: `${(weight as number) * 100}%` }}
                />
              </div>
              <span className="w-10 text-right font-mono text-xs text-fg-muted">
                {((weight as number) * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-lg bg-surface-subtle p-2.5 text-xs text-fg-muted">
          Threshold:{" "}
          <span className="font-mono text-fg">{versions.threshold}</span>
        </div>
      </div>

      {/* Enabled features */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Enabled Features
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {versions.features.map((f) => (
            <span
              key={f}
              className="rounded-md border border-border bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-fg-secondary"
            >
              {f}
            </span>
          ))}
        </div>
      </div>

      {/* Dataset config */}
      <div className="card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-muted">
          Dataset Configuration
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(versions.dataset_config).map(([key, val]) => (
            <div key={key} className="rounded-lg bg-surface-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-fg-muted">
                {key.replace(/_/g, " ")}
              </div>
              <div className="mt-0.5 font-mono text-lg font-semibold text-fg">
                {String(val)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
