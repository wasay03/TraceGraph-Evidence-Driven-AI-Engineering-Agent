CREATE OR REPLACE FUNCTION tg_index_job_get(p_id bigint)
RETURNS TABLE (
    id bigint, repo_id integer, snapshot_id integer, kind job_kind, status job_status, attempts integer,
    error text, created_at timestamptz, started_at timestamptz, finished_at timestamptz
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT j.id, j.repo_id, j.snapshot_id, j.kind, j.status, j.attempts, j.error,
           j.created_at, j.started_at, j.finished_at
    FROM index_job j WHERE j.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Index job % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
