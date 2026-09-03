"use client";

import type { TxMessage, RingAlert } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { EmptyState } from "@/components/States";

export default function TransactionsPage({
  recentTx,
  alerts,
}: {
  recentTx: TxMessage[];
  alerts: RingAlert[];
}) {
  const flaggedIds = new Set(alerts.flatMap((a) => a.ring.members));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Transactions"
        description="Recent transaction stream from the live feed."
      />

      {recentTx.length === 0 ? (
        <EmptyState
          icon="⇉"
          title="No transactions yet"
          description="Waiting for the stream to begin emitting transactions."
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left font-mono text-[11px] uppercase tracking-wider text-fg-muted">
                  <th className="px-4 py-3 font-medium">Tx ID</th>
                  <th className="px-4 py-3 font-medium">Sender</th>
                  <th className="px-4 py-3 font-medium">Receiver</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {recentTx.map((tx) => {
                  const isFlagged = tx.is_fraud_ring_member;
                  return (
                    <tr
                      key={tx.tx_id}
                      className={`border-b border-border-subtle transition-colors hover:bg-surface-hover ${
                        isFlagged ? "bg-danger/5" : ""
                      }`}
                    >
                      <td className="px-4 py-2.5 mono-data text-xs text-fg-secondary">{tx.tx_id}</td>
                      <td className="px-4 py-2.5 mono-data text-xs">
                        <span className={flaggedIds.has(tx.sender) ? "text-danger" : "text-fg-secondary"}>
                          {tx.sender}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 mono-data text-xs">
                        <span className={flaggedIds.has(tx.receiver) ? "text-danger" : "text-fg-secondary"}>
                          {tx.receiver}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right mono-data text-xs text-fg">
                        ₹{tx.amount.toLocaleString("en-IN")}
                      </td>
                      <td className="px-4 py-2.5">
                        {isFlagged ? (
                          <StatusBadge variant="danger" dot>
                            Flagged
                          </StatusBadge>
                        ) : (
                          <StatusBadge variant="success" dot>
                            Clean
                          </StatusBadge>
                        )}
                      </td>
                      <td className="px-4 py-2.5 mono-data text-xs text-fg-muted">
                        {new Date(tx.ts).toLocaleTimeString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
