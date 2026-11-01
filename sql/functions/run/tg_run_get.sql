CREATE OR REPLACE FUNCTION tg_run_get(p_id bigint)
RETURNS TABLE (id bigint, repo_id integer, snapshot_id integer, mode text, config text, status text, phase text, request text, state jsonb, version integer, created_at timestamptz, updated_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY SELECT r.id, r.repo_id, r.snapshot_id, r.mode, r.config, r.status, r.phase, r.request, r.state, r.version, r.created_at, r.updated_at FROM agent_run r WHERE r.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Run % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
