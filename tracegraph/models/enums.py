from sqlalchemy.dialects.postgresql import ENUM

from tracegraph.constants.graph import JOB_KINDS, JOB_STATUSES, OVERLAY_OPS, SNAPSHOT_STATUSES, TIERS

tier_enum = ENUM(*TIERS, name="tier", create_type=True)
snapshot_status_enum = ENUM(*SNAPSHOT_STATUSES, name="snapshot_status", create_type=True)
job_status_enum = ENUM(*JOB_STATUSES, name="job_status", create_type=True)
job_kind_enum = ENUM(*JOB_KINDS, name="job_kind", create_type=True)
overlay_op_enum = ENUM(*OVERLAY_OPS, name="overlay_op_kind", create_type=True)
