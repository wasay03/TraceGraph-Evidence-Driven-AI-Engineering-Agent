CREATE OR REPLACE FUNCTION tg_index_job_enqueue(p_repo_id integer, p_snapshot_id integer, p_kind job_kind, p_payload jsonb)
RETURNS TABLE (id bigint, repo_id integer, snapshot_id integer, kind job_kind, status job_status, created_at timestamptz)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    INSERT INTO index_job AS j (repo_id, snapshot_id, kind, payload)
    VALUES (p_repo_id, p_snapshot_id, p_kind, coalesce(p_payload, '{}'::jsonb))
    RETURNING j.id, j.repo_id, j.snapshot_id, j.kind, j.status, j.created_at;
END;
$$;
