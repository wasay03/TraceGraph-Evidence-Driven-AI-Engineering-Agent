CREATE OR REPLACE FUNCTION tg_run_create(p_repo_id integer, p_snapshot_id integer, p_mode text, p_config text, p_request text)
RETURNS TABLE (id bigint, repo_id integer, snapshot_id integer, mode text, config text, status text, phase text, request text, state jsonb, version integer, created_at timestamptz, updated_at timestamptz)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    INSERT INTO agent_run AS r (repo_id, snapshot_id, mode, config, request)
    VALUES (p_repo_id, p_snapshot_id, p_mode, p_config, p_request)
    RETURNING r.id, r.repo_id, r.snapshot_id, r.mode, r.config, r.status, r.phase, r.request, r.state, r.version, r.created_at, r.updated_at;
END;
$$;
