-- Claim the oldest queued job; concurrent workers skip rows locked by each other.
CREATE OR REPLACE FUNCTION tg_index_job_claim(p_worker text)
RETURNS TABLE (id bigint, repo_id integer, snapshot_id integer, kind job_kind, payload jsonb, attempts integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    UPDATE index_job j
    SET status = 'running', locked_by = p_worker, started_at = now(), attempts = j.attempts + 1
    WHERE j.id = (
        SELECT q.id FROM index_job q
        WHERE q.status = 'queued'
        ORDER BY q.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING j.id, j.repo_id, j.snapshot_id, j.kind, j.payload, j.attempts;
END;
$$;
