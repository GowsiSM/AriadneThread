"""
Deterministic versioning for the detector, dataset, and features.

Every detection run can be tagged with a version string that encodes
exactly which heuristic weights, threshold, and dataset configuration
produced the result. This makes experiments reproducible and lets the
audit trail answer "which detector version flagged this ring?"

Design (from the brief):
  - Detector version = hash of signal weights + threshold + algorithm constants
  - Dataset version  = hash of dataset config (n_users, n_tx, n_rings, seed)
  - Feature version  = hash of enabled features (motifs, flow, roles, etc.)

All hashes are deterministic SHA-256 truncated to 12 hex chars.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# Signal weights  (must match detection.py exactly)
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS: dict[str, float] = {
    "cycle_involvement": 0.25,
    "community_isolation": 0.22,
    "pagerank_anomaly": 0.18,
    "temporal_burst": 0.12,
    "neighbor_propagation": 0.08,
    "motif_presence": 0.08,
    "flow_concentration": 0.07,
}

DEFAULT_THRESHOLD: float = 55.0

# Enabled features (must match detection.py + graph_intelligence.py)
ENABLED_FEATURES: list[str] = [
    "cycle_detection",
    "community_detection_louvain",
    "pagerank",
    "temporal_burst",
    "neighbor_propagation",
    "motif_detection",
    "flow_analysis",
    "typology_classification",
    "role_assignment",
    "ring_decomposition",
]

# Dataset defaults (must match data_gen.py)
DATASET_CONFIG: dict = {
    "n_background_users": 300,
    "n_background_tx": 1200,
    "n_rings": 3,
    "seed": 42,
}


# ---------------------------------------------------------------------------
# Hashing utility
# ---------------------------------------------------------------------------

def _stable_hash(obj: object) -> str:
    """Deterministic SHA-256 of a JSON-serializable object, truncated to 12 hex chars."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Version dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectorVersion:
    """Version tag for a specific detector configuration."""
    hash: str
    signal_weights: dict[str, float]
    threshold: float
    features: list[str]

    @classmethod
    def compute(
        cls,
        weights: dict[str, float] | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        features: list[str] | None = None,
    ) -> DetectorVersion:
        w = weights or SIGNAL_WEIGHTS
        f = features or ENABLED_FEATURES
        h = _stable_hash({
            "weights": w,
            "threshold": threshold,
            "features": sorted(f),
        })
        return cls(hash=h, signal_weights=dict(w), threshold=threshold, features=list(f))

    @property
    def short(self) -> str:
        return f"det-{self.hash}"


@dataclass(frozen=True)
class DatasetVersion:
    """Version tag for a specific dataset configuration."""
    hash: str
    config: dict

    @classmethod
    def compute(cls, config: dict | None = None) -> DatasetVersion:
        c = config or DATASET_CONFIG
        h = _stable_hash(c)
        return cls(hash=h, config=dict(c))

    @property
    def short(self) -> str:
        return f"ds-{self.hash}"


@dataclass(frozen=True)
class FeatureVersion:
    """Version tag for the enabled feature set."""
    hash: str
    features: list[str]

    @classmethod
    def compute(cls, features: list[str] | None = None) -> FeatureVersion:
        f = features or ENABLED_FEATURES
        h = _stable_hash({"features": sorted(f)})
        return cls(hash=h, features=list(f))

    @property
    def short(self) -> str:
        return f"feat-{self.hash}"


@dataclass(frozen=True)
class RunVersion:
    """Combined version tag for a single detection run."""
    detector: DetectorVersion
    dataset: DatasetVersion
    features: FeatureVersion
    combined_hash: str = ""

    def __post_init__(self):
        if not self.combined_hash:
            combined = _stable_hash({
                "detector": self.detector.hash,
                "dataset": self.dataset.hash,
                "features": self.features.hash,
            })
            object.__setattr__(self, "combined_hash", combined)

    @property
    def short(self) -> str:
        return f"run-{self.combined_hash}"


# ---------------------------------------------------------------------------
# Module-level singletons (computed once, deterministic)
# ---------------------------------------------------------------------------

DETECTOR_VERSION = DetectorVersion.compute()
DATASET_VERSION = DatasetVersion.compute()
FEATURE_VERSION = FeatureVersion.compute()
RUN_VERSION = RunVersion(DETECTOR_VERSION, DATASET_VERSION, FEATURE_VERSION)


def log_versions() -> dict:
    """Return a JSON-serializable dict of all current versions for audit logging."""
    return {
        "detector_version": DETECTOR_VERSION.hash,
        "dataset_version": DATASET_VERSION.hash,
        "feature_version": FEATURE_VERSION.hash,
        "run_version": RUN_VERSION.combined_hash,
        "signal_weights": DETECTOR_VERSION.signal_weights,
        "threshold": DETECTOR_VERSION.threshold,
        "features": DETECTOR_VERSION.features,
        "dataset_config": DATASET_VERSION.config,
    }
