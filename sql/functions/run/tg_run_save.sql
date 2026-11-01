-- Persist a run transition. Fails with TG409 when another writer advanced the version first.
CREATE OR REPLACE FUNCTION tg_run_save(p_id bigint, p_expected_version integer, p_status text, p_phase text, p_state jsonb)
RETURNS integer
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_version integer;
BEGIN
    UPDATE agent_run r
    SET status = p_status, phase = p_phase, state = p_state, version = r.version + 1, updated_at = now()
    WHERE r.id = p_id AND r.version = p_expected_version
    RETURNING r.version INTO v_version;
    IF v_version IS NULL THEN
        RAISE EXCEPTION 'Run % changed concurrently (expected version %)', p_id, p_expected_version
            USING ERRCODE = 'TG409';
    END IF;
    RETURN v_version;
END;
$$;
