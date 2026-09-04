"use client";

import { usePathname } from "next/navigation";
import DashboardPage from "@/components/pages/DashboardPage";
import RingsPage from "@/components/pages/RingsPage";
import RingDetailPage from "@/components/pages/RingDetailPage";
import TransactionsPage from "@/components/pages/TransactionsPage";
import GraphPage from "@/components/pages/GraphPage";
import GraphAnalysisPage from "@/components/pages/GraphAnalysisPage";
import FairnessPage from "@/components/pages/FairnessPage";
import MetricsPage from "@/components/pages/MetricsPage";
import InvestigationPage from "@/components/pages/InvestigationPage";
import EvaluationPage from "@/components/pages/EvaluationPage";
import VersionsPage from "@/components/pages/VersionsPage";
import ChargebackPage from "@/components/pages/ChargebackPage";
import ChargebackCasePage from "@/components/pages/ChargebackCasePage";
import { useSentinelData } from "@/lib/SentinelDataProvider";

export default function PageRouter() {
  const pathname = usePathname();
  const data = useSentinelData();

  // Ring detail: /rings/[id]
  if (pathname.startsWith("/rings/")) {
    const ringId = pathname.split("/rings/")[1];
    return <RingDetailPage ringId={ringId} />;
  }

  // Chargeback case detail: /chargebacks/[id]
  if (pathname.startsWith("/chargebacks/")) {
    const caseId = pathname.split("/chargebacks/")[1];
    return <ChargebackCasePage caseId={caseId} />;
  }

  switch (pathname) {
    case "/rings":
      return <RingsPage alerts={data.alerts} />;
    case "/transactions":
      return <TransactionsPage recentTx={data.recentTx} alerts={data.alerts} />;
    case "/graph":
      return <GraphPage recentTx={data.recentTx} alerts={data.alerts} />;
    case "/graph-analysis":
      return <GraphAnalysisPage recentTx={data.recentTx} alerts={data.alerts} />;
    case "/fairness":
      return <FairnessPage cohorts={data.cohorts} />;
    case "/metrics":
      return <MetricsPage metrics={data.metrics} />;
    case "/investigation":
      return <InvestigationPage />;
    case "/evaluation":
      return <EvaluationPage />;
    case "/versions":
      return <VersionsPage />;
    case "/chargebacks":
      return <ChargebackPage />;
    default:
      return (
        <DashboardPage
          alerts={data.alerts}
          metrics={data.metrics}
          cohorts={data.cohorts}
          recentTx={data.recentTx}
          connectionState={data.connectionState}
          streamStats={data.streamStats}
        />
      );
  }
}
