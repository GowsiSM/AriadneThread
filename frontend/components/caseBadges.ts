import type { BadgeVariant } from "./StatusBadge";
import type { CaseStatus, CasePriority } from "@/lib/types";

export function caseStatusVariant(status: CaseStatus): BadgeVariant {
  switch (status) {
    case "OBSERVED":
      return "neutral";
    case "SUSPICIOUS":
      return "info";
    case "HIGH_RISK":
      return "warning";
    case "UNDER_REVIEW":
      return "info";
    case "CONFIRMED":
      return "danger";
    case "DISMISSED":
      return "success";
    case "RESOLVED":
      return "success";
    default:
      return "neutral";
  }
}

export function casePriorityVariant(priority: CasePriority): BadgeVariant {
  switch (priority) {
    case "CRITICAL":
      return "danger";
    case "HIGH":
      return "warning";
    case "MEDIUM":
      return "info";
    case "LOW":
      return "success";
    default:
      return "neutral";
  }
}

/**
 * Allowed next transitions for a given status, matching the backend state machine.
 */
export function nextTransitions(status: CaseStatus): CaseStatus[] {
  switch (status) {
    case "OBSERVED":
      return ["SUSPICIOUS", "DISMISSED"];
    case "SUSPICIOUS":
      return ["HIGH_RISK", "UNDER_REVIEW", "DISMISSED"];
    case "HIGH_RISK":
      return ["UNDER_REVIEW", "CONFIRMED", "DISMISSED"];
    case "UNDER_REVIEW":
      return ["CONFIRMED", "DISMISSED", "RESOLVED"];
    default:
      return []; // terminal states
  }
}
