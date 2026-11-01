-- Page of runs, newest first; carries budget and error instead of the full state.
CREATE OR REPLACE FUNCTION tg_run_list(p_repo_id integer, p_limit integer, p_offset integer)
RETURNS TABLE (
    id bigint, repo_id integer, snapshot_id integer, mode text, config text, status text, phase text, request text,
    budget jsonb, error text, created_at timestamptz, updated_at timestamptz, total bigint
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT r.id, r.repo_id, r.snapshot_id, r.mode, r.config, r.status, r.phase, r.request,
           coalesce(r.state -> 'budget', '{}'::jsonb), r.state ->> 'error', r.created_at, r.updated_at, count(*) OVER ()
    FROM agent_run r
    WHERE p_repo_id IS NULL OR r.repo_id = p_repo_id
    ORDER BY r.id DESC
    LIMIT p_limit OFFSET p_offset;
END;
$$;
