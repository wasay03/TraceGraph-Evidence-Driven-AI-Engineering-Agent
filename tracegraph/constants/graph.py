TIER_ASSERTED = "asserted"
TIER_OBSERVED = "observed"
TIER_DERIVED = "derived"
TIER_INFERRED = "inferred"
TIER_HYPOTHESIZED = "hypothesized"

# Strongest first; the index is the tier's rank (lower is stronger).
TIERS: tuple[str, ...] = (TIER_ASSERTED, TIER_OBSERVED, TIER_DERIVED, TIER_INFERRED, TIER_HYPOTHESIZED)
TIER_RANK: dict[str, int] = {name: rank for rank, name in enumerate(TIERS)}

SNAPSHOT_PENDING = "pending"
SNAPSHOT_INDEXING = "indexing"
SNAPSHOT_READY = "ready"
SNAPSHOT_FAILED = "failed"
SNAPSHOT_STATUSES: tuple[str, ...] = (SNAPSHOT_PENDING, SNAPSHOT_INDEXING, SNAPSHOT_READY, SNAPSHOT_FAILED)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_STATUSES: tuple[str, ...] = (JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, JOB_FAILED)

JOB_KIND_FULL = "full"
JOB_KIND_INCREMENTAL = "incremental"
JOB_KINDS: tuple[str, ...] = (JOB_KIND_FULL, JOB_KIND_INCREMENTAL)

OVERLAY_OPS: tuple[str, ...] = ("add_node", "drop_node", "set_props", "add_edge", "drop_edge")

OWNER_KIND_NODE = "node"
OWNER_KIND_EDGE = "edge"
